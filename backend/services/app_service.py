"""Azure App Service deployment helpers for customer applications.

The deployment worker builds a customer image in Azure Container Registry and
publishes it to an existing Linux App Service plan. A deployment is never marked
live from a constructed address: Azure must report the site running and its
public endpoint must answer first.
"""

from __future__ import annotations

import http.client
import io
import ipaddress
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator
from urllib.parse import urlsplit

try:
    from backend.services.redaction import redact_sensitive_text
except ImportError:  # pragma: no cover - worker-style imports
    from services.redaction import redact_sensitive_text


ACR_PULL_ROLE_ID = "7f951dda-4ed3-4680-a7ca-43fe172d538d"


class AzureDeploymentError(RuntimeError):
    """A user-safe error raised from an Azure deployment command."""


@dataclass(frozen=True)
class AppServiceRelease:
    app_name: str
    image_ref: str
    live_url: str
    revision: str


@dataclass(frozen=True)
class RegistryAccessToken:
    registry_server: str
    username: str
    access_token: str


def normalize_app_name(value: str) -> str:
    """Return an App Service-compatible, globally readable site name."""
    raw = "".join(char.lower() if char.isalnum() else "-" for char in value)
    raw = re.sub(r"-+", "-", raw).strip("-") or "app"
    if len(raw) > 60:
        # Queue callers append a stable project UUID fragment. Preserve it
        # when truncating long repository names so global App Service names do
        # not collapse to the same prefix.
        identity_suffix = re.search(r"-[0-9a-f]{8}$", raw)
        if identity_suffix:
            suffix = identity_suffix.group(0)
            raw = f"{raw[: 60 - len(suffix)].rstrip('-')}{suffix}"
        else:
            raw = raw[:60].rstrip("-")
    return raw if len(raw) >= 2 else f"{raw}0"


def _registry_name(login_server: str) -> str:
    name = str(login_server or "").strip().lower().split(".", 1)[0]
    if not name or not name.isalnum():
        raise AzureDeploymentError("The Azure container registry name is invalid.")
    return name


def _run(command: list[str], *, env: dict[str, str], cwd: str | None = None) -> Generator[str, None, None]:
    """Run Azure CLI without a shell; credentials are never yielded to logs."""
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except FileNotFoundError as error:
        raise AzureDeploymentError("The deployment worker is missing the Azure CLI.") from error

    if process.stdout:
        with io.TextIOWrapper(process.stdout, encoding="utf-8", errors="replace") as output:
            for line in output:
                value = redact_sensitive_text(line.strip(), maximum_length=10_000)
                if value:
                    yield value
    if process.wait():
        raise AzureDeploymentError("Azure rejected the deployment request. Review the Azure deployment log.")


def _capture(command: list[str], *, env: dict[str, str], cwd: str | None = None) -> str:
    return "\n".join(_run(command, env=env, cwd=cwd)).strip()


def _azure_environment(connection: Any, config_dir: str) -> dict[str, str]:
    environment = os.environ.copy()
    # Authentication is performed explicitly by ``_sign_in``. Do not let a
    # service-principal secret inherited by the worker leak into Azure CLI
    # child processes; the configured secret reaches ``az login`` only via
    # standard input.
    for secret_name in ("AZURE_CLIENT_SECRET", "ARM_CLIENT_SECRET", "AZURE_PASSWORD"):
        environment.pop(secret_name, None)
    environment.update(
        {
            "AZURE_CONFIG_DIR": config_dir,
            "AZURE_CORE_ONLY_SHOW_ERRORS": "true",
            "AZURE_CLIENT_ID": str(connection.client_id),
            "AZURE_TENANT_ID": str(connection.tenant_id),
        }
    )
    return environment


def _sign_in(connection: Any, client_secret: str, env: dict[str, str]) -> None:
    executable = shutil.which("az")
    if not executable:
        raise AzureDeploymentError("The deployment worker is missing the Azure CLI.")

    command_environment = dict(env)
    for secret_name in ("AZURE_CLIENT_SECRET", "ARM_CLIENT_SECRET", "AZURE_PASSWORD"):
        command_environment.pop(secret_name, None)
    command = [
        executable,
        "login",
        "--service-principal",
        "--username",
        str(connection.client_id),
        "--tenant",
        str(connection.tenant_id),
        "--output",
        "none",
    ]
    try:
        completed = subprocess.run(
            command,
            env=command_environment,
            input=f"{client_secret}\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as error:
        raise AzureDeploymentError("Azure authentication was unavailable.") from error
    if completed.returncode != 0:
        raise AzureDeploymentError("Azure authentication was rejected.")

    list(_run(
        ["az", "account", "set", "--subscription", str(connection.subscription_id)],
        env=command_environment,
    ))


def _port_for(metadata: dict[str, Any]) -> int:
    value = str(metadata.get("port") or "").strip()
    if value.isdigit() and 1 <= int(value) <= 65535:
        return int(value)
    return 8080 if metadata.get("framework") in {"FastAPI", "Flask"} else 3000


def _dockerfile_for(repo_path: str, generated_dockerfile: str | None) -> str:
    existing = Path(repo_path) / "Dockerfile"
    if existing.is_file():
        return "Dockerfile"
    if not generated_dockerfile:
        raise AzureDeploymentError("This application needs a Dockerfile before it can be launched.")
    generated = Path(repo_path) / ".zeroops.Dockerfile"
    generated.write_text(generated_dockerfile, encoding="utf-8")
    return generated.name


def build_image(
    *, connection: Any, client_secret: str, repo_path: str, image_ref: str, generated_dockerfile: str | None
) -> Generator[str, None, None]:
    """Build in ACR; the control plane does not require Docker-in-Docker."""
    registry = _registry_name(str(connection.acr_login_server))
    try:
        repository_and_tag = image_ref.split("/", 1)[1]
    except IndexError as error:
        raise AzureDeploymentError("The Azure image reference is invalid.") from error

    config_dir = tempfile.mkdtemp(prefix="zeroops-az-")
    try:
        env = _azure_environment(connection, config_dir)
        _sign_in(connection, client_secret, env)
        dockerfile = _dockerfile_for(repo_path, generated_dockerfile)
        yield "Building your application in Azure…"
        yield from _run([
            "az", "acr", "build", "--registry", registry, "--image", repository_and_tag,
            "--file", dockerfile, repo_path, "--output", "none",
        ], env=env)
        yield "Your application image is ready."
    finally:
        shutil.rmtree(config_dir, ignore_errors=True)


def resolve_image_digest(
    *,
    connection: Any,
    client_secret: str,
    image_ref: str,
) -> str:
    """Resolve an ACR tag to its immutable, registry-reported digest.

    Azure CLI output is captured through the same redacting command boundary
    as deployment operations.  A malformed or absent digest fails closed; a
    mutable tag is never relabeled as an image digest by the caller.
    """

    login_server = str(getattr(connection, "acr_login_server", "") or "").strip().lower().rstrip("/")
    registry = _registry_name(login_server)
    prefix = f"{login_server}/"
    if not image_ref.lower().startswith(prefix) or "@" in image_ref:
        raise AzureDeploymentError("The Azure image tag is invalid for the configured registry.")
    repository_and_tag = image_ref[len(prefix):]
    if not re.fullmatch(r"[a-z0-9]+(?:[._/-][a-z0-9]+)*(?::[A-Za-z0-9][A-Za-z0-9._-]{0,127})", repository_and_tag):
        raise AzureDeploymentError("The Azure image tag is invalid.")
    repository = repository_and_tag.rsplit(":", 1)[0]

    config_dir = tempfile.mkdtemp(prefix="zeroops-az-")
    try:
        env = _azure_environment(connection, config_dir)
        _sign_in(connection, client_secret, env)
        digest = _capture([
            "az",
            "acr",
            "repository",
            "show",
            "--name",
            registry,
            "--image",
            repository_and_tag,
            "--query",
            "digest",
            "--output",
            "tsv",
        ], env=env).strip().lower()
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise AzureDeploymentError(
                "Azure Container Registry did not return a verified image digest."
            )
        return f"{login_server}/{repository}@{digest}"
    finally:
        shutil.rmtree(config_dir, ignore_errors=True)


def acquire_registry_access_token(
    *,
    connection: Any,
    client_secret: str,
) -> RegistryAccessToken:
    """Return a short-lived ACR token without logging or persisting it.

    The exposed token is captured directly from bounded JSON stdout.  It is
    never placed in a child-process argument, environment variable, exception,
    or deployment log.  The caller must keep it in memory only and use it for
    one exact-registry scan invocation.
    """

    login_server = str(getattr(connection, "acr_login_server", "") or "").strip().lower().rstrip("/")
    if not re.fullmatch(r"[a-z0-9]+\.azurecr\.io", login_server):
        raise AzureDeploymentError("The Azure container registry server is invalid.")
    registry = _registry_name(login_server)
    executable = shutil.which("az")
    if not executable:
        raise AzureDeploymentError("The deployment worker is missing the Azure CLI.")

    config_dir = tempfile.mkdtemp(prefix="zeroops-az-")
    try:
        env = _azure_environment(connection, config_dir)
        _sign_in(connection, client_secret, env)
        completed = subprocess.run(
            [
                executable,
                "acr",
                "login",
                "--name",
                registry,
                "--expose-token",
                "--output",
                "json",
            ],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=60,
            check=False,
        )
        if completed.returncode != 0 or len(completed.stdout) > 1_000_000:
            raise AzureDeploymentError("Azure Container Registry authentication was unavailable.")
        try:
            payload = json.loads(completed.stdout)
        except (json.JSONDecodeError, TypeError) as error:
            raise AzureDeploymentError("Azure Container Registry returned invalid authentication metadata.") from error
        token = str(payload.get("accessToken") or "") if isinstance(payload, dict) else ""
        username = str(payload.get("username") or "00000000-0000-0000-0000-000000000000") if isinstance(payload, dict) else ""
        if not token or len(token) > 16_384 or not re.fullmatch(r"[0-9a-f-]{36}", username.lower()):
            raise AzureDeploymentError("Azure Container Registry returned invalid authentication metadata.")
        return RegistryAccessToken(
            registry_server=login_server,
            username=username,
            access_token=token,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as error:
        raise AzureDeploymentError("Azure Container Registry authentication was unavailable.") from error
    finally:
        shutil.rmtree(config_dir, ignore_errors=True)


def _set_app_settings(
    *, app_name: str, resource_group: str, environment_variables: dict[str, tuple[str, bool]], port: str, env: dict[str, str]
) -> None:
    settings = {"WEBSITES_PORT": port}
    for key, (value, _) in environment_variables.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise AzureDeploymentError(f"Environment variable name '{key}' is invalid for App Service.")
        settings[key] = value

    # Keep setting values out of the process argument list. Azure CLI supports
    # @file JSON input; the file lives inside the already short-lived,
    # permission-scoped CLI directory and is removed immediately afterwards.
    settings_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="appsettings-",
            suffix=".json",
            dir=env.get("AZURE_CONFIG_DIR"),
            delete=False,
        ) as settings_file:
            json.dump(settings, settings_file)
            settings_path = settings_file.name
        try:
            os.chmod(settings_path, 0o600)
        except OSError:
            pass
        list(_run([
            "az", "webapp", "config", "appsettings", "set", "--name", app_name,
            "--resource-group", resource_group, "--settings", f"@{settings_path}", "--output", "none",
        ], env=env))
    finally:
        if settings_path:
            try:
                os.unlink(settings_path)
            except FileNotFoundError:
                pass


def deploy_image(
    *,
    connection: Any,
    client_secret: str,
    app_name: str,
    image_ref: str,
    metadata: dict[str, Any],
    environment_variables: dict[str, tuple[str, bool]] | None = None,
) -> Generator[str | AppServiceRelease, None, None]:
    """Create/update a Linux App Service site and yield its Azure-reported URL."""
    app_name = normalize_app_name(app_name)
    resource_group = str(connection.resource_group)
    plan_name = str(getattr(connection, "app_service_plan", "") or "").strip()
    registry_server = str(connection.acr_login_server or "").rstrip("/")
    if not plan_name:
        raise AzureDeploymentError("Azure hosting needs an existing Linux App Service plan before launch.")
    if not registry_server:
        raise AzureDeploymentError("Azure hosting needs a container registry before launch.")

    config_dir = tempfile.mkdtemp(prefix="zeroops-az-")
    try:
        env = _azure_environment(connection, config_dir)
        _sign_in(connection, client_secret, env)
        exists = True
        try:
            _capture(["az", "webapp", "show", "--name", app_name, "--resource-group", resource_group, "--output", "none"], env=env)
        except AzureDeploymentError:
            exists = False

        if not exists:
            yield "Creating your application site…"
            yield from _run([
                "az", "webapp", "create", "--name", app_name, "--resource-group", resource_group,
                "--plan", plan_name, "--deployment-container-image-name", image_ref, "--output", "none",
            ], env=env)

        principal_id = _capture([
            "az", "webapp", "identity", "assign", "--name", app_name, "--resource-group", resource_group,
            "--query", "principalId", "--output", "tsv",
        ], env=env)
        registry_id = _capture([
            "az", "acr", "show", "--name", _registry_name(registry_server), "--query", "id", "--output", "tsv",
        ], env=env)
        if not principal_id or not registry_id:
            raise AzureDeploymentError("Azure could not configure private image access for this application.")
        try:
            _capture([
                "az", "role", "assignment", "create", "--assignee-object-id", principal_id,
                "--assignee-principal-type", "ServicePrincipal", "--role", ACR_PULL_ROLE_ID,
                "--scope", registry_id, "--output", "none",
            ], env=env)
        except AzureDeploymentError as error:
            raise AzureDeploymentError(
                "Azure could not grant AcrPull to the application identity on the "
                "configured registry. Grant the deployment principal role-assignment "
                "permission at the registry scope and retry."
            ) from error

        yield "Publishing your new version…"
        yield from _run([
            "az", "webapp", "config", "set", "--name", app_name, "--resource-group", resource_group,
            "--generic-configurations", '{"acrUseManagedIdentityCreds": true}', "--output", "none",
        ], env=env)
        yield from _run([
            "az", "webapp", "config", "container", "set", "--name", app_name,
            "--resource-group", resource_group, "--docker-custom-image-name", image_ref,
            "--docker-registry-server-url", f"https://{registry_server}", "--output", "none",
        ], env=env)
        _set_app_settings(
            app_name=app_name,
            resource_group=resource_group,
            environment_variables=environment_variables or {},
            port=str(_port_for(metadata)),
            env=env,
        )
        yield from _run([
            "az", "webapp", "restart", "--name", app_name, "--resource-group", resource_group, "--output", "none",
        ], env=env)

        host = _capture([
            "az", "webapp", "show", "--name", app_name, "--resource-group", resource_group,
            "--query", "defaultHostName", "--output", "tsv",
        ], env=env)
        state = _capture([
            "az", "webapp", "show", "--name", app_name, "--resource-group", resource_group,
            "--query", "state", "--output", "tsv",
        ], env=env)
        revision = _capture([
            "az", "webapp", "show", "--name", app_name, "--resource-group", resource_group,
            "--query", "lastModifiedTimeUtc", "--output", "tsv",
        ], env=env)
        if not host or state.lower() != "running":
            raise AzureDeploymentError("Azure has not reported the application site running yet.")
        yield AppServiceRelease(app_name, image_ref, f"https://{host}", revision or image_ref.rsplit(":", 1)[-1])
    finally:
        shutil.rmtree(config_dir, ignore_errors=True)


def _validated_app_service_endpoint(live_url: str, expected_app_name: str) -> tuple[str, str]:
    """Return the exact Azure hostname and request target for a trusted site URL."""

    if (
        not isinstance(live_url, str)
        or not live_url
        or len(live_url) > 2_048
        or live_url != live_url.strip()
        or any(ord(character) < 33 or ord(character) == 127 for character in live_url)
    ):
        raise AzureDeploymentError("The application endpoint could not be safely verified.")
    raw_app_name = str(expected_app_name or "").strip()
    if not raw_app_name:
        raise AzureDeploymentError("The application endpoint could not be safely verified.")
    expected_host = f"{normalize_app_name(raw_app_name)}.azurewebsites.net"

    try:
        endpoint = urlsplit(live_url)
        port = endpoint.port
    except (TypeError, ValueError) as error:
        raise AzureDeploymentError("The application endpoint could not be safely verified.") from error
    if (
        endpoint.scheme.lower() != "https"
        or endpoint.hostname != expected_host
        or endpoint.username is not None
        or endpoint.password is not None
        or port is not None
        or endpoint.netloc.lower() != expected_host
        or endpoint.fragment
    ):
        raise AzureDeploymentError("The application endpoint could not be safely verified.")

    request_target = endpoint.path or "/"
    if endpoint.query:
        request_target = f"{request_target}?{endpoint.query}"
    return expected_host, request_target


def _resolve_public_addresses(host: str) -> tuple[str, ...]:
    """Resolve every address for ``host`` and reject any non-public result."""

    try:
        records = socket.getaddrinfo(
            host,
            443,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except (OSError, UnicodeError) as error:
        raise AzureDeploymentError("The application endpoint could not be safely verified.") from error

    addresses: list[str] = []
    for record in records:
        try:
            raw_address = str(record[4][0])
            if "%" in raw_address:
                raise ValueError("Scoped addresses are not public endpoints.")
            address = ipaddress.ip_address(raw_address)
        except (IndexError, TypeError, ValueError) as error:
            raise AzureDeploymentError("The application endpoint could not be safely verified.") from error
        if (
            not address.is_global
            or address.is_loopback
            or address.is_private
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        ):
            raise AzureDeploymentError("The application endpoint could not be safely verified.")
        canonical = str(address)
        if canonical not in addresses:
            addresses.append(canonical)
    if not addresses:
        raise AzureDeploymentError("The application endpoint could not be safely verified.")
    return tuple(addresses)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection that uses a pre-validated IP while retaining TLS SNI."""

    def __init__(self, host: str, address: str, *, timeout: float) -> None:
        super().__init__(
            host,
            port=443,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self._validated_address = address

    def connect(self) -> None:
        # Pin the connection to the address returned by the validation lookup.
        # TLS still authenticates the exact expected azurewebsites.net hostname.
        raw_socket = socket.create_connection(
            (self._validated_address, 443),
            self.timeout,
            self.source_address,
        )
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except Exception:
            raw_socket.close()
            raise


def _request_pinned_https(host: str, request_target: str, address: str, *, timeout: float) -> int:
    """Issue one direct HTTPS GET without proxy or redirect handling."""

    connection = _PinnedHTTPSConnection(host, address, timeout=timeout)
    try:
        connection.request(
            "GET",
            request_target,
            headers={"Host": host, "User-Agent": "ZeroOps release check", "Connection": "close"},
        )
        response = connection.getresponse()
        return int(response.status)
    finally:
        connection.close()


def verify_public_endpoint(
    live_url: str,
    *,
    expected_app_name: str,
    attempts: int = 12,
    delay_seconds: float = 5,
) -> None:
    """Require a direct 2xx response from the expected public App Service host.

    The verifier never follows redirects. DNS is resolved again for every
    attempt, every returned address must be globally routable, and each socket
    is pinned to an address that passed that validation while TLS verifies the
    exact ``<app>.azurewebsites.net`` hostname.
    """

    host, request_target = _validated_app_service_endpoint(live_url, expected_app_name)
    bounded_attempts = max(1, min(int(attempts), 60))
    bounded_delay = max(0.0, min(float(delay_seconds), 30.0))
    failure: Exception | None = None
    for attempt in range(bounded_attempts):
        try:
            addresses = _resolve_public_addresses(host)
        except AzureDeploymentError as error:
            failure = error
            addresses = ()

        for address in addresses:
            try:
                status = _request_pinned_https(host, request_target, address, timeout=15)
            except (OSError, TimeoutError, ssl.SSLError, http.client.HTTPException) as error:
                failure = error
                continue
            if 200 <= status < 300:
                return
            failure = AzureDeploymentError("The application endpoint returned an unhealthy response.")
            break

        if attempt + 1 < bounded_attempts:
            time.sleep(bounded_delay)
    raise AzureDeploymentError("The application did not become healthy after Azure reported it running.") from failure

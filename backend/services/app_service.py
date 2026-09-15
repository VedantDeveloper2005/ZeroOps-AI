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
import uuid
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

    collected_output: list[str] = []
    if process.stdout:
        with io.TextIOWrapper(process.stdout, encoding="utf-8", errors="replace") as output:
            for line in output:
                value = redact_sensitive_text(line.strip(), maximum_length=10_000)
                if value:
                    collected_output.append(value)
                    yield value
    returncode = process.wait()
    if returncode:
        details = " | ".join(collected_output[-5:]) if collected_output else "Unknown error"
        cmd_summary = f"{command[0]} {command[1] if len(command) > 1 else ''} {command[2] if len(command) > 2 else ''}"
        raise AzureDeploymentError(f"Azure rejected the deployment request ({cmd_summary}): {details}")


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
        "-p",
        "@-",
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
        dockerfile_path = str((Path(repo_path) / dockerfile).resolve())
        yield "Building your application in Azure…"
        yield from _run([
            "az", "acr", "build", "--registry", registry, "--image", repository_and_tag,
            "--file", dockerfile_path, repo_path, "--output", "none",
        ], env=env, cwd=repo_path)
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
    project_resource_group: str | None = None,
) -> Generator[str | AppServiceRelease, None, None]:
    """Publish to Terraform-provisioned App Service without changing Azure RBAC."""
    app_name = normalize_app_name(app_name)
    resource_group = project_resource_group or str(connection.resource_group)
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
        try:
            principal_id = _capture([
                "az", "webapp", "show", "--name", app_name,
                "--resource-group", resource_group,
                "--query", "identity.principalId", "--output", "tsv",
            ], env=env)
        except AzureDeploymentError as error:
            raise AzureDeploymentError(
                "The approved Terraform apply has not provisioned this application site. "
                "Apply the exact saved plan before publishing a release."
            ) from error
        registry_id = _capture([
            "az", "acr", "show", "--name", _registry_name(registry_server), "--query", "id", "--output", "tsv",
        ], env=env)
        if not principal_id or not registry_id:
            raise AzureDeploymentError(
                "The Terraform-provisioned application identity or registry scope is unavailable."
            )
        try:
            assignment_id = _capture([
                "az", "role", "assignment", "list",
                "--assignee-object-id", principal_id,
                "--scope", registry_id,
                "--role", ACR_PULL_ROLE_ID,
                "--query", "[0].id", "--output", "tsv",
            ], env=env)
        except AzureDeploymentError as error:
            raise AzureDeploymentError(
                "Azure could not verify the Terraform-managed AcrPull assignment on the "
                "configured registry. Reconcile the exact saved plan before retrying."
            ) from error
        if not assignment_id:
            raise AzureDeploymentError(
                "The exact Terraform apply has not granted AcrPull to the application "
                "identity on the configured registry."
            )

        yield "Publishing your new version…"
        yield from _run([
            "az", "webapp", "config", "set", "--name", app_name, "--resource-group", resource_group,
            "--generic-configurations", "acrUseManagedIdentityCreds=true",
            "--acr-identity", "[system]",
            "--acr-use-identity", "true",
            "--output", "none",
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


def teardown_app_service(
    *,
    connection: Any,
    client_secret: str,
    app_name: str,
    resource_group: str,
) -> list[str]:
    """Delete the deployed Azure App Service web app.

    This is a best-effort teardown: it authenticates with the service principal
    and calls ``az webapp delete``. The caller is responsible for handling
    ``AzureDeploymentError`` — a failure here must not prevent the database
    record from being removed.

    The App Service Plan and ACR registry are NOT deleted; those are shared
    infrastructure managed at the connection level.
    """
    if not app_name or not str(app_name).strip():
        raise AzureDeploymentError("A valid application name is required to perform teardown.")
    if not resource_group or not str(resource_group).strip():
        raise AzureDeploymentError("A valid resource group is required to perform teardown.")
    safe_app_name = normalize_app_name(app_name)

    config_dir = tempfile.mkdtemp(prefix="zeroops-az-teardown-")
    messages: list[str] = []
    try:
        env = _azure_environment(connection, config_dir)
        _sign_in(connection, client_secret, env)

        # Check the web app exists before attempting deletion (avoids noisy errors)
        try:
            state = _capture([
                "az", "webapp", "show",
                "--name", safe_app_name,
                "--resource-group", resource_group,
                "--query", "state",
                "--output", "tsv",
            ], env=env).strip().lower()
        except AzureDeploymentError:
            # App already gone or RBAC issue — treat as success
            messages.append(f"App Service '{safe_app_name}' was not found in Azure; skipping deletion.")
            return messages

        if not state:
            messages.append(f"App Service '{safe_app_name}' not found; skipping deletion.")
            return messages

        messages.append(f"Deleting App Service '{safe_app_name}' from resource group '{resource_group}'…")
        list(_run([
            "az", "webapp", "delete",
            "--name", safe_app_name,
            "--resource-group", resource_group,
            "--output", "none",
        ], env=env))
        messages.append(f"App Service '{safe_app_name}' deleted successfully.")
        return messages
    finally:
        shutil.rmtree(config_dir, ignore_errors=True)


def teardown_project_resources(
    *,
    connection: Any,
    client_secret: str,
    project_id: Any,
    deployment_metadata_list: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Clean up all Azure resources created for this project.

    Performs complete cloud cleanup:
    1. Deletes all Azure App Service web apps created by the project's deployments.
    2. Deletes the project's dedicated resource group (``rg-zeroops-<project_id_hex>``).

    Shared tenant infrastructure (App Service Plan, ACR) is preserved.
    """
    if not project_id:
        raise AzureDeploymentError("A valid project ID is required to perform project teardown.")

    project_rg = f"rg-zeroops-{uuid.UUID(str(project_id)).hex}"
    config_dir = tempfile.mkdtemp(prefix="zeroops-az-proj-teardown-")
    messages: list[str] = []
    deleted_apps: list[str] = []
    deleted_rg: bool = False

    try:
        env = _azure_environment(connection, config_dir)
        _sign_in(connection, client_secret, env)

        # 1. Delete known App Services from deployment metadata
        apps_to_delete: set[tuple[str, str]] = set()
        if deployment_metadata_list:
            for meta in deployment_metadata_list:
                release_meta = meta.get("release", {}) or {}
                target_meta = meta.get("target", {}) or {}
                app_name = release_meta.get("application_name") or target_meta.get("application_name")
                rg = target_meta.get("resource_group") or meta.get("resource_group") or project_rg
                if app_name:
                    apps_to_delete.add((normalize_app_name(app_name), rg))

        for safe_app_name, rg in apps_to_delete:
            try:
                list(_run([
                    "az", "webapp", "delete",
                    "--name", safe_app_name,
                    "--resource-group", rg,
                    "--output", "none",
                ], env=env))
                messages.append(f"Deleted App Service '{safe_app_name}' from resource group '{rg}'.")
                deleted_apps.append(safe_app_name)
            except Exception as app_err:
                messages.append(f"App Service '{safe_app_name}' deletion status: {app_err}")

        # 2. Delete the dedicated project resource group
        try:
            rg_exists = _capture([
                "az", "group", "exists",
                "--name", project_rg,
                "--output", "tsv",
            ], env=env).strip().lower() == "true"

            if rg_exists:
                messages.append(f"Deleting project resource group '{project_rg}'…")
                list(_run([
                    "az", "group", "delete",
                    "--name", project_rg,
                    "--yes",
                    "--no-wait",
                ], env=env))
                messages.append(f"Project resource group '{project_rg}' deletion initiated.")
                deleted_rg = True
            else:
                messages.append(f"Project resource group '{project_rg}' does not exist; skipping.")
        except Exception as rg_err:
            messages.append(f"Project resource group '{project_rg}' teardown note: {rg_err}")

        return {
            "status": "success",
            "project_resource_group": project_rg,
            "deleted_apps": deleted_apps,
            "deleted_rg": deleted_rg,
            "messages": messages,
        }
    finally:
        shutil.rmtree(config_dir, ignore_errors=True)


def poll_app_service_metrics(
    *,
    connection: Any,
    client_secret: str,
    app_name: str,
    resource_group: str,
) -> dict[str, Any]:
    """Fetch current App Service runtime metrics from Azure Monitor.

    Returns a dict with keys: ``cpu_percent``, ``request_count``,
    ``http_error_rate_percent``, ``response_latency_ms``. Values may be
    ``None`` if not available (e.g. freshly deployed app with < 5 min data).

    Raises ``AzureDeploymentError`` if Azure CLI is unavailable or auth fails.
    """
    safe_app_name = normalize_app_name(app_name)
    config_dir = tempfile.mkdtemp(prefix="zeroops-az-metrics-")
    try:
        env = _azure_environment(connection, config_dir)
        _sign_in(connection, client_secret, env)

        # Build the resource ID for the web app
        subscription_id = str(getattr(connection, "subscription_id", "") or "").strip()
        resource_id = (
            f"/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Web/sites/{safe_app_name}"
        )

        def _fetch_metric(metric_name: str, aggregation: str = "Average") -> float | None:
            try:
                raw = _capture([
                    "az", "monitor", "metrics", "list",
                    "--resource", resource_id,
                    "--metric", metric_name,
                    "--interval", "PT5M",
                    "--aggregation", aggregation,
                    "--query", f"value[0].timeseries[0].data[-1].{aggregation.lower()}",
                    "--output", "tsv",
                ], env=env).strip()
                value = float(raw)
                return value if value >= 0 else None
            except (AzureDeploymentError, ValueError, TypeError):
                return None

        cpu = _fetch_metric("CpuPercentage", "Average")
        if cpu is not None:
            cpu = round(cpu, 2)

        requests_total_val = _fetch_metric("Requests", "Total")
        requests_total = int(requests_total_val) if requests_total_val is not None else None

        http_5xx_val = _fetch_metric("Http5xx", "Total")
        http_5xx = float(http_5xx_val) if http_5xx_val is not None else None

        error_rate: float | None = None
        if requests_total is not None and requests_total > 0 and http_5xx is not None:
            error_rate = round((http_5xx / requests_total) * 100, 2)
        elif requests_total == 0:
            error_rate = 0.0

        latency_raw = _fetch_metric("AverageResponseTime", "Average")
        # Azure returns AverageResponseTime in seconds; convert to ms
        latency = round(latency_raw * 1000, 1) if latency_raw is not None else None

        return {
            "cpu_percent": cpu,
            "request_count": requests_total,
            "http_error_rate_percent": error_rate,
            "response_latency_ms": latency,
        }
    finally:
        shutil.rmtree(config_dir, ignore_errors=True)



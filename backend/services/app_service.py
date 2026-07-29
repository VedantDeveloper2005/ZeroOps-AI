"""Azure App Service deployment helpers for customer applications.

The deployment worker builds a customer image in Azure Container Registry and
publishes it to an existing Linux App Service plan. A deployment is never marked
live from a constructed address: Azure must report the site running and its
public endpoint must answer first.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ACR_PULL_ROLE_ID = "7f951dda-4ed3-4680-a7ca-43fe172d538d"


class AzureDeploymentError(RuntimeError):
    """A user-safe error raised from an Azure deployment command."""


@dataclass(frozen=True)
class AppServiceRelease:
    app_name: str
    image_ref: str
    live_url: str
    revision: str


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
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as error:
        raise AzureDeploymentError("The deployment worker is missing the Azure CLI.") from error

    if process.stdout:
        for line in process.stdout:
            value = line.strip()
            if value:
                yield value
    if process.wait():
        raise AzureDeploymentError("Azure rejected the deployment request. Review the Azure deployment log.")


def _capture(command: list[str], *, env: dict[str, str], cwd: str | None = None) -> str:
    return "\n".join(_run(command, env=env, cwd=cwd)).strip()


def _azure_environment(connection: Any, client_secret: str, config_dir: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "AZURE_CONFIG_DIR": config_dir,
            "AZURE_CORE_ONLY_SHOW_ERRORS": "true",
            "AZURE_CLIENT_ID": str(connection.client_id),
            "AZURE_TENANT_ID": str(connection.tenant_id),
            "AZURE_CLIENT_SECRET": client_secret,
        }
    )
    return environment


def _sign_in(connection: Any, client_secret: str, env: dict[str, str]) -> None:
    list(_run([
        "az", "login", "--service-principal", "--username", str(connection.client_id),
        "--password", client_secret, "--tenant", str(connection.tenant_id), "--output", "none",
    ], env=env))
    list(_run(["az", "account", "set", "--subscription", str(connection.subscription_id)], env=env))


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
        env = _azure_environment(connection, client_secret, config_dir)
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


def _set_app_settings(
    *, app_name: str, resource_group: str, environment_variables: dict[str, tuple[str, bool]], port: str, env: dict[str, str]
) -> None:
    settings = [f"WEBSITES_PORT={port}"]
    for key, (value, _) in environment_variables.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise AzureDeploymentError(f"Environment variable name '{key}' is invalid for App Service.")
        settings.append(f"{key}={value}")
    # Azure CLI receives values only in this short-lived worker command. Output
    # is suppressed so neither secret nor non-secret settings enter release logs.
    list(_run([
        "az", "webapp", "config", "appsettings", "set", "--name", app_name,
        "--resource-group", resource_group, "--settings", *settings, "--output", "none",
    ], env=env))


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
        env = _azure_environment(connection, client_secret, config_dir)
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
        except AzureDeploymentError:
            # Assignment creation is idempotent from the release perspective.
            pass

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


def verify_public_endpoint(live_url: str, *, attempts: int = 12, delay_seconds: float = 5) -> None:
    """Require an HTTP response before treating an App Service release as live."""
    failure: Exception | None = None
    for _ in range(attempts):
        try:
            request = Request(live_url, method="HEAD", headers={"User-Agent": "ZeroOps release check"})
            with urlopen(request, timeout=15) as response:
                if response.status < 500:
                    return
        except HTTPError as error:
            if error.code < 500:
                return
            failure = error
        except (URLError, TimeoutError) as error:
            failure = error
        time.sleep(delay_seconds)
    raise AzureDeploymentError("The application did not become reachable after Azure reported it running.") from failure

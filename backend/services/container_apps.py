"""Azure Container Apps deployment helpers.

The helpers deliberately use Azure's managed build and app services.  A release is
never marked live from a constructed URL: Azure must report a ready revision and
the public endpoint must answer first.

This module is intended to run in the isolated deployment worker, not a web
request process.  The worker needs the Azure CLI with the ``containerapp``
extension installed and receives a customer's BYOS credential only for the
duration of one deployment.
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
PUBLIC_PLACEHOLDER_IMAGE = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"


class AzureDeploymentError(RuntimeError):
    """A user-safe error from an Azure deployment command."""


@dataclass(frozen=True)
class ContainerAppRelease:
    app_name: str
    image_ref: str
    live_url: str
    revision: str


def normalize_app_name(value: str) -> str:
    """Return an Azure Container App-compatible name (2-32 chars)."""
    raw = "".join(char.lower() if char.isalnum() else "-" for char in value)
    while "--" in raw:
        raw = raw.replace("--", "-")
    raw = raw.strip("-") or "app"
    raw = raw[:32].rstrip("-")
    if len(raw) < 2:
        raw = f"{raw}0"
    return raw


def _registry_name(login_server: str) -> str:
    name = str(login_server or "").strip().lower().split(".", 1)[0]
    if not name or not name.isalnum():
        raise AzureDeploymentError("The Azure container registry name is invalid.")
    return name


def _run(command: list[str], *, env: dict[str, str], cwd: str | None = None) -> Generator[str, None, None]:
    """Run a command without a shell and yield output without echoing credentials."""
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
    except FileNotFoundError as exc:
        raise AzureDeploymentError("The isolated deployment worker is missing the Azure CLI.") from exc

    if process.stdout:
        for line in process.stdout:
            text = line.strip()
            if text:
                yield text
    exit_code = process.wait()
    if exit_code:
        raise AzureDeploymentError("Azure rejected the deployment request. Review the deployment log for the Azure error.")


def _capture(command: list[str], *, env: dict[str, str], cwd: str | None = None) -> str:
    output = list(_run(command, env=env, cwd=cwd))
    return "\n".join(output).strip()


def _azure_environment(connection: Any, client_secret: str, config_dir: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "AZURE_CONFIG_DIR": config_dir,
            "AZURE_CORE_ONLY_SHOW_ERRORS": "true",
            "AZURE_EXTENSION_USE_DYNAMIC_INSTALL": "yes_without_prompt",
            "AZURE_CLIENT_ID": str(connection.client_id),
            "AZURE_TENANT_ID": str(connection.tenant_id),
            "AZURE_CLIENT_SECRET": client_secret,
        }
    )
    return environment


def _sign_in(connection: Any, client_secret: str, env: dict[str, str]) -> None:
    # The credential is passed only to this short-lived, isolated worker process
    # and is never yielded to the user-facing log stream.
    list(
        _run(
            [
                "az",
                "login",
                "--service-principal",
                "--username",
                str(connection.client_id),
                "--password",
                client_secret,
                "--tenant",
                str(connection.tenant_id),
                "--output",
                "none",
            ],
            env=env,
        )
    )
    list(
        _run(
            ["az", "account", "set", "--subscription", str(connection.subscription_id)],
            env=env,
        )
    )


def _port_for(metadata: dict[str, Any]) -> int:
    value = str(metadata.get("port") or "").strip()
    if value.isdigit() and 1 <= int(value) <= 65535:
        return int(value)
    return 8080 if metadata.get("framework") in {"FastAPI", "Flask"} else 3000


def _secret_ref_name(key: str) -> str:
    value = re.sub(r"[^0-9a-z-]", "-", key.lower()).strip("-")
    return (f"env-{value}" if value else "env-value")[:63].rstrip("-")


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
    *,
    connection: Any,
    client_secret: str,
    repo_path: str,
    image_ref: str,
    generated_dockerfile: str | None,
) -> Generator[str, None, None]:
    """Build in ACR so the control plane never requires Docker-in-Docker."""
    registry = _registry_name(str(connection.acr_login_server))
    try:
        repository_and_tag = image_ref.split("/", 1)[1]
    except IndexError as exc:
        raise AzureDeploymentError("The Azure image reference is invalid.") from exc

    config_dir = tempfile.mkdtemp(prefix="zeroops-az-")
    try:
        env = _azure_environment(connection, client_secret, config_dir)
        _sign_in(connection, client_secret, env)
        dockerfile = _dockerfile_for(repo_path, generated_dockerfile)
        yield "Building your application in Azure…"
        for line in _run(
            [
                "az",
                "acr",
                "build",
                "--registry",
                registry,
                "--image",
                repository_and_tag,
                "--file",
                dockerfile,
                repo_path,
                "--output",
                "none",
            ],
            env=env,
        ):
            yield line
        yield "Your application image is ready."
    finally:
        shutil.rmtree(config_dir, ignore_errors=True)


def deploy_image(
    *,
    connection: Any,
    client_secret: str,
    app_name: str,
    image_ref: str,
    metadata: dict[str, Any],
    environment_variables: dict[str, tuple[str, bool]] | None = None,
) -> Generator[str | ContainerAppRelease, None, None]:
    """Create or update a Container App and yield its Azure-verified public URL."""
    app_name = normalize_app_name(app_name)
    resource_group = str(connection.resource_group)
    environment_name = str(connection.container_apps_environment)
    registry_server = str(connection.acr_login_server).rstrip("/")
    config_dir = tempfile.mkdtemp(prefix="zeroops-az-")
    port = str(_port_for(metadata))

    try:
        env = _azure_environment(connection, client_secret, config_dir)
        _sign_in(connection, client_secret, env)
        show = ["az", "containerapp", "show", "--name", app_name, "--resource-group", resource_group, "--output", "none"]
        exists = True
        try:
            _capture(show, env=env)
        except AzureDeploymentError:
            exists = False

        if not exists:
            yield "Creating your managed application environment…"
            for line in _run(
                [
                    "az", "containerapp", "create", "--name", app_name,
                    "--resource-group", resource_group,
                    "--environment", environment_name,
                    "--image", PUBLIC_PLACEHOLDER_IMAGE,
                    "--ingress", "external",
                    "--target-port", port,
                    "--min-replicas", "0",
                    "--max-replicas", "2",
                    "--cpu", "0.25",
                    "--memory", "0.5Gi",
                    "--system-assigned",
                    "--output", "none",
                ],
                env=env,
            ):
                yield line

        principal_id = _capture(
            [
                "az", "containerapp", "show", "--name", app_name,
                "--resource-group", resource_group,
                "--query", "identity.principalId", "--output", "tsv",
            ],
            env=env,
        )
        registry_id = _capture(
            [
                "az", "acr", "show", "--name", _registry_name(registry_server),
                "--query", "id", "--output", "tsv",
            ],
            env=env,
        )
        if not principal_id or not registry_id:
            raise AzureDeploymentError("Azure could not configure image access for this application.")

        # Idempotent assignment: if it already exists, Azure CLI returns a non-zero
        # result. We leave the existing assignment in place and continue safely.
        role_command = [
            "az", "role", "assignment", "create", "--assignee-object-id", principal_id,
            "--assignee-principal-type", "ServicePrincipal", "--role", ACR_PULL_ROLE_ID,
            "--scope", registry_id, "--output", "none",
        ]
        try:
            _capture(role_command, env=env)
        except AzureDeploymentError:
            pass

        yield "Publishing your new version…"
        for line in _run(
            [
                "az", "containerapp", "registry", "set", "--name", app_name,
                "--resource-group", resource_group, "--server", registry_server,
                "--identity", "system", "--output", "none",
            ],
            env=env,
        ):
            yield line

        environment_variables = environment_variables or {}
        secret_values: list[str] = []
        environment_values: list[str] = []
        for key, (value, is_secret) in environment_variables.items():
            if is_secret:
                secret_name = _secret_ref_name(key)
                secret_values.append(f"{secret_name}={value}")
                environment_values.append(f"{key}=secretref:{secret_name}")
            else:
                environment_values.append(f"{key}={value}")

        if secret_values:
            # The short-lived deployment worker passes these values directly to
            # Azure without logging or writing them to deployment metadata.
            for line in _run(
                [
                    "az", "containerapp", "secret", "set", "--name", app_name,
                    "--resource-group", resource_group, "--secrets", *secret_values,
                    "--output", "none",
                ],
                env=env,
            ):
                yield line

        update_command = [
            "az", "containerapp", "update", "--name", app_name,
            "--resource-group", resource_group, "--image", image_ref,
            "--min-replicas", "0", "--max-replicas", "2",
        ]
        if environment_values:
            update_command.extend(["--set-env-vars", *environment_values])
        update_command.extend(["--output", "none"])
        for line in _run(
            update_command,
            env=env,
        ):
            yield line

        fqdn = _capture(
            [
                "az", "containerapp", "show", "--name", app_name,
                "--resource-group", resource_group,
                "--query", "properties.configuration.ingress.fqdn", "--output", "tsv",
            ],
            env=env,
        )
        revision = _capture(
            [
                "az", "containerapp", "show", "--name", app_name,
                "--resource-group", resource_group,
                "--query", "properties.latestReadyRevisionName", "--output", "tsv",
            ],
            env=env,
        )
        if not fqdn or not revision:
            raise AzureDeploymentError("Azure has not reported a ready version yet.")
        release = ContainerAppRelease(app_name, image_ref, f"https://{fqdn}", revision)
        yield release
    finally:
        shutil.rmtree(config_dir, ignore_errors=True)


def verify_public_endpoint(live_url: str, *, attempts: int = 12, delay_seconds: float = 5) -> None:
    """Require an actual HTTP response before treating a release as live."""
    failure: Exception | None = None
    for _ in range(attempts):
        try:
            request = Request(live_url, method="HEAD", headers={"User-Agent": "ZeroOps release check"})
            with urlopen(request, timeout=15) as response:
                if response.status < 500:
                    return
        except HTTPError as error:
            # A 4xx response proves that the application endpoint is reachable;
            # the app itself may intentionally not serve a root route.
            if error.code < 500:
                return
            failure = error
        except (URLError, TimeoutError) as error:
            failure = error
        time.sleep(delay_seconds)
    raise AzureDeploymentError("The application did not become reachable after Azure reported it ready.") from failure

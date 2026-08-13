from types import SimpleNamespace
from datetime import datetime
import json
from pathlib import Path

import pytest

try:
    from backend.services import app_service, deployment_targets
except ImportError:
    from services import app_service, deployment_targets


def azure_connection(**overrides):
    values = {
        "tenant_id": "tenant-id",
        "subscription_id": "subscription-id",
        "client_id": "client-id",
        "resource_group": "apps-rg",
        "acr_login_server": "zeroopsapps.azurecr.io",
        "app_service_plan": "customer-linux-plan",
        "aks_cluster_name": None,
        "region": "eastus",
        "namespace_prefix": "team-a",
        "connection_status": "connected",
        "is_active": True,
        "deployment_target_verified_at": datetime(2026, 1, 1),
    }
    values.update(overrides)
    connection = SimpleNamespace(**values)
    if "deployment_target_fingerprint" not in overrides:
        connection.deployment_target_fingerprint = (
            deployment_targets.configuration_fingerprint(connection)
        )
    return connection


def test_azure_target_requires_app_service_configuration():
    connection = azure_connection(app_service_plan="")

    status = deployment_targets.status_payload(connection)

    assert status["any_ready"] is False
    assert status["targets"][0]["provider"] == "azure-app-service"
    assert "Linux App Service plan" in status["targets"][0]["missing"]


def test_azure_target_selects_only_azure_app_service():
    target = deployment_targets.choose_target({}, azure_connection(), "auto")

    assert target.provider == "azure-app-service"
    assert deployment_targets.image_ref_for_target(target, "team-a-app", "v1") == "zeroopsapps.azurecr.io/team-a-app:v1"
    assert deployment_targets.metadata_for_target(target)["app_service_plan"] == "customer-linux-plan"


def test_nonempty_but_unverified_azure_target_is_not_ready():
    connection = azure_connection(
        deployment_target_fingerprint=None,
        deployment_target_verified_at=None,
    )

    status = deployment_targets.status_payload(connection)

    assert status["any_ready"] is False
    assert "Verified Azure deployment target" in status["targets"][0]["missing"]
    with pytest.raises(ValueError, match="Verified Azure deployment target"):
        deployment_targets.choose_target({}, connection, "auto")


def test_target_verification_is_invalidated_when_configuration_changes():
    connection = azure_connection()
    connection.app_service_plan = "an-unverified-plan"

    status = deployment_targets.status_payload(connection)

    assert status["any_ready"] is False
    assert "Verified Azure deployment target" in status["targets"][0]["missing"]


def test_aks_is_not_advertised_or_selected_before_external_verification_exists():
    connection = azure_connection(aks_cluster_name="existing-cluster")

    status = deployment_targets.status_payload(connection)
    aks_status = next(item for item in status["targets"] if item["provider"] == "azure-aks")
    assert aks_status["ready"] is False
    assert deployment_targets.AKS_RELEASE_BLOCKER in aks_status["missing"]

    with pytest.raises(ValueError, match="Hardened AKS Service/Ingress verification"):
        deployment_targets.choose_target(
            {"files_list": ["k8s/deployment.yaml", "k8s/service.yaml"]},
            connection,
            "auto",
        )

    with pytest.raises(ValueError, match="Hardened AKS Service/Ingress verification"):
        deployment_targets.choose_target(
            {"kubernetes_detected": True},
            connection,
            "aks",
        )


def test_aks_fails_closed_without_manifests_or_cluster():
    with pytest.raises(ValueError, match="validated Kubernetes"):
        deployment_targets.choose_target({}, azure_connection(aks_cluster_name="cluster"), "aks")

    with pytest.raises(ValueError, match="Existing AKS cluster"):
        deployment_targets.choose_target(
            {"kubernetes_detected": True},
            azure_connection(aks_cluster_name=""),
            "aks",
        )


def test_rejects_non_azure_deployment_targets():
    with pytest.raises(ValueError, match="Supported targets"):
        deployment_targets.choose_target({}, azure_connection(), "gke")


def test_app_settings_use_ephemeral_json_instead_of_secret_argv(tmp_path, monkeypatch):
    captured = {}

    def fake_run(command, *, env, cwd=None):
        captured["command"] = command
        settings_arg = command[command.index("--settings") + 1]
        assert settings_arg.startswith("@")
        settings_path = Path(settings_arg[1:])
        captured["path"] = settings_path
        captured["settings"] = json.loads(settings_path.read_text(encoding="utf-8"))
        return iter(())

    monkeypatch.setattr(app_service, "_run", fake_run)
    app_service._set_app_settings(
        app_name="example-app",
        resource_group="apps-rg",
        environment_variables={"API_TOKEN": ("top-secret-value", True)},
        port="3000",
        env={"AZURE_CONFIG_DIR": str(tmp_path)},
    )

    assert "top-secret-value" not in " ".join(captured["command"])
    assert captured["settings"] == {"WEBSITES_PORT": "3000", "API_TOKEN": "top-secret-value"}
    assert not captured["path"].exists()


def test_app_service_fails_fast_when_acr_pull_assignment_is_rejected(monkeypatch):
    commands = []

    monkeypatch.setattr(app_service, "_sign_in", lambda *_args, **_kwargs: None)

    def fake_capture(command, *, env, cwd=None):
        commands.append(command)
        if command[:3] == ["az", "webapp", "show"]:
            return ""
        if command[:4] == ["az", "webapp", "identity", "assign"]:
            return "web-app-principal-id"
        if command[:3] == ["az", "acr", "show"]:
            return "/subscriptions/subscription-id/resourceGroups/apps-rg/providers/Microsoft.ContainerRegistry/registries/zeroopsapps"
        if command[:4] == ["az", "role", "assignment", "create"]:
            raise app_service.AzureDeploymentError("provider response must stay hidden")
        raise AssertionError(f"Unexpected Azure command: {command}")

    monkeypatch.setattr(app_service, "_capture", fake_capture)

    with pytest.raises(app_service.AzureDeploymentError) as raised:
        list(
            app_service.deploy_image(
                connection=azure_connection(),
                client_secret="secret",
                app_name="example-app",
                image_ref="zeroopsapps.azurecr.io/example-app:release",
                metadata={"framework": "FastAPI", "port": "8000"},
            )
        )

    assert "grant AcrPull" in str(raised.value)
    assert "role-assignment permission" in str(raised.value)
    assert "provider response" not in str(raised.value)
    role_command = next(
        command
        for command in commands
        if command[:4] == ["az", "role", "assignment", "create"]
    )
    assert app_service.ACR_PULL_ROLE_ID in role_command


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Team A / My App", "team-a-my-app"),
        ("__", "app"),
        ("A" * 40, "a" * 40),
    ],
)
def test_app_service_name_normalization(value, expected):
    assert app_service.normalize_app_name(value) == expected

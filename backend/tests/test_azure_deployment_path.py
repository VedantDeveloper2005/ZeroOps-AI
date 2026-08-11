from types import SimpleNamespace
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
    }
    values.update(overrides)
    return SimpleNamespace(**values)


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

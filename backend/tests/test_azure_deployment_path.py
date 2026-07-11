from types import SimpleNamespace

import pytest

try:
    from backend.services import container_apps, deployment_targets
except ImportError:
    from services import container_apps, deployment_targets


def azure_connection(**overrides):
    values = {
        "tenant_id": "tenant-id",
        "subscription_id": "subscription-id",
        "client_id": "client-id",
        "resource_group": "apps-rg",
        "acr_login_server": "zeroopsapps.azurecr.io",
        "container_apps_environment": "customer-apps",
        "region": "eastus",
        "namespace_prefix": "team-a",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_azure_target_requires_container_apps_configuration():
    connection = azure_connection(container_apps_environment="")

    status = deployment_targets.status_payload(connection)

    assert status["any_ready"] is False
    assert status["targets"][0]["provider"] == "azure-container-apps"
    assert "Application environment" in status["targets"][0]["missing"]


def test_azure_target_selects_only_azure_container_apps():
    target = deployment_targets.choose_target({}, azure_connection(), "auto")

    assert target.provider == "azure-container-apps"
    assert deployment_targets.image_ref_for_target(target, "team-a-app", "v1") == "zeroopsapps.azurecr.io/team-a-app:v1"
    assert deployment_targets.metadata_for_target(target)["container_apps_environment"] == "customer-apps"


def test_rejects_non_azure_deployment_targets():
    with pytest.raises(ValueError, match="Only Azure"):
        deployment_targets.choose_target({}, azure_connection(), "gke")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Team A / My App", "team-a-my-app"),
        ("__", "app"),
        ("A" * 40, "a" * 32),
    ],
)
def test_container_app_name_normalization(value, expected):
    assert container_apps.normalize_app_name(value) == expected

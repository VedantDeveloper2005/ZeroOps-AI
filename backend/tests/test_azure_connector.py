from types import SimpleNamespace

import pytest

from backend.services import azure_connector


SUBSCRIPTION_ID = "00000000-1111-2222-3333-444444444444"
RESOURCE_GROUP = "apps-rg"
ACR_LOGIN_SERVER = "zeroopsapps.azurecr.io"
APP_SERVICE_PLAN = "zeroops-linux-plan"


def _resource_id(provider: str, resource_type: str, name: str) -> str:
    return (
        f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/{provider}/{resource_type}/{name}"
    )


def _registry(*, login_server: str = ACR_LOGIN_SERVER, state: str = "Succeeded"):
    return SimpleNamespace(
        id=_resource_id(
            "Microsoft.ContainerRegistry",
            "registries",
            "zeroopsapps",
        ),
        type="Microsoft.ContainerRegistry/registries",
        # ACR does not have to be in the App Service plan region.
        location="westus2",
        properties={
            "loginServer": login_server,
            "provisioningState": state,
        },
    )


def _plan(
    *,
    reserved: bool = True,
    location: str = "East US",
    state: str = "Succeeded",
):
    return SimpleNamespace(
        id=_resource_id("Microsoft.Web", "serverfarms", APP_SERVICE_PLAN),
        type="Microsoft.Web/serverfarms",
        location=location,
        # Exercise the Azure SDK object's attribute-style shape as well as the
        # mapping shape used by GenericResource.properties.
        properties=SimpleNamespace(
            reserved=reserved,
            provisioningState=state,
            status="Ready",
        ),
    )


def _install_azure_sdk_mocks(monkeypatch, *, registry=None, plan=None, error=None):
    registry = registry or _registry()
    plan = plan or _plan()
    calls = {"credential": None, "subscription": None, "group": [], "resources": []}

    class ResourceGroups:
        def get(self, resource_group):
            calls["group"].append(resource_group)
            return SimpleNamespace(name=resource_group)

    class Resources:
        def get_by_id(self, resource_id, api_version):
            calls["resources"].append((resource_id, api_version))
            if error is not None:
                raise error
            if "/Microsoft.ContainerRegistry/registries/" in resource_id:
                return registry
            return plan

    class ResourceClient:
        def __init__(self, _credential, subscription_id):
            calls["subscription"] = subscription_id
            self.resource_groups = ResourceGroups()
            self.resources = Resources()

    def credential_factory(**kwargs):
        calls["credential"] = kwargs
        return object()

    monkeypatch.setattr(azure_connector, "ClientSecretCredential", credential_factory)
    monkeypatch.setattr(azure_connector, "ResourceManagementClient", ResourceClient)
    return calls


def _validate(**overrides):
    values = {
        "tenant_id": "tenant-id",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "subscription_id": SUBSCRIPTION_ID,
        "resource_group": RESOURCE_GROUP,
        "acr_login_server": ACR_LOGIN_SERVER,
        "app_service_plan": APP_SERVICE_PLAN,
        "region": "eastus",
    }
    values.update(overrides)
    return azure_connector.validate_credential(**values)


def test_validation_reads_exact_acr_and_linux_plan_and_allows_cross_region_acr(monkeypatch):
    calls = _install_azure_sdk_mocks(monkeypatch)

    result = _validate()

    assert result["success"] is True
    assert calls["group"] == [RESOURCE_GROUP]
    assert calls["resources"] == [
        (
            _resource_id(
                "Microsoft.ContainerRegistry",
                "registries",
                "zeroopsapps",
            ),
            azure_connector.ACR_RESOURCE_API_VERSION,
        ),
        (
            _resource_id("Microsoft.Web", "serverfarms", APP_SERVICE_PLAN),
            azure_connector.APP_SERVICE_PLAN_API_VERSION,
        ),
    ]
    assert calls["subscription"] == SUBSCRIPTION_ID


def test_validation_rejects_windows_app_service_plan(monkeypatch):
    _install_azure_sdk_mocks(monkeypatch, plan=_plan(reserved=False))

    result = _validate()

    assert result == {
        "success": False,
        "error": "The configured App Service plan is not a Linux plan.",
    }


def test_validation_rejects_plan_outside_configured_region(monkeypatch):
    _install_azure_sdk_mocks(monkeypatch, plan=_plan(location="centralus"))

    result = _validate()

    assert result["success"] is False
    assert "must match the configured Azure region" in result["error"]


def test_validation_rejects_acr_login_server_mismatch(monkeypatch):
    _install_azure_sdk_mocks(
        monkeypatch,
        registry=_registry(login_server="anotherregistry.azurecr.io"),
    )

    result = _validate()

    assert result["success"] is False
    assert "does not match the Azure resource" in result["error"]


def test_validation_rejects_plan_returned_from_another_resource_group(monkeypatch):
    plan = _plan()
    plan.id = plan.id.replace(
        f"/resourceGroups/{RESOURCE_GROUP}/",
        "/resourceGroups/another-rg/",
    )
    _install_azure_sdk_mocks(monkeypatch, plan=plan)

    result = _validate()

    assert result["success"] is False
    assert "does not match the configured resource group" in result["error"]


def test_validation_fails_closed_without_target_fields(monkeypatch):
    def unexpected_client(*_args, **_kwargs):
        pytest.fail("Azure SDK should not be called for incomplete target settings")

    monkeypatch.setattr(azure_connector, "ClientSecretCredential", unexpected_client)

    result = _validate(acr_login_server="")

    assert result["success"] is False
    assert "container registry" in result["error"]


def test_validation_redacts_provider_error_and_client_secret(monkeypatch, caplog):
    client_secret = "do-not-expose-this-secret"
    _install_azure_sdk_mocks(
        monkeypatch,
        error=RuntimeError(f"provider details included {client_secret}"),
    )

    result = _validate(client_secret=client_secret)

    assert result["success"] is False
    assert client_secret not in result["error"]
    assert client_secret not in caplog.text
    assert "provider details" not in caplog.text

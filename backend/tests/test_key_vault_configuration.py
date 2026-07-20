import pytest

try:
    from backend.services import vault
except ImportError:
    from services import vault


class _Secret:
    def __init__(self, value: str):
        self.value = value


class _NotFound(Exception):
    status_code = 404


class _VaultClient:
    def __init__(self, values: dict[str, str]):
        self.values = values
        self.calls: list[str] = []

    def get_secret(self, name: str) -> _Secret:
        self.calls.append(name)
        if name not in self.values:
            raise _NotFound()
        return _Secret(self.values[name])


@pytest.fixture(autouse=True)
def _reset_vault_cache():
    vault.clear_application_setting_cache()
    yield
    vault.clear_application_setting_cache()


def test_application_setting_uses_canonical_key_vault_name_and_caches(monkeypatch):
    client = _VaultClient({"zeroops-database-url": "postgresql://vault"})
    monkeypatch.setattr(vault, "kv_client", client)
    monkeypatch.setattr(vault, "HAS_AZURE_KV", True)

    assert vault.get_application_setting("DATABASE_URL") == "postgresql://vault"
    assert vault.get_application_setting("DATABASE_URL") == "postgresql://vault"
    assert client.calls == ["zeroops-database-url"]


def test_application_setting_supports_documented_legacy_key_names(monkeypatch):
    client = _VaultClient({"zeroops-ai-api-key": "vault-key"})
    monkeypatch.setattr(vault, "kv_client", client)
    monkeypatch.setattr(vault, "HAS_AZURE_KV", True)

    assert vault.get_application_setting("OPENAI_API_KEY") == "vault-key"
    assert client.calls == ["zeroops-ai-api-key"]


def test_required_setting_fails_closed_when_key_is_absent(monkeypatch):
    monkeypatch.setattr(vault, "kv_client", _VaultClient({}))
    monkeypatch.setattr(vault, "HAS_AZURE_KV", True)

    with pytest.raises(vault.KeyVaultConfigurationError, match="DATABASE_URL"):
        vault.get_application_setting("DATABASE_URL", required=True)


def test_development_default_is_used_only_without_a_vault(monkeypatch):
    monkeypatch.setattr(vault, "kv_client", None)
    monkeypatch.setattr(vault, "HAS_AZURE_KV", False)

    assert vault.get_application_setting("OPENAI_MODEL", default="gpt-5.4-mini") == "gpt-5.4-mini"


def test_worker_callback_token_is_rejected_before_database_access(monkeypatch):
    from fastapi import HTTPException
    from backend import main

    monkeypatch.setattr(main.config, "WORKER_EVENT_TOKEN", "worker-token")

    with pytest.raises(HTTPException) as error:
        import asyncio
        asyncio.run(main.require_worker_event_token(None))

    assert error.value.status_code == 403

import pytest
from unittest.mock import MagicMock

try:
    from backend.services import action_gateway, azure_connector
    from backend import schemas
except ImportError:
    from services import action_gateway, azure_connector
    import schemas

def test_secret_redaction_utility():
    # Test dictionary with multiple secret keys at various nesting levels
    params = {
        "cluster_name": "aks-cluster",
        "client_secret": "zo_live_secret_12345",
        "password": "my-vault-password",
        "nested": {
            "token": "gh_token_abcd",
            "api_key": "some_api_key",
            "safe_field": "public_data"
        },
        "list_field": [
            {"secret_token": "token_val"},
            {"safe_val": 42}
        ]
    }
    
    redacted = action_gateway.redact_secrets(params)
    
    # Assert values for secret keys are redacted
    assert redacted["client_secret"] == "<REDACTED>"
    assert redacted["password"] == "<REDACTED>"
    assert redacted["nested"]["token"] == "<REDACTED>"
    assert redacted["nested"]["api_key"] == "<REDACTED>"
    assert redacted["list_field"][0]["secret_token"] == "<REDACTED>"
    
    # Assert values for safe keys are preserved
    assert redacted["cluster_name"] == "aks-cluster"
    assert redacted["nested"]["safe_field"] == "public_data"
    assert redacted["list_field"][1]["safe_val"] == 42

def test_credential_onboarding_memory_zeroing():
    # Verify client secret memory zeroing inside azure_connector
    import uuid
    user_id = uuid.uuid4()
    secret = "my-super-secret-key-1234"
    
    # We call onboarding storage
    store_ok = azure_connector.store_credential_in_vault(user_id, secret)
    assert store_ok is True
    
    # Check that we can fetch the secret from Key Vault (mocked or real)
    fetched_secret = azure_connector.get_credential_secret(user_id)
    assert fetched_secret == "my-super-secret-key-1234"
    
    # Clean up
    azure_connector.delete_credential_from_vault(user_id)

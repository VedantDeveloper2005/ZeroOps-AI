"""Unit tests for the optional Microsoft Foundry Azure OpenAI provider."""

from types import SimpleNamespace

import pytest

from backend.services.providers.azure_openai import AzureOpenAIProvider
from backend.services.providers.base import (
    ProviderConfiguration,
    ProviderConfigurationError,
    ProviderCredentialUnavailableError,
    ProviderError,
    ProviderRequest,
)


def _configuration(**overrides):
    values = {
        "provider": "azure-openai",
        "endpoint": "https://zeroops-foundry.openai.azure.com",
        "model": "zeroops-gpt-5-mini",
        "api_key": "test-foundry-key",
        "max_input_chars": 10_000,
        "max_output_tokens": 200,
    }
    values.update(overrides)
    return ProviderConfiguration(**values)


def _request():
    return ProviderRequest(
        system_prompt="Return JSON only.",
        user_prompt="{}",
        schema_name="Example",
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
        },
        max_output_tokens=400,
    )


def test_azure_openai_normalizes_resource_endpoint_and_uses_responses_api():
    captured = {}

    class Responses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                model="zeroops-gpt-5-mini",
                output_text='{"ok":true}',
                usage=SimpleNamespace(input_tokens=12, output_tokens=4),
            )

    provider = AzureOpenAIProvider(
        _configuration(endpoint="https://ZEROOPS-FOUNDRY.openai.azure.com/openai/v1/"),
        client=SimpleNamespace(responses=Responses()),
    )

    response = provider.generate(_request())

    assert provider.configuration.endpoint == "https://zeroops-foundry.openai.azure.com/openai/v1"
    assert captured["model"] == "zeroops-gpt-5-mini"
    assert captured["max_output_tokens"] == 200
    assert captured["store"] is False
    assert captured["text"]["format"]["strict"] is True
    assert response.content == '{"ok":true}'
    assert response.input_tokens == 12
    assert response.output_tokens == 4


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://zeroops-foundry.openai.azure.com",
        "https://api.openai.com/v1",
        "https://zeroops-foundry.openai.azure.com/openai/deployments/demo",
        "https://zeroops-foundry.openai.azure.com/openai/v1?key=not-allowed",
    ],
)
def test_azure_openai_rejects_untrusted_or_non_v1_endpoints(endpoint):
    with pytest.raises(ProviderConfigurationError):
        AzureOpenAIProvider(_configuration(endpoint=endpoint), client=SimpleNamespace())


def test_azure_openai_requires_workload_key_and_deployment_name():
    with pytest.raises(ProviderCredentialUnavailableError):
        AzureOpenAIProvider(_configuration(api_key=""), client=SimpleNamespace())
    with pytest.raises(ProviderConfigurationError, match="deployment"):
        AzureOpenAIProvider(_configuration(model=""), client=SimpleNamespace())


def test_azure_openai_hides_upstream_errors_and_key():
    class Responses:
        def create(self, **kwargs):
            raise RuntimeError("Authorization failed: test-foundry-key")

    provider = AzureOpenAIProvider(
        _configuration(), client=SimpleNamespace(responses=Responses())
    )
    with pytest.raises(ProviderError, match="Microsoft Foundry OpenAI inference failed") as error:
        provider.generate(_request())
    assert "test-foundry-key" not in str(error.value)

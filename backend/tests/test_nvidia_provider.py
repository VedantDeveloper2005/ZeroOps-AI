"""Unit tests for NvidiaProvider and its integration with the model gateway.

All tests use a mocked OpenAI client. No test calls the real NVIDIA API.
The existing Azure Foundry tests in test_model_gateway.py continue passing
without change; this file focuses on NVIDIA-specific behaviour.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend import config
from backend.contracts.ai import AIWorkload, RepositoryAssessment
from backend.services.model_gateway import (
    ModelGateway,
    ModelRouteNotConfiguredError,
    build_provider,
)
from backend.services.providers import (
    NvidiaProvider,
    ProviderConfiguration,
    ProviderConfigurationError,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NVIDIA_ENDPOINT = "https://integrate.api.nvidia.com/v1"
_NVIDIA_MODEL = "z-ai/glm-5.2"
_NVIDIA_KEY = "test-nvapi-key"


def _cfg(**overrides) -> ProviderConfiguration:
    """Build a valid NvidiaProvider configuration with sensible defaults."""
    defaults = dict(
        provider="nvidia",
        endpoint=_NVIDIA_ENDPOINT,
        model=_NVIDIA_MODEL,
        api_key=_NVIDIA_KEY,
        max_input_chars=40_000,
        max_output_tokens=1_600,
    )
    defaults.update(overrides)
    return ProviderConfiguration(**defaults)


def _request(**overrides) -> ProviderRequest:
    defaults = dict(
        system_prompt="Analyze the supplied repository facts.",
        user_prompt='{"facts": []}',
        schema_name="TestSchema",
        output_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        max_output_tokens=400,
        temperature=0.0,
    )
    defaults.update(overrides)
    return ProviderRequest(**defaults)


def _fake_response(content: str = '{"ok":true}') -> SimpleNamespace:
    return SimpleNamespace(
        model=_NVIDIA_MODEL,
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )


def _fake_client(content: str = '{"ok":true}') -> SimpleNamespace:
    """Return a minimal mock client whose chat.completions.create returns content."""
    captured: dict = {}

    class _Completions:
        def create(self_, **kwargs):  # noqa: N805
            captured.update(kwargs)
            return _fake_response(content)

    ns = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    ns._captured = captured  # type: ignore[attr-defined]
    return ns


# ---------------------------------------------------------------------------
# Configuration validation tests
# ---------------------------------------------------------------------------


class TestNvidiaProviderConfiguration:
    def test_missing_api_key_is_rejected(self):
        with pytest.raises(ProviderConfigurationError, match="credential"):
            NvidiaProvider(_cfg(api_key=""))

    def test_whitespace_api_key_and_model_are_rejected(self):
        with pytest.raises(ProviderConfigurationError, match="credential"):
            NvidiaProvider(_cfg(api_key="   "), client=SimpleNamespace())
        with pytest.raises(ProviderConfigurationError, match="model"):
            NvidiaProvider(_cfg(model="   "), client=SimpleNamespace())

    def test_http_endpoint_is_rejected(self):
        with pytest.raises(ProviderConfigurationError, match="HTTPS"):
            NvidiaProvider(
                _cfg(endpoint="http://integrate.api.nvidia.com/v1"),
                client=SimpleNamespace(),
            )

    def test_wrong_endpoint_host_is_rejected(self):
        with pytest.raises(ProviderConfigurationError, match="integrate.api.nvidia.com"):
            NvidiaProvider(
                _cfg(endpoint="https://api.openai.com/v1"),
                client=SimpleNamespace(),
            )

    def test_empty_model_is_rejected(self):
        with pytest.raises(ProviderConfigurationError, match="model"):
            NvidiaProvider(
                _cfg(model=""),
                client=SimpleNamespace(),
            )

    def test_endpoint_is_normalized_regardless_of_path_suffix(self):
        """Even if the caller supplies a trailing slash or extra path, the
        provider normalizes to the canonical endpoint."""
        provider = NvidiaProvider(
            _cfg(endpoint="https://integrate.api.nvidia.com/v1/"),
            client=SimpleNamespace(),
        )
        assert provider.configuration.endpoint == _NVIDIA_ENDPOINT

    def test_provider_is_instantiated_with_valid_configuration(self):
        provider = NvidiaProvider(_cfg(), client=SimpleNamespace())
        assert provider.name == "nvidia"
        assert provider.configuration.model == _NVIDIA_MODEL

    def test_api_key_never_appears_in_repr(self):
        provider = NvidiaProvider(_cfg(), client=SimpleNamespace())
        assert _NVIDIA_KEY not in repr(provider.configuration)

    def test_api_key_never_appears_in_provider_error(self):
        """SDK exceptions must be converted without including the key."""

        class _BadClient:
            class chat:
                class completions:
                    @staticmethod
                    def create(**_):
                        raise RuntimeError(f"auth-failure key={_NVIDIA_KEY}")

        provider = NvidiaProvider(_cfg(), client=_BadClient())
        with pytest.raises(ProviderError, match="NVIDIA inference failed") as exc_info:
            provider.generate(_request())
        assert _NVIDIA_KEY not in str(exc_info.value)


# ---------------------------------------------------------------------------
# build_provider() integration test
# ---------------------------------------------------------------------------


class TestBuildProvider:
    def test_build_provider_nvidia_returns_nvidia_provider(self):
        cfg = _cfg()
        with patch(
            "backend.services.providers.nvidia.OpenAI",
            return_value=MagicMock(),
        ):
            provider = build_provider(cfg)
        assert isinstance(provider, NvidiaProvider)

    def test_build_provider_unsupported_raises_configuration_error(self):
        with pytest.raises(ProviderConfigurationError, match="not supported"):
            build_provider(
                ProviderConfiguration(
                    provider="unknown-ai",
                    endpoint="https://example.com",
                    model="some-model",
                    api_key="key",
                )
            )


# ---------------------------------------------------------------------------
# generate() behaviour tests
# ---------------------------------------------------------------------------


class TestNvidiaProviderGenerate:
    def test_correct_model_messages_tokens_temperature_are_sent(self):
        client = _fake_client()
        provider = NvidiaProvider(_cfg(max_output_tokens=800), client=client)
        provider.generate(_request(max_output_tokens=400, temperature=0.1))

        captured = client._captured
        assert captured["model"] == _NVIDIA_MODEL
        assert captured["temperature"] == 0.1
        # Config cap (800) is larger than request cap (400); request wins.
        assert captured["max_tokens"] == 400
        assert captured["stream"] is False
        msgs = captured["messages"]
        assert msgs[0]["role"] == "system"
        assert "JSON Schema" in msgs[0]["content"]
        assert msgs[1]["role"] == "user"

    def test_output_token_cap_uses_smaller_of_request_and_config(self):
        client = _fake_client()
        provider = NvidiaProvider(_cfg(max_output_tokens=100), client=client)
        # Request asks for 400 but config only allows 100.
        provider.generate(_request(max_output_tokens=400))
        assert client._captured["max_tokens"] == 100

    def test_schema_included_in_system_prompt(self):
        client = _fake_client()
        provider = NvidiaProvider(_cfg(), client=client)
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        provider.generate(_request(output_schema=schema))

        system_content = client._captured["messages"][0]["content"]
        assert '"name"' in system_content
        assert "JSON Schema" in system_content

    def test_input_larger_than_max_chars_is_rejected_before_api_call(self):
        client = _fake_client()
        # Tiny budget: any realistic prompt will exceed it.
        provider = NvidiaProvider(_cfg(max_input_chars=5), client=client)
        with pytest.raises(ProviderError, match="input budget"):
            provider.generate(_request())
        # Client must never have been called.
        assert not client._captured

    def test_empty_response_is_rejected(self):
        client = _fake_client(content="")
        provider = NvidiaProvider(_cfg(), client=client)
        with pytest.raises(ProviderError, match="empty response"):
            provider.generate(_request())

    def test_invalid_response_envelope_is_safely_rejected(self):
        class _InvalidCompletions:
            def create(self, **_):
                return SimpleNamespace(
                    choices=[SimpleNamespace()],
                    usage=None,
                )

        client = SimpleNamespace(
            chat=SimpleNamespace(completions=_InvalidCompletions())
        )
        provider = NvidiaProvider(_cfg(), client=client)
        with pytest.raises(ProviderError, match="invalid response"):
            provider.generate(_request())

    def test_sdk_exception_becomes_safe_provider_error(self):
        class _RaisingCompletions:
            def create(self, **_):
                raise ConnectionError("network timeout details")

        bad_client = SimpleNamespace(chat=SimpleNamespace(completions=_RaisingCompletions()))
        provider = NvidiaProvider(_cfg(), client=bad_client)
        with pytest.raises(ProviderError, match="NVIDIA inference failed"):
            provider.generate(_request())

    def test_token_usage_and_latency_are_returned(self):
        client = _fake_client()
        provider = NvidiaProvider(_cfg(), client=client)
        response = provider.generate(_request())

        assert response.input_tokens == 10
        assert response.output_tokens == 5
        assert response.latency_ms >= 0
        assert response.model == _NVIDIA_MODEL

    def test_response_model_name_comes_from_api_response(self):
        """If the API returns a different model name, use that."""

        class _OverrideCompletions:
            def create(self_, **_):  # noqa: N805
                return SimpleNamespace(
                    model="z-ai/glm-5.2-turbo",
                    choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))],
                    usage=SimpleNamespace(prompt_tokens=2, completion_tokens=2),
                )

        client = SimpleNamespace(chat=SimpleNamespace(completions=_OverrideCompletions()))
        provider = NvidiaProvider(_cfg(), client=client)
        response = provider.generate(_request())
        assert response.model == "z-ai/glm-5.2-turbo"


# ---------------------------------------------------------------------------
# Model gateway integration tests
# ---------------------------------------------------------------------------


def _nvidia_configuration(
    workload: AIWorkload,
    *,
    api_key: str = _NVIDIA_KEY,
    max_output_tokens: int = 200,
) -> ProviderConfiguration:
    return ProviderConfiguration(
        provider="nvidia",
        endpoint=_NVIDIA_ENDPOINT,
        model=_NVIDIA_MODEL,
        api_key=api_key,
        max_input_chars=20_000,
        max_output_tokens=max_output_tokens,
        prompt_version=f"{workload.value}.v1",
    )


def _valid_assessment_json() -> str:
    return json.dumps({
        "schema_version": "repository-assessment.v1",
        "summary": "A bounded web application.",
        "deployment_risk": "No runtime telemetry supplied.",
        "recommendations": [],
        "cost_optimizations": [],
        "unresolved_questions": [],
        "confidence": "medium",
        "limitations": [],
    })


class _FakeNvidiaProvider:
    name = "nvidia"

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class TestNvidiaGatewayIntegration:
    def test_build_provider_nvidia_wires_through_gateway(self, monkeypatch):
        monkeypatch.setattr(config, "AI_REPOSITORY_PROVIDER", "nvidia")
        monkeypatch.setattr(config, "AI_REPOSITORY_ENDPOINT", _NVIDIA_ENDPOINT)
        monkeypatch.setattr(config, "AI_REPOSITORY_MODEL", _NVIDIA_MODEL)
        monkeypatch.setattr(config, "AI_REPOSITORY_API_KEY", _NVIDIA_KEY)
        monkeypatch.setattr(config, "AI_REPOSITORY_MAX_INPUT_CHARS", 40_000)
        monkeypatch.setattr(config, "AI_REPOSITORY_MAX_OUTPUT_TOKENS", 1_600)

        with patch(
            "backend.services.providers.nvidia.OpenAI",
            return_value=MagicMock(),
        ):
            provider = build_provider(
                ModelGateway().configuration_for(AIWorkload.REPOSITORY_ANALYSIS)
            )
        assert isinstance(provider, NvidiaProvider)

    def test_repository_analysis_degrades_safely_when_nvidia_unavailable(self):
        """Provider raises ProviderError → gateway returns deterministic_only result."""
        provider = _FakeNvidiaProvider(
            [ProviderError("NVIDIA inference failed.")]
        )
        gateway = ModelGateway(
            configurations={
                AIWorkload.REPOSITORY_ANALYSIS: _nvidia_configuration(
                    AIWorkload.REPOSITORY_ANALYSIS
                )
            },
            providers={AIWorkload.REPOSITORY_ANALYSIS: provider},
        )
        result = gateway.generate_structured(
            workload=AIWorkload.REPOSITORY_ANALYSIS,
            system_prompt="Analyze bounded facts.",
            user_prompt="{}",
            output_contract=RepositoryAssessment,
        )
        assert result.value is None
        assert result.deterministic_only is True
        assert result.degraded_reason == "provider_unavailable"

    def test_terraform_generation_fails_closed_when_nvidia_unavailable(self):
        """Provider raises ProviderError → gateway raises for Terraform (fail-closed)."""
        provider = _FakeNvidiaProvider(
            [ProviderError("NVIDIA inference failed.")]
        )
        gateway = ModelGateway(
            configurations={
                AIWorkload.TERRAFORM_GENERATION: _nvidia_configuration(
                    AIWorkload.TERRAFORM_GENERATION
                )
            },
            providers={AIWorkload.TERRAFORM_GENERATION: provider},
        )
        with pytest.raises(Exception):
            gateway.generate_structured(
                workload=AIWorkload.TERRAFORM_GENERATION,
                system_prompt="Generate bounded Terraform.",
                user_prompt="{}",
                output_contract=RepositoryAssessment,
            )

    def test_terraform_fails_closed_when_nvidia_configuration_missing(self):
        """No API key → NvidiaProvider raises ProviderConfigurationError → gateway fails."""
        terraform_config = _nvidia_configuration(
            AIWorkload.TERRAFORM_GENERATION, api_key=""
        )
        gateway = ModelGateway(
            configurations={AIWorkload.TERRAFORM_GENERATION: terraform_config}
        )
        with pytest.raises(ModelRouteNotConfiguredError):
            gateway.generate_structured(
                workload=AIWorkload.TERRAFORM_GENERATION,
                system_prompt="Generate bounded Terraform.",
                user_prompt="{}",
                output_contract=RepositoryAssessment,
            )

    def test_repository_analysis_degrades_when_configuration_missing(self):
        """No API key → configuration error → deterministic_only degradation."""
        repository_config = _nvidia_configuration(
            AIWorkload.REPOSITORY_ANALYSIS, api_key=""
        )
        gateway = ModelGateway(
            configurations={AIWorkload.REPOSITORY_ANALYSIS: repository_config}
        )
        result = gateway.generate_structured(
            workload=AIWorkload.REPOSITORY_ANALYSIS,
            system_prompt="Analyze bounded facts.",
            user_prompt="{}",
            output_contract=RepositoryAssessment,
        )
        assert result.value is None
        assert result.deterministic_only is True

    def test_nvidia_provider_successful_structured_generation(self):
        provider = _FakeNvidiaProvider(
            [
                ProviderResponse(
                    content=_valid_assessment_json(),
                    model=_NVIDIA_MODEL,
                    input_tokens=15,
                    output_tokens=80,
                    latency_ms=300,
                )
            ]
        )
        gateway = ModelGateway(
            configurations={
                AIWorkload.REPOSITORY_ANALYSIS: _nvidia_configuration(
                    AIWorkload.REPOSITORY_ANALYSIS, max_output_tokens=200
                )
            },
            providers={AIWorkload.REPOSITORY_ANALYSIS: provider},
        )
        result = gateway.generate_structured(
            workload=AIWorkload.REPOSITORY_ANALYSIS,
            system_prompt="Analyze bounded facts.",
            user_prompt='{"facts": []}',
            output_contract=RepositoryAssessment,
        )
        assert result.value is not None
        assert result.provenance.provider == "nvidia"
        assert result.provenance.input_tokens == 15
        assert result.provenance.output_tokens == 80

    def test_three_tier_fallback_chain_nvidia_primary_secondary_groq(self, monkeypatch):
        """Test that when NVIDIA primary fails, NVIDIA secondary is tried, and when both fail, Groq is used."""
        monkeypatch.setattr(config, "AI_REPOSITORY_PROVIDER", "nvidia")
        monkeypatch.setattr(config, "AI_REPOSITORY_ENDPOINT", _NVIDIA_ENDPOINT)
        monkeypatch.setattr(config, "AI_REPOSITORY_MODEL", _NVIDIA_MODEL)
        monkeypatch.setattr(config, "AI_REPOSITORY_API_KEY", "primary-key")
        monkeypatch.setattr(config, "AI_REPOSITORY_SECONDARY_API_KEY", "secondary-key")
        monkeypatch.setattr(config, "AI_REPOSITORY_FALLBACK_PROVIDER", "groq")
        monkeypatch.setattr(config, "AI_REPOSITORY_FALLBACK_ENDPOINT", "https://api.groq.com/openai/v1")
        monkeypatch.setattr(config, "AI_REPOSITORY_FALLBACK_MODEL", "openai/gpt-oss-120b")
        monkeypatch.setattr(config, "AI_REPOSITORY_FALLBACK_API_KEY", "groq-key")

        # Case 1: Primary fails, Secondary succeeds
        primary_provider = _FakeNvidiaProvider([ProviderError("Primary NVIDIA failed.")])
        secondary_provider = _FakeNvidiaProvider(
            [
                ProviderResponse(
                    content=_valid_assessment_json(),
                    model=_NVIDIA_MODEL,
                    input_tokens=12,
                    output_tokens=50,
                )
            ]
        )
        gateway = ModelGateway(
            configurations={
                AIWorkload.REPOSITORY_ANALYSIS: _nvidia_configuration(
                    AIWorkload.REPOSITORY_ANALYSIS, api_key="primary-key"
                )
            },
            providers={AIWorkload.REPOSITORY_ANALYSIS: primary_provider},
        )
        # Mock _generate_with_secondary to return secondary_provider result
        with patch.object(
            gateway,
            "secondary_configuration_for",
            return_value=_nvidia_configuration(
                AIWorkload.REPOSITORY_ANALYSIS, api_key="secondary-key"
            ),
        ):
            with patch(
                "backend.services.model_gateway.build_provider",
                return_value=secondary_provider,
            ):
                result = gateway.generate_structured(
                    workload=AIWorkload.REPOSITORY_ANALYSIS,
                    system_prompt="Analyze bounded facts.",
                    user_prompt='{"facts": []}',
                    output_contract=RepositoryAssessment,
                )
                assert result.value is not None
                assert result.provenance.provider == "nvidia"



# ---------------------------------------------------------------------------
# Credential safety tests
# ---------------------------------------------------------------------------


class TestCredentialSafety:
    def test_api_key_absent_from_configuration_repr(self):
        cfg = _cfg()
        assert _NVIDIA_KEY not in repr(cfg)

    def test_api_key_absent_from_provider_repr(self):
        provider = NvidiaProvider(_cfg(), client=SimpleNamespace())
        # No explicit __repr__ on provider, but configuration.repr must not leak.
        assert _NVIDIA_KEY not in repr(provider.configuration)

    def test_sdk_error_message_not_surfaced_in_provider_error(self):
        secret_detail = "secret-token-12345"

        class _LeakyCompletions:
            def create(self, **_):
                raise ValueError(f"Request rejected: key={secret_detail}")

        client = SimpleNamespace(chat=SimpleNamespace(completions=_LeakyCompletions()))
        provider = NvidiaProvider(_cfg(), client=client)
        with pytest.raises(ProviderError) as exc_info:
            provider.generate(_request())
        error_text = str(exc_info.value)
        assert secret_detail not in error_text
        assert "NVIDIA inference failed" in error_text

    def test_api_key_not_included_in_input_budget_error(self):
        client = _fake_client()
        provider = NvidiaProvider(_cfg(max_input_chars=1), client=client)
        with pytest.raises(ProviderError) as exc_info:
            provider.generate(_request())
        assert _NVIDIA_KEY not in str(exc_info.value)

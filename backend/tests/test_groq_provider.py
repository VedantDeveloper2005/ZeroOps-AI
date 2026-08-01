"""Secure Groq transport and NVIDIA-to-Groq fallback tests.

Every client is mocked. These tests never read a real provider credential or
make a network request.
"""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend import config
from backend.contracts.ai import AIWorkload, RepositoryAssessment
from backend.services.model_gateway import (
    ModelGateway,
    ModelInputBudgetError,
    ModelOutputValidationError,
    build_provider,
    fallback_route_configuration,
)
from backend.services.providers import (
    GROQ_API_ENDPOINT,
    GROQ_GPT_OSS_MODEL,
    GroqProvider,
    ProviderConfiguration,
    ProviderConfigurationError,
    ProviderError,
    ProviderInputBudgetError,
    ProviderRequest,
    ProviderResponse,
)


_TEST_GROQ_KEY = "test-only-groq-placeholder"
_NVIDIA_MODEL = "z-ai/glm-5.2"


def _groq_configuration(
    workload: AIWorkload = AIWorkload.REPOSITORY_ANALYSIS,
    *,
    api_key: str = _TEST_GROQ_KEY,
    max_input_chars: int = 14_000,
    max_output_tokens: int = 800,
) -> ProviderConfiguration:
    return ProviderConfiguration(
        provider="groq",
        endpoint=GROQ_API_ENDPOINT,
        model=GROQ_GPT_OSS_MODEL,
        api_key=api_key,
        max_input_chars=max_input_chars,
        max_output_tokens=max_output_tokens,
        prompt_version=f"{workload.value}.v1",
    )


def _nvidia_configuration(
    workload: AIWorkload = AIWorkload.REPOSITORY_ANALYSIS,
    *,
    max_input_chars: int = 40_000,
) -> ProviderConfiguration:
    return ProviderConfiguration(
        provider="nvidia",
        endpoint="https://integrate.api.nvidia.com/v1",
        model=_NVIDIA_MODEL,
        api_key="test-only-nvidia-placeholder",
        max_input_chars=max_input_chars,
        max_output_tokens=1_600,
        prompt_version=f"{workload.value}.v1",
    )


def _request(**overrides) -> ProviderRequest:
    values = {
        "system_prompt": "Analyze only the supplied repository facts.",
        "user_prompt": "{}",
        "schema_name": "ExampleOutput",
        "output_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
        },
        "max_output_tokens": 500,
        "temperature": 0.0,
    }
    values.update(overrides)
    return ProviderRequest(**values)


def _valid_assessment_json() -> str:
    return json.dumps(
        {
            "schema_version": "repository-assessment.v1",
            "summary": "The supplied evidence describes a bounded application.",
            "deployment_risk": "Runtime telemetry was not supplied.",
            "recommendations": [],
            "cost_optimizations": [],
            "unresolved_questions": [],
            "confidence": "medium",
            "limitations": [],
        }
    )


class _RecordingProvider:
    def __init__(self, name: str, responses: list[ProviderResponse | Exception]):
        self.name = name
        self.responses = list(responses)
        self.requests: list[ProviderRequest] = []

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _response(content: str, *, model: str) -> ProviderResponse:
    return ProviderResponse(
        content=content,
        model=model,
        input_tokens=50,
        output_tokens=20,
        latency_ms=10,
    )


class TestGroqProviderConfiguration:
    def test_requires_separate_credential_and_exact_model(self):
        with pytest.raises(ProviderConfigurationError, match="credential"):
            GroqProvider(_groq_configuration(api_key=""), client=SimpleNamespace())
        with pytest.raises(ProviderConfigurationError, match="gpt-oss-120b"):
            GroqProvider(
                replace(_groq_configuration(), model="openai/another-model"),
                client=SimpleNamespace(),
            )

    @pytest.mark.parametrize(
        "endpoint",
        [
            "http://api.groq.com/openai/v1",
            "https://api.groq.com:443/openai/v1",
            "https://user@api.groq.com/openai/v1",
            "https://api.groq.com/openai/v2",
            "https://api.groq.com/openai/v1?redirect=1",
            "https://api.groq.com.evil.example/openai/v1",
        ],
    )
    def test_rejects_every_noncanonical_endpoint(self, endpoint):
        configuration = ProviderConfiguration(
            provider="groq",
            endpoint=endpoint,
            model=GROQ_GPT_OSS_MODEL,
            api_key=_TEST_GROQ_KEY,
        )
        with pytest.raises(ProviderConfigurationError):
            GroqProvider(configuration, client=SimpleNamespace())

    def test_normalizes_only_a_trailing_slash(self):
        configuration = ProviderConfiguration(
            provider="groq",
            endpoint=f"{GROQ_API_ENDPOINT}/",
            model=GROQ_GPT_OSS_MODEL,
            api_key=_TEST_GROQ_KEY,
        )
        provider = GroqProvider(configuration, client=SimpleNamespace())
        assert provider.configuration.endpoint == GROQ_API_ENDPOINT

    def test_credential_is_absent_from_repr_and_safe_errors(self):
        class _FailingCompletions:
            def create(self, **_):
                raise RuntimeError(f"upstream included {_TEST_GROQ_KEY}")

        client = SimpleNamespace(
            chat=SimpleNamespace(completions=_FailingCompletions())
        )
        provider = GroqProvider(_groq_configuration(), client=client)
        assert _TEST_GROQ_KEY not in repr(provider.configuration)
        with pytest.raises(ProviderError, match="Groq inference failed") as captured:
            provider.generate(_request())
        assert _TEST_GROQ_KEY not in str(captured.value)


class TestGroqProviderGeneration:
    def test_uses_strict_json_schema_and_capped_completion(self):
        captured = {}

        class _Completions:
            def create(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    model=GROQ_GPT_OSS_MODEL,
                    choices=[
                        SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))
                    ],
                    usage=SimpleNamespace(prompt_tokens=12, completion_tokens=3),
                )

        client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
        provider = GroqProvider(
            _groq_configuration(max_output_tokens=300), client=client
        )
        response = provider.generate(_request(max_output_tokens=900))

        assert captured["model"] == GROQ_GPT_OSS_MODEL
        assert captured["max_completion_tokens"] == 300
        assert captured["stream"] is False
        assert captured["response_format"] == {
            "type": "json_schema",
            "json_schema": {
                "name": "ExampleOutput",
                "schema": _request().output_schema,
                "strict": True,
            },
        }
        assert response.input_tokens == 12
        assert response.output_tokens == 3

    def test_complete_prompt_budget_counts_schema_before_network(self):
        captured = {}

        class _Completions:
            def create(self, **kwargs):
                captured.update(kwargs)

        client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
        provider = GroqProvider(
            _groq_configuration(max_input_chars=200), client=client
        )
        with pytest.raises(ProviderInputBudgetError, match="input budget"):
            provider.generate(
                _request(output_schema={"type": "object", "description": "x" * 300})
            )
        assert not captured

    def test_build_provider_selects_groq_without_hidden_retries(self):
        with patch(
            "backend.services.providers.groq.OpenAI", return_value=MagicMock()
        ) as sdk:
            provider = build_provider(_groq_configuration())
        assert isinstance(provider, GroqProvider)
        assert sdk.call_args.kwargs["max_retries"] == 0


class TestFallbackRouting:
    def test_route_settings_are_workload_isolated(self, monkeypatch):
        monkeypatch.setattr(
            config, "AI_REPOSITORY_FALLBACK_API_KEY", "repository-fallback-key"
        )
        monkeypatch.setattr(
            config, "AI_TERRAFORM_FALLBACK_API_KEY", "terraform-fallback-key"
        )
        repository = fallback_route_configuration(AIWorkload.REPOSITORY_ANALYSIS)
        terraform = fallback_route_configuration(AIWorkload.TERRAFORM_GENERATION)

        assert repository.api_key == "repository-fallback-key"
        assert terraform.api_key == "terraform-fallback-key"
        assert repository.api_key != terraform.api_key
        assert repository.model == terraform.model == GROQ_GPT_OSS_MODEL
        assert "repository-fallback-key" not in repr(repository)
        assert "terraform-fallback-key" not in repr(terraform)

    @pytest.mark.parametrize(
        ("workload", "setting"),
        [
            (
                AIWorkload.REPOSITORY_ANALYSIS,
                "AI_REPOSITORY_FALLBACK_PROVIDER",
            ),
            (
                AIWorkload.TERRAFORM_GENERATION,
                "AI_TERRAFORM_FALLBACK_PROVIDER",
            ),
        ],
    )
    def test_fallback_route_rejects_every_non_groq_provider(
        self, monkeypatch, workload, setting
    ):
        monkeypatch.setattr(config, setting, "github-models")
        with pytest.raises(ProviderConfigurationError, match="must be Groq"):
            fallback_route_configuration(workload)

    @pytest.mark.parametrize(
        "workload",
        [AIWorkload.REPOSITORY_ANALYSIS, AIWorkload.TERRAFORM_GENERATION],
    )
    def test_injected_fallback_configuration_is_also_locked_to_groq(
        self, workload
    ):
        wrong_fallback = ProviderConfiguration(
            provider="github-models",
            endpoint="https://models.github.ai/inference",
            model="openai/gpt-4o",
            api_key="test-only-wrong-fallback-placeholder",
        )
        gateway = ModelGateway(
            fallback_configurations={workload: wrong_fallback}
        )
        with pytest.raises(ProviderConfigurationError, match="must use Groq"):
            gateway.fallback_configuration_for(workload)

    def test_injected_non_groq_provider_cannot_bypass_fallback_lock(self):
        primary = _RecordingProvider(
            "nvidia", [ProviderError("safe primary failure")]
        )
        wrong_fallback = _RecordingProvider(
            "github-models",
            [_response(_valid_assessment_json(), model="openai/gpt-4o")],
        )
        gateway = ModelGateway(
            configurations={
                AIWorkload.REPOSITORY_ANALYSIS: _nvidia_configuration()
            },
            providers={AIWorkload.REPOSITORY_ANALYSIS: primary},
            fallback_configurations={
                AIWorkload.REPOSITORY_ANALYSIS: _groq_configuration()
            },
            fallback_providers={
                AIWorkload.REPOSITORY_ANALYSIS: wrong_fallback
            },
        )
        result = gateway.generate_structured(
            workload=AIWorkload.REPOSITORY_ANALYSIS,
            system_prompt="Analyze bounded facts.",
            user_prompt="{}",
            output_contract=RepositoryAssessment,
        )

        assert result.deterministic_only is True
        assert result.provenance.selected_route == "none"
        assert result.provenance.fallback_attempted is False
        assert len(wrong_fallback.requests) == 0

    def test_primary_unavailable_uses_groq_and_records_actual_route(self):
        primary = _RecordingProvider(
            "nvidia", [ProviderError("safe primary failure")]
        )
        fallback = _RecordingProvider(
            "groq",
            [_response(_valid_assessment_json(), model=GROQ_GPT_OSS_MODEL)],
        )
        gateway = ModelGateway(
            configurations={
                AIWorkload.REPOSITORY_ANALYSIS: _nvidia_configuration()
            },
            providers={AIWorkload.REPOSITORY_ANALYSIS: primary},
            fallback_configurations={
                AIWorkload.REPOSITORY_ANALYSIS: _groq_configuration()
            },
            fallback_providers={AIWorkload.REPOSITORY_ANALYSIS: fallback},
        )
        result = gateway.generate_structured(
            workload=AIWorkload.REPOSITORY_ANALYSIS,
            system_prompt="Analyze bounded facts.",
            user_prompt="{}",
            output_contract=RepositoryAssessment,
        )

        assert result.value is not None
        assert result.provenance.provider == "groq"
        assert result.provenance.model == GROQ_GPT_OSS_MODEL
        assert result.provenance.selected_route == "fallback"
        assert result.provenance.fallback_attempted is True
        assert result.provenance.primary_failure_code == "provider_unavailable"
        assert result.provenance.repair_attempted is False
        assert len(primary.requests) == 1
        assert len(fallback.requests) == 1

    def test_gateway_sends_groq_a_conservative_strict_schema_subset(self):
        primary = _RecordingProvider(
            "nvidia", [ProviderError("safe primary failure")]
        )
        fallback = _RecordingProvider(
            "groq",
            [_response(_valid_assessment_json(), model=GROQ_GPT_OSS_MODEL)],
        )
        gateway = ModelGateway(
            configurations={
                AIWorkload.REPOSITORY_ANALYSIS: _nvidia_configuration()
            },
            providers={AIWorkload.REPOSITORY_ANALYSIS: primary},
            fallback_configurations={
                AIWorkload.REPOSITORY_ANALYSIS: _groq_configuration()
            },
            fallback_providers={AIWorkload.REPOSITORY_ANALYSIS: fallback},
        )
        result = gateway.generate_structured(
            workload=AIWorkload.REPOSITORY_ANALYSIS,
            system_prompt="Analyze bounded facts.",
            user_prompt="{}",
            output_contract=RepositoryAssessment,
        )
        assert result.value is not None
        schema = fallback.requests[0].output_schema

        unsupported = {
            "$defs",
            "$ref",
            "default",
            "format",
            "maxItems",
            "maxLength",
            "minimum",
            "pattern",
            "title",
        }

        def walk(value, *, property_map=False):
            if isinstance(value, dict):
                if property_map:
                    for item in value.values():
                        walk(item)
                    return
                assert not (set(value) & unsupported)
                if value.get("type") == "object":
                    assert value["additionalProperties"] is False
                    assert set(value["required"]) == set(value["properties"])
                for key, item in value.items():
                    walk(item, property_map=key == "properties")
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(schema)

    def test_primary_contract_gets_one_repair_then_one_groq_request(self):
        invalid = _response('{"invalid":true}', model=_NVIDIA_MODEL)
        primary = _RecordingProvider("nvidia", [invalid, invalid])
        fallback = _RecordingProvider(
            "groq",
            [_response(_valid_assessment_json(), model=GROQ_GPT_OSS_MODEL)],
        )
        gateway = ModelGateway(
            configurations={
                AIWorkload.REPOSITORY_ANALYSIS: _nvidia_configuration()
            },
            providers={AIWorkload.REPOSITORY_ANALYSIS: primary},
            fallback_configurations={
                AIWorkload.REPOSITORY_ANALYSIS: _groq_configuration()
            },
            fallback_providers={AIWorkload.REPOSITORY_ANALYSIS: fallback},
        )
        result = gateway.generate_structured(
            workload=AIWorkload.REPOSITORY_ANALYSIS,
            system_prompt="Analyze bounded facts.",
            user_prompt="{}",
            output_contract=RepositoryAssessment,
        )

        assert result.value is not None
        assert result.provenance.provider == "groq"
        assert result.provenance.selected_route == "fallback"
        assert result.provenance.primary_failure_code == "invalid_model_output"
        assert result.provenance.primary_input_tokens == 100
        assert result.provenance.primary_output_tokens == 40
        assert result.provenance.primary_latency_ms == 20
        assert result.provenance.primary_repair_attempted is True
        assert len(primary.requests) == 2
        assert len(fallback.requests) == 1

    def test_invalid_groq_contract_is_not_repaired(self):
        primary = _RecordingProvider(
            "nvidia", [ProviderError("safe primary failure")]
        )
        fallback = _RecordingProvider(
            "groq", [_response('{"invalid":true}', model=GROQ_GPT_OSS_MODEL)]
        )
        gateway = ModelGateway(
            configurations={
                AIWorkload.REPOSITORY_ANALYSIS: _nvidia_configuration()
            },
            providers={AIWorkload.REPOSITORY_ANALYSIS: primary},
            fallback_configurations={
                AIWorkload.REPOSITORY_ANALYSIS: _groq_configuration()
            },
            fallback_providers={AIWorkload.REPOSITORY_ANALYSIS: fallback},
        )
        result = gateway.generate_structured(
            workload=AIWorkload.REPOSITORY_ANALYSIS,
            system_prompt="Analyze bounded facts.",
            user_prompt="{}",
            output_contract=RepositoryAssessment,
        )

        assert result.deterministic_only is True
        assert result.degraded_reason == "invalid_model_output"
        assert result.provenance.provider == "groq"
        assert result.provenance.selected_route == "none"
        assert result.provenance.fallback_attempted is True
        assert result.provenance.primary_failure_code == "provider_unavailable"
        assert result.provenance.repair_attempted is False
        assert len(fallback.requests) == 1

    def test_missing_groq_route_degrades_with_no_selected_model(self):
        primary = _RecordingProvider(
            "nvidia", [ProviderError("safe primary failure")]
        )
        gateway = ModelGateway(
            configurations={
                AIWorkload.REPOSITORY_ANALYSIS: _nvidia_configuration()
            },
            providers={AIWorkload.REPOSITORY_ANALYSIS: primary},
            fallback_configurations={
                AIWorkload.REPOSITORY_ANALYSIS: _groq_configuration(api_key="")
            },
        )
        result = gateway.generate_structured(
            workload=AIWorkload.REPOSITORY_ANALYSIS,
            system_prompt="Analyze bounded facts.",
            user_prompt="{}",
            output_contract=RepositoryAssessment,
        )

        assert result.deterministic_only is True
        assert result.degraded_reason == "provider_unavailable"
        assert result.provenance.selected_route == "none"
        assert result.provenance.fallback_attempted is False
        assert result.provenance.primary_failure_code == "provider_unavailable"

    def test_terraform_fails_closed_after_invalid_groq_contract(self):
        workload = AIWorkload.TERRAFORM_GENERATION
        primary = _RecordingProvider(
            "nvidia", [ProviderError("safe primary failure")]
        )
        fallback = _RecordingProvider(
            "groq", [_response('{"invalid":true}', model=GROQ_GPT_OSS_MODEL)]
        )
        gateway = ModelGateway(
            configurations={workload: _nvidia_configuration(workload)},
            providers={workload: primary},
            fallback_configurations={
                workload: _groq_configuration(
                    workload, max_output_tokens=1_000
                )
            },
            fallback_providers={workload: fallback},
        )
        with pytest.raises(ModelOutputValidationError):
            gateway.generate_structured(
                workload=workload,
                system_prompt="Generate bounded Terraform.",
                user_prompt="{}",
                output_contract=RepositoryAssessment,
            )
        assert len(fallback.requests) == 1

    def test_primary_input_budget_never_calls_fallback(self):
        primary = _RecordingProvider(
            "nvidia", [ProviderInputBudgetError("bounded input rejected")]
        )
        fallback = _RecordingProvider(
            "groq",
            [_response(_valid_assessment_json(), model=GROQ_GPT_OSS_MODEL)],
        )
        gateway = ModelGateway(
            configurations={
                AIWorkload.REPOSITORY_ANALYSIS: _nvidia_configuration()
            },
            providers={AIWorkload.REPOSITORY_ANALYSIS: primary},
            fallback_configurations={
                AIWorkload.REPOSITORY_ANALYSIS: _groq_configuration()
            },
            fallback_providers={AIWorkload.REPOSITORY_ANALYSIS: fallback},
        )
        result = gateway.generate_structured(
            workload=AIWorkload.REPOSITORY_ANALYSIS,
            system_prompt="Analyze bounded facts.",
            user_prompt="{}",
            output_contract=RepositoryAssessment,
        )

        assert result.deterministic_only is True
        assert result.degraded_reason == "input_budget_exceeded"
        assert result.provenance.selected_route == "none"
        assert len(fallback.requests) == 0

    def test_terraform_input_budget_fails_closed_without_fallback(self):
        workload = AIWorkload.TERRAFORM_GENERATION
        primary = _RecordingProvider(
            "nvidia", [ProviderInputBudgetError("bounded input rejected")]
        )
        fallback = _RecordingProvider(
            "groq",
            [_response(_valid_assessment_json(), model=GROQ_GPT_OSS_MODEL)],
        )
        gateway = ModelGateway(
            configurations={workload: _nvidia_configuration(workload)},
            providers={workload: primary},
            fallback_configurations={workload: _groq_configuration(workload)},
            fallback_providers={workload: fallback},
        )
        with pytest.raises(ModelInputBudgetError):
            gateway.generate_structured(
                workload=workload,
                system_prompt="Generate bounded Terraform.",
                user_prompt="{}",
                output_contract=RepositoryAssessment,
            )
        assert len(fallback.requests) == 0

    def test_non_nvidia_primary_never_uses_groq_fallback(self):
        primary_config = ProviderConfiguration(
            provider="github-models",
            endpoint="https://models.github.ai/inference",
            model="openai/gpt-4o",
            api_key="test-only-github-placeholder",
            max_input_chars=20_000,
            max_output_tokens=800,
        )
        primary = _RecordingProvider(
            "github-models", [ProviderError("safe primary failure")]
        )
        fallback = _RecordingProvider(
            "groq",
            [_response(_valid_assessment_json(), model=GROQ_GPT_OSS_MODEL)],
        )
        gateway = ModelGateway(
            configurations={AIWorkload.REPOSITORY_ANALYSIS: primary_config},
            providers={AIWorkload.REPOSITORY_ANALYSIS: primary},
            fallback_configurations={
                AIWorkload.REPOSITORY_ANALYSIS: _groq_configuration()
            },
            fallback_providers={AIWorkload.REPOSITORY_ANALYSIS: fallback},
        )
        result = gateway.generate_structured(
            workload=AIWorkload.REPOSITORY_ANALYSIS,
            system_prompt="Analyze bounded facts.",
            user_prompt="{}",
            output_contract=RepositoryAssessment,
        )

        assert result.deterministic_only is True
        assert len(fallback.requests) == 0

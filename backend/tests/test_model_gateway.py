import json
from types import SimpleNamespace

import pytest

from backend import config
from backend.contracts.ai import (
    AIWorkload,
    RepositoryAnalysisRequest,
    RepositoryAssessment,
)
from backend.services.model_gateway import (
    ModelGateway,
    ModelOutputValidationError,
    ModelRouteNotConfiguredError,
    generate_repository_assessment,
    route_configuration,
)
from backend.services.providers import (
    AzureFoundryProvider,
    GitHubModelsProvider,
    ProviderConfiguration,
    ProviderConfigurationError,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)


def _configuration(
    workload: AIWorkload,
    *,
    api_key: str = "workload-specific-key",
    max_output_tokens: int = 200,
) -> ProviderConfiguration:
    return ProviderConfiguration(
        provider="github-models",
        endpoint="https://models.github.ai/inference",
        model="openai/gpt-4o",
        api_key=api_key,
        api_version="2026-03-10",
        max_input_chars=20_000,
        max_output_tokens=max_output_tokens,
        prompt_version=f"{workload.value}.v1",
    )


def _valid_assessment() -> dict:
    return {
        "schema_version": "repository-assessment.v1",
        "summary": "The supplied manifest identifies a bounded web application.",
        "deployment_risk": "Production traffic and recovery requirements are not supplied.",
        "recommendations": [
            {
                "id": "verify-production-build",
                "priority": "required",
                "category": "delivery",
                "action": "Run the recorded production build in an isolated build environment.",
                "rationale": "The repository facts identify a build script but no successful build evidence.",
                "evidence_refs": ["fact-build"],
                "cost_impact": "unknown",
                "security_impact": "neutral",
                "reliability_impact": "increase",
                "tradeoffs": ["The build consumes temporary CI capacity."],
            }
        ],
        "cost_optimizations": [
            {
                "id": "measure-before-sizing",
                "title": "Measure utilization before selecting a fixed tier",
                "rationale": "No traffic or utilization evidence is supplied.",
                "evidence_refs": ["fact-build"],
                "expected_impact": "unknown",
                "tradeoffs": ["Measurement delays a final sizing decision."],
                "validation_needed": "Collect representative request and utilization telemetry.",
            }
        ],
        "unresolved_questions": ["What traffic and recovery objectives apply?"],
        "confidence": "medium",
        "limitations": ["No runtime telemetry or verified pricing was supplied."],
    }


def _analysis_request() -> RepositoryAnalysisRequest:
    return RepositoryAnalysisRequest.model_validate(
        {
            "schema_version": "repository-analysis-request.v1",
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "project_id": "22222222-2222-2222-2222-222222222222",
            "repository": "owner/repository",
            "branch": "main",
            "commit_sha": "a" * 40,
            "source_facts": [
                {
                    "id": "fact-build",
                    "category": "build",
                    "value": "npm run build",
                    "source_path": "package.json",
                    "source_line": 5,
                }
            ],
            "safe_files": [],
            "repository_tree": "package.json",
            "constraints": [],
        }
    )


class FakeProvider:
    name = "fake-provider"

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_workload_routes_use_distinct_credentials_without_legacy_fallback(monkeypatch):
    monkeypatch.setattr(config, "AI_REPOSITORY_API_KEY", "repository-key")
    monkeypatch.setattr(config, "AI_TERRAFORM_API_KEY", "terraform-key")
    monkeypatch.setattr(config, "GITHUB_MODELS_API_KEY", "legacy-shared-key")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "legacy-openai-key")

    repository = route_configuration(AIWorkload.REPOSITORY_ANALYSIS)
    terraform = route_configuration(AIWorkload.TERRAFORM_GENERATION)

    assert repository.api_key == "repository-key"
    assert terraform.api_key == "terraform-key"
    assert repository.api_key != terraform.api_key
    assert "repository-key" not in repr(repository)
    assert "terraform-key" not in repr(terraform)

    monkeypatch.setattr(config, "AI_REPOSITORY_API_KEY", "")
    assert route_configuration(AIWorkload.REPOSITORY_ANALYSIS).api_key == ""


def test_missing_repository_route_degrades_but_terraform_fails_closed():
    repository_config = _configuration(AIWorkload.REPOSITORY_ANALYSIS, api_key="")
    repository_gateway = ModelGateway(
        configurations={AIWorkload.REPOSITORY_ANALYSIS: repository_config}
    )
    result = repository_gateway.generate_structured(
        workload=AIWorkload.REPOSITORY_ANALYSIS,
        system_prompt="Analyze bounded facts.",
        user_prompt="{}",
        output_contract=RepositoryAssessment,
    )

    assert result.value is None
    assert result.deterministic_only is True
    assert result.degraded_reason == "provider_not_configured"

    terraform_config = _configuration(AIWorkload.TERRAFORM_GENERATION, api_key="")
    terraform_gateway = ModelGateway(
        configurations={AIWorkload.TERRAFORM_GENERATION: terraform_config}
    )
    with pytest.raises(ModelRouteNotConfiguredError):
        terraform_gateway.generate_structured(
            workload=AIWorkload.TERRAFORM_GENERATION,
            system_prompt="Generate bounded Terraform.",
            user_prompt="{}",
            output_contract=RepositoryAssessment,
        )


def test_invalid_repository_limits_degrade_while_terraform_limits_fail_closed(monkeypatch):
    monkeypatch.setattr(config, "AI_REPOSITORY_MAX_INPUT_CHARS", 0)
    repository = ModelGateway().generate_structured(
        workload=AIWorkload.REPOSITORY_ANALYSIS,
        system_prompt="Analyze bounded facts.",
        user_prompt="{}",
        output_contract=RepositoryAssessment,
    )
    assert repository.deterministic_only is True
    assert repository.degraded_reason == "provider_not_configured"

    monkeypatch.setattr(config, "AI_TERRAFORM_MAX_OUTPUT_TOKENS", 0)
    with pytest.raises(ModelRouteNotConfiguredError):
        ModelGateway().generate_structured(
            workload=AIWorkload.TERRAFORM_GENERATION,
            system_prompt="Generate bounded Terraform.",
            user_prompt="{}",
            output_contract=RepositoryAssessment,
        )


def test_gateway_repairs_invalid_json_once_and_aggregates_provenance():
    valid_json = json.dumps(_valid_assessment())
    provider = FakeProvider(
        [
            ProviderResponse(
                content='{"schema_version":"repository-assessment.v1","summary":7}',
                model="openai/gpt-4o",
                input_tokens=10,
                output_tokens=4,
                latency_ms=20,
            ),
            ProviderResponse(
                content=valid_json,
                model="openai/gpt-4o",
                input_tokens=12,
                output_tokens=30,
                latency_ms=25,
            ),
        ]
    )
    gateway = ModelGateway(
        configurations={
            AIWorkload.REPOSITORY_ANALYSIS: _configuration(
                AIWorkload.REPOSITORY_ANALYSIS,
                max_output_tokens=50,
            )
        },
        providers={AIWorkload.REPOSITORY_ANALYSIS: provider},
    )

    result = gateway.generate_structured(
        workload=AIWorkload.REPOSITORY_ANALYSIS,
        system_prompt="Analyze bounded facts.",
        user_prompt='{"facts":[]}',
        output_contract=RepositoryAssessment,
        max_output_tokens=500,
    )

    assert result.value is not None
    assert result.value.schema_version == "repository-assessment.v1"
    assert len(provider.requests) == 2
    assert all(request.max_output_tokens == 50 for request in provider.requests)
    assert result.provenance.repair_attempted is True
    assert result.provenance.input_tokens == 22
    assert result.provenance.output_tokens == 34
    assert result.provenance.latency_ms == 45
    assert result.provenance.schema_version == "repository-assessment.v1"


def test_foundry_gateway_uses_portal_safe_schema_and_runtime_validation():
    provider = FakeProvider(
        [
            ProviderResponse(
                content=json.dumps(_valid_assessment()),
                model="zeroops-repository-analyst",
            )
        ]
    )
    gateway = ModelGateway(
        configurations={
            AIWorkload.REPOSITORY_ANALYSIS: ProviderConfiguration(
                provider="azure-foundry",
                endpoint="https://example.ai.azure.com/api/projects/zeroops",
                model="",
                api_key="",
                agent_name="zeroops-repository-analyst",
                max_input_chars=200_000,
                max_output_tokens=2_000,
                prompt_version="repository-analysis.v1",
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

    assert result.value is not None
    schema = provider.requests[0].output_schema

    def walk(value, *, property_map=False):
        if isinstance(value, dict):
            if property_map:
                for item in value.values():
                    walk(item)
                return
            assert not (
                set(value)
                & {
                    "$defs",
                    "$ref",
                    "default",
                    "format",
                    "maxItems",
                    "maxLength",
                    "minimum",
                    "pattern",
                }
            )
            if value.get("type") == "object":
                assert value["additionalProperties"] is False
                assert set(value["required"]) == set(value["properties"])
            for key, item in value.items():
                walk(item, property_map=key == "properties")
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(schema)


def test_gateway_never_attempts_a_second_repair():
    invalid = ProviderResponse(
        content='{"not":"the contract"}',
        model="openai/gpt-4o",
        input_tokens=1,
        output_tokens=1,
        latency_ms=1,
    )
    provider = FakeProvider([invalid, invalid, invalid])
    gateway = ModelGateway(
        configurations={
            AIWorkload.TERRAFORM_GENERATION: _configuration(
                AIWorkload.TERRAFORM_GENERATION
            )
        },
        providers={AIWorkload.TERRAFORM_GENERATION: provider},
    )

    with pytest.raises(ModelOutputValidationError):
        gateway.generate_structured(
            workload=AIWorkload.TERRAFORM_GENERATION,
            system_prompt="Generate bounded output.",
            user_prompt="{}",
            output_contract=RepositoryAssessment,
        )
    assert len(provider.requests) == 2


def test_repository_wrapper_enforces_evidence_references_and_degrades_safely():
    provider = FakeProvider(
        [
            ProviderResponse(
                content=json.dumps(_valid_assessment()),
                model="openai/gpt-4o",
            )
        ]
    )
    gateway = ModelGateway(
        configurations={
            AIWorkload.REPOSITORY_ANALYSIS: _configuration(
                AIWorkload.REPOSITORY_ANALYSIS
            )
        },
        providers={AIWorkload.REPOSITORY_ANALYSIS: provider},
    )
    result = generate_repository_assessment(_analysis_request(), gateway=gateway)
    assert result.value is not None
    assert result.deterministic_only is False

    invalid_assessment = _valid_assessment()
    invalid_assessment["recommendations"][0]["evidence_refs"] = ["not-supplied"]
    invalid_provider = FakeProvider(
        [
            ProviderResponse(
                content=json.dumps(invalid_assessment),
                model="openai/gpt-4o",
            )
        ]
    )
    invalid_gateway = ModelGateway(
        configurations={
            AIWorkload.REPOSITORY_ANALYSIS: _configuration(
                AIWorkload.REPOSITORY_ANALYSIS
            )
        },
        providers={AIWorkload.REPOSITORY_ANALYSIS: invalid_provider},
    )
    degraded = generate_repository_assessment(
        _analysis_request(),
        gateway=invalid_gateway,
    )
    assert degraded.value is None
    assert degraded.deterministic_only is True
    assert degraded.degraded_reason == "invalid_evidence_reference"


def test_github_models_provider_requires_current_endpoint_and_catalog_model():
    configuration = _configuration(AIWorkload.REPOSITORY_ANALYSIS)
    provider = GitHubModelsProvider(configuration, client=SimpleNamespace())
    assert provider.configuration.endpoint == "https://models.github.ai/inference"
    assert provider.configuration.model == "openai/gpt-4o"

    with pytest.raises(ProviderConfigurationError, match="models.github.ai"):
        GitHubModelsProvider(
            ProviderConfiguration(
                provider="github-models",
                endpoint="https://models.inference.ai.azure.com",
                model="openai/gpt-4o",
                api_key="key",
            ),
            client=SimpleNamespace(),
        )

    with pytest.raises(ProviderConfigurationError, match="catalog-qualified"):
        GitHubModelsProvider(
            ProviderConfiguration(
                provider="github-models",
                endpoint="https://models.github.ai/inference",
                model="gpt-4o",
                api_key="key",
            ),
            client=SimpleNamespace(),
        )


def test_github_models_provider_sends_schema_and_enforces_output_cap():
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                model="openai/gpt-4o",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"ok":true}')
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3),
            )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=Completions())
    )
    provider = GitHubModelsProvider(
        _configuration(
            AIWorkload.REPOSITORY_ANALYSIS,
            max_output_tokens=40,
        ),
        client=client,
    )
    response = provider.generate(
        ProviderRequest(
            system_prompt="Return bounded output.",
            user_prompt="{}",
            schema_name="Example",
            output_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
            },
            max_output_tokens=400,
            temperature=0,
        )
    )

    assert "Return only a JSON object matching this JSON Schema exactly" in captured["messages"][0]["content"]
    assert '"additionalProperties":false' in captured["messages"][0]["content"]
    assert captured["max_tokens"] == 40
    assert captured["response_format"] == {"type": "json_object"}
    assert response.input_tokens == 5
    assert response.output_tokens == 3

    tiny_budget = ProviderConfiguration(
        provider="github-models",
        endpoint="https://models.github.ai/inference",
        model="openai/gpt-4o",
        api_key="key",
        max_input_chars=20,
        max_output_tokens=40,
    )
    with pytest.raises(ProviderError, match="input budget"):
        GitHubModelsProvider(tiny_budget, client=client).generate(
            ProviderRequest(
                system_prompt="system",
                user_prompt="user",
                schema_name="Example",
                output_schema={"type": "object", "properties": {"value": {"type": "string"}}},
                max_output_tokens=10,
            )
        )


def test_foundry_route_rejects_api_keys_and_accepts_managed_identity_shape():
    with pytest.raises(ProviderConfigurationError, match="managed identity"):
        AzureFoundryProvider(
            ProviderConfiguration(
                provider="azure-foundry",
                endpoint="https://example.ai.azure.com/api/projects/zeroops",
                model="",
                agent_name="zeroops-repository-analyst",
                api_key="must-not-be-used",
            ),
            openai_client=SimpleNamespace(),
        )

    provider = AzureFoundryProvider(
        ProviderConfiguration(
            provider="azure-foundry",
            endpoint="https://example.ai.azure.com/api/projects/zeroops",
            model="",
            agent_name="zeroops-repository-analyst",
            api_key="",
        ),
        openai_client=SimpleNamespace(),
    )
    assert provider.configuration.agent_name == "zeroops-repository-analyst"

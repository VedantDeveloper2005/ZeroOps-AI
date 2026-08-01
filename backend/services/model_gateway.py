"""Workload-isolated structured model gateway.

Repository analysis and Terraform generation intentionally resolve independent
configuration and provider instances. Missing repository inference degrades to
the deterministic scanner; Terraform generation always fails closed.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar, get_args
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError

from backend import config
from backend.contracts.ai import (
    AIWorkload,
    ModelProvenance,
    RepositoryAnalysisRequest,
    RepositoryAssessment,
)
from backend.services.providers import (
    AzureFoundryProvider,
    GitHubModelsProvider,
    NvidiaProvider,
    ProviderConfiguration,
    ProviderConfigurationError,
    ProviderError,
    ProviderRequest,
    StructuredModelProvider,
)


OutputContract = TypeVar("OutputContract", bound=BaseModel)
_AI_SPEC_ROOT = Path(__file__).resolve().parents[2] / "ai-specs"


class ModelGatewayError(RuntimeError):
    """Base safe error for callers; never includes provider response content."""


class ModelRouteNotConfiguredError(ModelGatewayError):
    """Raised when a fail-closed workload has no usable provider route."""


class ModelInputBudgetError(ModelGatewayError):
    """Raised when bounded model input is too large."""


class ModelOutputValidationError(ModelGatewayError):
    """Raised when initial and repair responses both violate the contract."""


@dataclass(frozen=True)
class StructuredGenerationResult(Generic[OutputContract]):
    value: OutputContract | None
    provenance: ModelProvenance
    degraded_reason: str | None = None

    @property
    def deterministic_only(self) -> bool:
        return self.provenance.execution_mode == "deterministic_only"


def route_configuration(workload: AIWorkload) -> ProviderConfiguration:
    """Resolve exactly one workload route without consulting legacy AI keys."""
    if workload == AIWorkload.REPOSITORY_ANALYSIS:
        return ProviderConfiguration(
            provider=config.AI_REPOSITORY_PROVIDER,
            endpoint=config.AI_REPOSITORY_ENDPOINT,
            model=config.AI_REPOSITORY_MODEL,
            api_key=config.AI_REPOSITORY_API_KEY,
            agent_name=config.AI_REPOSITORY_AGENT_NAME,
            api_version=config.AI_GITHUB_API_VERSION,
            timeout_seconds=config.AI_MODEL_TIMEOUT_SECONDS,
            max_input_chars=config.AI_REPOSITORY_MAX_INPUT_CHARS,
            max_output_tokens=config.AI_REPOSITORY_MAX_OUTPUT_TOKENS,
            prompt_version=config.AI_REPOSITORY_PROMPT_VERSION,
        )
    if workload == AIWorkload.TERRAFORM_GENERATION:
        return ProviderConfiguration(
            provider=config.AI_TERRAFORM_PROVIDER,
            endpoint=config.AI_TERRAFORM_ENDPOINT,
            model=config.AI_TERRAFORM_MODEL,
            api_key=config.AI_TERRAFORM_API_KEY,
            agent_name=config.AI_TERRAFORM_AGENT_NAME,
            api_version=config.AI_GITHUB_API_VERSION,
            timeout_seconds=config.AI_MODEL_TIMEOUT_SECONDS,
            max_input_chars=config.AI_TERRAFORM_MAX_INPUT_CHARS,
            max_output_tokens=config.AI_TERRAFORM_MAX_OUTPUT_TOKENS,
            prompt_version=config.AI_TERRAFORM_PROMPT_VERSION,
        )
    raise ModelRouteNotConfiguredError("Unsupported AI workload.")


def build_provider(configuration: ProviderConfiguration) -> StructuredModelProvider:
    provider_name = configuration.provider.strip().lower().replace("_", "-")
    if provider_name == "nvidia":
        return NvidiaProvider(configuration)
    if provider_name == "github-models":
        return GitHubModelsProvider(configuration)
    if provider_name in {"azure-foundry", "microsoft-foundry"}:
        return AzureFoundryProvider(configuration)
    raise ProviderConfigurationError("The selected AI provider is not supported.")


def _parse_json_object(content: str) -> dict:
    value = content.strip()
    if value.startswith("```json") and value.endswith("```"):
        value = value[7:-3].strip()
    elif value.startswith("```") and value.endswith("```"):
        value = value[3:-3].strip()
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("Structured model output must be a JSON object.")
    return parsed


def _schema_version(output_contract: type[BaseModel]) -> str:
    field = output_contract.model_fields.get("schema_version")
    default = getattr(field, "default", None)
    if isinstance(default, str):
        return default
    annotation_values = get_args(getattr(field, "annotation", None))
    if len(annotation_values) == 1 and isinstance(annotation_values[0], str):
        return annotation_values[0]
    return output_contract.__name__


_UNSUPPORTED_FOUNDRY_SCHEMA_KEYS = {
    "$schema",
    "$defs",
    "$ref",
    "default",
    "format",
    "maxItems",
    "maxLength",
    "maxProperties",
    "maximum",
    "minContains",
    "minItems",
    "minLength",
    "minProperties",
    "minimum",
    "multipleOf",
    "pattern",
    "patternProperties",
    "propertyNames",
    "title",
    "unevaluatedItems",
    "unevaluatedProperties",
    "uniqueItems",
}


def _foundry_output_schema(schema: dict) -> dict:
    """Return the strict structured-output subset supported by Foundry."""

    definitions = schema.get("$defs", {})

    def dereference(value):
        if isinstance(value, list):
            return [dereference(item) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            reference = value["$ref"]
            prefix = "#/$defs/"
            if not isinstance(reference, str) or not reference.startswith(prefix):
                raise ModelGatewayError("AI output schema contains an unsupported reference.")
            name = reference.removeprefix(prefix)
            if name not in definitions:
                raise ModelGatewayError("AI output schema contains an unknown reference.")
            merged = copy.deepcopy(definitions[name])
            merged.update({key: item for key, item in value.items() if key != "$ref"})
            return dereference(merged)
        return {
            key: dereference(item)
            for key, item in value.items()
            if key != "$defs"
        }

    def reduce(value, *, property_map: bool = False):
        if isinstance(value, list):
            return [reduce(item) for item in value]
        if not isinstance(value, dict):
            return value
        if property_map:
            return {
                str(field_name): reduce(field_schema)
                for field_name, field_schema in value.items()
            }
        result = {}
        for key, item in value.items():
            if key in _UNSUPPORTED_FOUNDRY_SCHEMA_KEYS:
                continue
            if key == "const":
                result["enum"] = [item]
                continue
            result[key] = reduce(item, property_map=key == "properties")
        if result.get("type") == "object":
            properties = result.get("properties")
            if not isinstance(properties, dict):
                raise ModelGatewayError(
                    "Foundry output objects require explicit properties."
                )
            result["additionalProperties"] = False
            result["required"] = list(properties)
        return result

    return reduce(dereference(schema))


def _request_hash(
    *,
    workload: AIWorkload,
    configuration: ProviderConfiguration,
    system_prompt: str,
    user_prompt: str,
    output_schema: dict,
) -> str:
    # Credentials and tenant display names are never part of persisted
    # provenance. The actual bounded model input and route version are hashed.
    canonical = json.dumps(
        {
            "workload": workload.value,
            "provider": configuration.provider,
            "model": configuration.model,
            "prompt_version": configuration.prompt_version,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "output_schema": output_schema,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ModelGateway:
    def __init__(
        self,
        *,
        configurations: dict[AIWorkload, ProviderConfiguration] | None = None,
        providers: dict[AIWorkload, StructuredModelProvider] | None = None,
    ) -> None:
        self._configurations = configurations or {}
        self._providers = providers or {}

    def configuration_for(self, workload: AIWorkload) -> ProviderConfiguration:
        return self._configurations.get(workload) or route_configuration(workload)

    def provider_for(self, workload: AIWorkload) -> StructuredModelProvider:
        provider = self._providers.get(workload)
        if provider is not None:
            return provider
        provider = build_provider(self.configuration_for(workload))
        self._providers[workload] = provider
        return provider

    def generate_structured(
        self,
        *,
        workload: AIWorkload,
        system_prompt: str,
        user_prompt: str,
        output_contract: type[OutputContract],
        correlation_id: UUID | None = None,
        max_output_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> StructuredGenerationResult[OutputContract]:
        """Generate and validate a model response with at most one repair call."""
        if not 0.0 <= temperature <= 1.0:
            raise ValueError("AI temperature must be between 0 and 1.")
        output_schema = output_contract.model_json_schema()
        serialized_schema = json.dumps(
            output_schema,
            sort_keys=True,
            separators=(",", ":"),
        )
        correlation = correlation_id or uuid4()
        try:
            configuration = self.configuration_for(workload)
        except ProviderConfigurationError as error:
            if workload == AIWorkload.TERRAFORM_GENERATION:
                raise ModelRouteNotConfiguredError(
                    "The selected AI workload route is not configured."
                ) from error
            configuration = ProviderConfiguration(
                provider="none",
                endpoint="",
                model="deterministic-scanner",
                max_input_chars=60_000,
                max_output_tokens=1,
                prompt_version="repository-analysis.v1",
            )
            request_digest = _request_hash(
                workload=workload,
                configuration=configuration,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                output_schema=output_schema,
            )
            return self._degrade_or_raise(
                workload=workload,
                configuration=configuration,
                correlation_id=correlation,
                request_hash=request_digest,
                schema_version=_schema_version(output_contract),
                reason="provider_not_configured",
                exception=ModelRouteNotConfiguredError(
                    "The selected AI workload route is not configured."
                ),
            )
        provider_output_schema = (
            _foundry_output_schema(output_schema)
            if configuration.provider.strip().lower().replace("_", "-")
            in {"azure-foundry", "microsoft-foundry"}
            else output_schema
        )
        serialized_schema = json.dumps(
            provider_output_schema,
            sort_keys=True,
            separators=(",", ":"),
        )
        request_digest = _request_hash(
            workload=workload,
            configuration=configuration,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_schema=provider_output_schema,
        )
        if (
            len(system_prompt)
            + len(user_prompt)
            + len(serialized_schema)
            > configuration.max_input_chars
        ):
            return self._degrade_or_raise(
                workload=workload,
                configuration=configuration,
                correlation_id=correlation,
                request_hash=request_digest,
                schema_version=_schema_version(output_contract),
                reason="input_budget_exceeded",
                exception=ModelInputBudgetError("AI request exceeds the configured input budget."),
            )

        try:
            provider = self.provider_for(workload)
        except (ProviderConfigurationError, ProviderError) as error:
            return self._degrade_or_raise(
                workload=workload,
                configuration=configuration,
                correlation_id=correlation,
                request_hash=request_digest,
                schema_version=_schema_version(output_contract),
                reason="provider_not_configured",
                exception=ModelRouteNotConfiguredError(
                    "The selected AI workload route is not configured."
                ),
            )

        capped_output_tokens = min(
            max_output_tokens or configuration.max_output_tokens,
            configuration.max_output_tokens,
        )
        initial_request = ProviderRequest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_name=output_contract.__name__,
            output_schema=provider_output_schema,
            max_output_tokens=capped_output_tokens,
            temperature=temperature,
        )

        input_tokens = 0
        output_tokens = 0
        latency_ms = 0
        repair_attempted = False
        try:
            initial = provider.generate(initial_request)
            input_tokens += initial.input_tokens
            output_tokens += initial.output_tokens
            latency_ms += initial.latency_ms
        except ProviderError:
            return self._degrade_or_raise(
                workload=workload,
                configuration=configuration,
                correlation_id=correlation,
                request_hash=request_digest,
                schema_version=_schema_version(output_contract),
                reason="provider_unavailable",
                exception=ModelGatewayError("AI inference is currently unavailable."),
            )

        try:
            value = output_contract.model_validate(_parse_json_object(initial.content))
        except (ValueError, json.JSONDecodeError, ValidationError):
            repair_attempted = True
            repair_system = (
                "Repair the candidate JSON so it matches the supplied JSON Schema exactly. "
                "Do not add commentary, markdown, facts, or fields. Return only the repaired JSON object."
            )
            invalid_candidate = initial.content[:12_000]
            repair_user = json.dumps(
                {
                    "schema": provider_output_schema,
                    "candidate": invalid_candidate,
                },
                separators=(",", ":"),
            )
            if len(repair_system) + len(repair_user) > configuration.max_input_chars:
                return self._degrade_or_raise(
                    workload=workload,
                    configuration=configuration,
                    correlation_id=correlation,
                    request_hash=request_digest,
                    schema_version=_schema_version(output_contract),
                    reason="invalid_model_output",
                    exception=ModelOutputValidationError(
                        "AI output did not satisfy the required contract."
                    ),
                    provider_name=provider.name,
                    model=initial.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    repair_attempted=repair_attempted,
                )

            try:
                repaired = provider.generate(
                    ProviderRequest(
                        system_prompt=repair_system,
                        user_prompt=repair_user,
                        schema_name=output_contract.__name__,
                        output_schema=provider_output_schema,
                        max_output_tokens=capped_output_tokens,
                        temperature=0.0,
                    )
                )
                input_tokens += repaired.input_tokens
                output_tokens += repaired.output_tokens
                latency_ms += repaired.latency_ms
                value = output_contract.model_validate(_parse_json_object(repaired.content))
                response_model = repaired.model
            except (ProviderError, ValueError, json.JSONDecodeError, ValidationError):
                return self._degrade_or_raise(
                    workload=workload,
                    configuration=configuration,
                    correlation_id=correlation,
                    request_hash=request_digest,
                    schema_version=_schema_version(output_contract),
                    reason="invalid_model_output",
                    exception=ModelOutputValidationError(
                        "AI output did not satisfy the required contract."
                    ),
                    provider_name=provider.name,
                    model=initial.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    repair_attempted=repair_attempted,
                )
        else:
            response_model = initial.model

        provenance = ModelProvenance(
            workload=workload,
            provider=provider.name,
            model=response_model,
            prompt_version=configuration.prompt_version,
            schema_version=_schema_version(output_contract),
            execution_mode="model",
            correlation_id=correlation,
            request_hash=request_digest,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            repair_attempted=repair_attempted,
            cached=False,
        )
        return StructuredGenerationResult(value=value, provenance=provenance)

    @staticmethod
    def _degrade_or_raise(
        *,
        workload: AIWorkload,
        configuration: ProviderConfiguration,
        correlation_id: UUID,
        request_hash: str,
        schema_version: str,
        reason: str,
        exception: ModelGatewayError,
        provider_name: str | None = None,
        model: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
        repair_attempted: bool = False,
    ):
        if workload == AIWorkload.TERRAFORM_GENERATION:
            raise exception

        provenance = ModelProvenance(
            workload=workload,
            provider=provider_name or configuration.provider or "none",
            model=model or configuration.model or "deterministic-scanner",
            prompt_version=configuration.prompt_version,
            schema_version=schema_version,
            execution_mode="deterministic_only",
            correlation_id=correlation_id,
            request_hash=request_hash,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            repair_attempted=repair_attempted,
            cached=False,
        )
        return StructuredGenerationResult(
            value=None,
            provenance=provenance,
            degraded_reason=reason,
        )


def load_repository_instructions() -> str:
    path = _AI_SPEC_ROOT / "repository-analysis" / "instructions.md"
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ModelGatewayError(
            "Repository analysis instructions are unavailable."
        ) from error
    if not value:
        raise ModelGatewayError("Repository analysis instructions are empty.")
    return value


def validate_repository_evidence(
    assessment: RepositoryAssessment,
    request: RepositoryAnalysisRequest,
) -> RepositoryAssessment:
    """Require every model recommendation to cite supplied evidence IDs."""
    evidence_ids = {
        *(fact.id for fact in request.source_facts),
        *(file.id for file in request.safe_files),
    }
    cited_ids = {
        *(
            evidence_id
            for recommendation in assessment.recommendations
            for evidence_id in recommendation.evidence_refs
        ),
        *(
            evidence_id
            for optimization in assessment.cost_optimizations
            for evidence_id in optimization.evidence_refs
        ),
    }
    if not cited_ids.issubset(evidence_ids):
        raise ModelOutputValidationError(
            "Repository assessment cites evidence that was not supplied."
        )
    return assessment


def generate_repository_assessment(
    request: RepositoryAnalysisRequest,
    *,
    gateway: ModelGateway | None = None,
) -> StructuredGenerationResult[RepositoryAssessment]:
    """Run bounded analysis or return an explicit deterministic-only outcome."""
    model_gateway = gateway or ModelGateway()
    result = model_gateway.generate_structured(
        workload=AIWorkload.REPOSITORY_ANALYSIS,
        system_prompt=load_repository_instructions(),
        user_prompt=json.dumps(
            request.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ),
        output_contract=RepositoryAssessment,
    )
    if result.value is None:
        return result
    try:
        validate_repository_evidence(result.value, request)
    except ModelOutputValidationError:
        return StructuredGenerationResult(
            value=None,
            provenance=result.provenance.model_copy(
                update={"execution_mode": "deterministic_only"}
            ),
            degraded_reason="invalid_evidence_reference",
        )
    return result


__all__ = [
    "ModelGateway",
    "ModelGatewayError",
    "ModelInputBudgetError",
    "ModelOutputValidationError",
    "ModelRouteNotConfiguredError",
    "StructuredGenerationResult",
    "build_provider",
    "generate_repository_assessment",
    "load_repository_instructions",
    "route_configuration",
    "validate_repository_evidence",
]

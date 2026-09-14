"""Strict Microsoft Foundry inference with workload-local credentials."""

from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Literal, TypeVar
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from pydantic import BaseModel, ValidationError

from .security import canonical_json_bytes, sha256_bytes


T = TypeVar("T", bound=BaseModel)



def _azure_openai_endpoint(endpoint: str) -> str:
    """Validate and normalize a Microsoft Foundry Azure OpenAI v1 endpoint."""
    try:
        parsed = urlparse(endpoint)
        port = parsed.port
    except ValueError as error:
        raise ValueError("Microsoft Foundry OpenAI endpoint must be a valid HTTPS URL") from error
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not hostname.endswith(".openai.azure.com"):
        raise ValueError("Microsoft Foundry OpenAI endpoint must use HTTPS *.openai.azure.com")
    if (
        port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") not in {"", "/openai/v1"}
    ):
        raise ValueError("Microsoft Foundry OpenAI endpoint must be a bare /openai/v1 URL")
    return f"https://{hostname}/openai/v1"


class ModelUnavailableError(RuntimeError):
    pass


class ModelContractError(RuntimeError):
    pass


class ModelInputBudgetError(RuntimeError):
    """A route input cannot fit within its configured request budget."""


class ModelPolicyViolationError(RuntimeError):
    """A structurally valid response violated deterministic product policy."""


class ModelRoutesExhaustedError(ModelUnavailableError):
    """All configured routes failed without exposing upstream error text."""

    def __init__(self, routing: "ModelRoutingProvenance"):
        super().__init__("All configured model routes failed")
        self.routing = routing


@dataclass(frozen=True)
class ModelProvenance:
    provider: str
    model: str
    workload: str
    prompt_version: str
    schema_version: str
    execution_mode: str
    correlation_id: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    request_hash: str
    repair_attempted: bool
    cached: bool


@dataclass(frozen=True)
class ModelRoutingProvenance:
    """Safe route-selection evidence persisted with each model result."""

    selected_route: Literal["primary", "fallback", "none"]
    fallback_attempted: bool
    primary_provider: str | None
    primary_model: str | None
    fallback_provider: str | None
    fallback_model: str | None
    primary_failure_code: str | None
    fallback_failure_code: str | None


def _safe_failure_code(error: Exception) -> str:
    if isinstance(error, ModelInputBudgetError):
        return "input_budget_exceeded"
    if isinstance(error, ModelPolicyViolationError):
        return "policy_violation"
    if isinstance(error, ModelContractError):
        return "contract_invalid"
    if isinstance(error, ModelUnavailableError):
        return "unavailable"
    return "failed"


def _supports_strict_json_schema(value: Any) -> bool:
    """Return whether every object follows Groq strict-schema requirements."""

    if isinstance(value, list):
        return all(_supports_strict_json_schema(item) for item in value)
    if not isinstance(value, dict):
        return True
    properties = value.get("properties")
    if properties is not None:
        if not isinstance(properties, dict):
            return False
        if value.get("additionalProperties") is not False:
            return False
        required = value.get("required")
        if not isinstance(required, list) or set(required) != set(properties):
            return False
    return all(_supports_strict_json_schema(item) for item in value.values())


_UNSUPPORTED_STRICT_SCHEMA_KEYS = {
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


def strict_provider_output_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Reduce Pydantic JSON Schema to Groq's conservative strict subset.

    Omitted constraints remain authoritative in local Pydantic and semantic
    validation after inference.
    """

    definitions = schema.get("$defs", {})

    def dereference(value: Any) -> Any:
        if isinstance(value, list):
            return [dereference(item) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            reference = value["$ref"]
            prefix = "#/$defs/"
            if not isinstance(reference, str) or not reference.startswith(prefix):
                raise ModelContractError(
                    "Model output schema contains an unsupported reference"
                )
            name = reference.removeprefix(prefix)
            if name not in definitions:
                raise ModelContractError(
                    "Model output schema contains an unknown reference"
                )
            merged = copy.deepcopy(definitions[name])
            merged.update({key: item for key, item in value.items() if key != "$ref"})
            return dereference(merged)
        return {
            key: dereference(item)
            for key, item in value.items()
            if key != "$defs"
        }

    def reduce(value: Any, *, property_map: bool = False) -> Any:
        if isinstance(value, list):
            return [reduce(item) for item in value]
        if not isinstance(value, dict):
            return value
        if property_map:
            return {
                str(field_name): reduce(field_schema)
                for field_name, field_schema in value.items()
            }
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key in _UNSUPPORTED_STRICT_SCHEMA_KEYS:
                continue
            if key == "const":
                result["enum"] = [item]
                continue
            result[key] = reduce(item, property_map=key == "properties")
        if result.get("type") == "object":
            properties = result.get("properties")
            if not isinstance(properties, dict):
                raise ModelContractError(
                    "Strict model output objects require explicit properties"
                )
            result["additionalProperties"] = False
            result["required"] = list(properties)
        return result

    transformed = reduce(dereference(schema))
    if not isinstance(transformed, dict) or not _supports_strict_json_schema(
        transformed
    ):
        raise ModelContractError("Model output schema is not strict-compatible")
    return transformed


class StructuredModelClient:
    """A route-specific client.

    The caller supplies exactly one credential. This type has no fallback
    registry and therefore cannot cross the repository/Terraform trust boundary.
    """

    def __init__(
        self,
        *,
        provider: str,
        endpoint: str,
        model: str,
        api_key: str,
        workload: str,
        prompt_version: str,
        maximum_input_chars: int,
        maximum_output_tokens: int,
        timeout_seconds: float = 45.0,
        api_version: str = "2026-03-10",
        transport: httpx.BaseTransport | None = None,
        credential: Any = None,
        agent_name: str = "zeroops-architecture-advisor",
        agent_version: str = "3",
    ):
        self.provider = provider.strip().lower().replace("_", "-")
        self.endpoint = endpoint.strip().rstrip("/")
        self.model = model.strip()
        self.api_key = api_key.strip()
        self.workload = workload
        self.prompt_version = prompt_version
        self.maximum_input_chars = maximum_input_chars
        self.maximum_output_tokens = maximum_output_tokens
        self.timeout_seconds = timeout_seconds
        self.api_version = api_version.strip()
        self.transport = transport
        self.agent_name = agent_name
        self.agent_version = agent_version
        self.credential = credential
        if self.provider == "azure-foundry":
            parsed = urlparse(self.endpoint)
            if (parsed.scheme != "https" or not (parsed.hostname or "").endswith(".services.ai.azure.com")
                    or not parsed.path.startswith("/api/projects/") or parsed.username
                    or parsed.password or parsed.query or parsed.fragment or parsed.port):
                raise ValueError("Foundry agent requires an HTTPS project endpoint")
            if credential is None or not agent_name or not agent_version:
                raise ModelUnavailableError("Foundry agent identity and version are required")
            self.model = model.strip() or agent_name
            self.api_key = ""
            return
        if self.provider in {"azure-openai", "foundry-openai", "microsoft-foundry-openai"}:
            self.provider = "azure-openai"
            self.endpoint = _azure_openai_endpoint(self.endpoint)
            if not self.model:
                raise ValueError("Microsoft Foundry OpenAI requires a deployment name")
        else:
            raise ModelUnavailableError("Configured model provider is not supported")
        if not self.api_key:
            raise ModelUnavailableError(f"No credential configured for {workload}")

    def generate(
        self,
        *,
        system_instructions: str,
        input_value: dict[str, Any],
        output_model: type[T],
        schema_version: str,
        correlation_id: str | None = None,
        semantic_validator: Callable[[T], None] | None = None,
    ) -> tuple[T, ModelProvenance]:
        input_json = canonical_json_bytes(input_value).decode("utf-8")
        output_schema = output_model.model_json_schema()
        provider_output_schema = (
            strict_provider_output_schema(output_schema)
            if self.provider in {"azure-openai"}
            else output_schema
        )
        schema_json = canonical_json_bytes(provider_output_schema).decode("utf-8")
        strict_schema_enabled = self.provider in {"azure-openai"}
        bounded_system_instructions = (
            f"{system_instructions.strip()}\n\n"
            "Return exactly one JSON object matching the enforced JSON Schema. "
            "Do not add markdown or unknown fields."
        )
        if not strict_schema_enabled:
            bounded_system_instructions = f"{bounded_system_instructions}\n{schema_json}"
        request_character_count = len(bounded_system_instructions) + len(input_json)
        if strict_schema_enabled:
            # The schema is sent once through Foundry's strict response contract.
            request_character_count += len(schema_json)
        if request_character_count > self.maximum_input_chars:
            raise ModelInputBudgetError(
                "Structured model input exceeds the configured limit"
            )
        request_hash = sha256_bytes(
            canonical_json_bytes(
                {
                    "workload": self.workload,
                    "provider": self.provider,
                    "model": self.model,
                    "prompt_version": self.prompt_version,
                    "schema_version": schema_version,
                    "system_instructions": system_instructions,
                    "output_schema": output_schema,
                    "input": input_value,
                }
            )
        )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": bounded_system_instructions},
            {"role": "user", "content": input_json},
        ]
        started = time.perf_counter()
        raw, usage = self._request(messages, output_schema=provider_output_schema)
        repair_attempted = False
        try:
            result = self._validate(raw, output_model, semantic_validator)
        except (json.JSONDecodeError, ValidationError, ValueError) as initial_error:
            repair_attempted = True
            repair_messages = [
                *messages,
                {"role": "assistant", "content": raw[:12_000]},
                {
                    "role": "user",
                    "content": (
                        "Return one corrected JSON object only. Preserve only claims "
                        "supported by the original input and satisfy the supplied "
                        f"{schema_version} JSON Schema exactly."
                    ),
                },
            ]
            if (
                sum(len(message["content"]) for message in repair_messages)
                > self.maximum_input_chars
            ):
                raise ModelInputBudgetError(
                    "Model output could not be repaired within the configured input limit"
                )
            raw, repair_usage = self._request(
                repair_messages,
                output_schema=provider_output_schema,
            )
            usage["prompt_tokens"] += repair_usage["prompt_tokens"]
            usage["completion_tokens"] += repair_usage["completion_tokens"]
            try:
                result = self._validate(raw, output_model, semantic_validator)
            except (json.JSONDecodeError, ValidationError, ValueError) as final_error:
                raise ModelContractError("Model output failed strict validation") from final_error
        latency_ms = int((time.perf_counter() - started) * 1000)
        return result, ModelProvenance(
            provider=self.provider,
            model=self.model,
            workload=self.workload,
            prompt_version=self.prompt_version,
            schema_version=schema_version,
            execution_mode="model",
            correlation_id=correlation_id or str(uuid4()),
            input_tokens=usage["prompt_tokens"],
            output_tokens=usage["completion_tokens"],
            latency_ms=latency_ms,
            request_hash=request_hash,
            repair_attempted=repair_attempted,
            cached=False,
        )

    def _request(
        self,
        messages: list[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> tuple[str, dict[str, int]]:
        if self.provider == "azure-foundry":
            return self._request_foundry_agent(messages)
        return self._request_azure_openai(messages, output_schema=output_schema)

    def _request_foundry_agent(self, messages: list[dict[str, str]]) -> tuple[str, dict[str, int]]:
        from azure.ai.projects import AIProjectClient

        task = "TERRAFORM_GENERATION" if self.workload == "terraform-generation" else "REPOSITORY_ANALYSIS"
        try:
            with AIProjectClient(endpoint=self.endpoint, credential=self.credential, allow_preview=True) as project:
                with project.get_openai_client(agent_name=self.agent_name, timeout=self.timeout_seconds, max_retries=0) as client:
                    response = client.responses.create(
                        input=[{"role": "user", "content": f"TASK_TYPE: {task}\n" + json.dumps(messages)}],
                        extra_body={"agent_reference": {"type": "agent_reference", "name": self.agent_name, "version": self.agent_version}},
                        max_output_tokens=self.maximum_output_tokens,
                        store=False,
                    )
        except Exception as error:
            raise ModelUnavailableError("Foundry agent request failed") from error
        if response.status != "completed" or not response.output_text:
            raise ModelContractError("Foundry agent did not complete structured output")
        usage = response.usage
        return response.output_text, {
            "prompt_tokens": int(getattr(usage, "input_tokens", 0) or 0),
            "completion_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        }

    def _request_azure_openai(
        self,
        messages: list[dict[str, str]],
        *,
        output_schema: dict[str, Any],
    ) -> tuple[str, dict[str, int]]:
        """Call the Foundry v1 Responses API with Azure's api-key header."""
        payload = {
            "model": self.model,
            "input": messages,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "zeroops_structured_response",
                    "strict": True,
                    "schema": output_schema,
                }
            },
            "max_output_tokens": self.maximum_output_tokens,
            "store": False,
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.post(
                    f"{self.endpoint}/responses",
                    headers={
                        "api-key": self.api_key,
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                value = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise ModelUnavailableError("Microsoft Foundry OpenAI request failed") from error
        try:
            if value.get("status") in {"incomplete", "failed", "cancelled"}:
                raise ModelContractError("Microsoft Foundry returned an incomplete response")
            content = str(value.get("output_text") or "").strip()
            if not content:
                content = "\n".join(
                    part.get("text", "")
                    for item in value.get("output", []) if isinstance(item, dict)
                    for part in item.get("content", []) if isinstance(part, dict)
                    if part.get("type") == "output_text"
                ).strip()
            usage = value.get("usage") or {}
        except AttributeError as error:
            raise ModelContractError("Microsoft Foundry OpenAI returned an invalid response envelope") from error
        if not content:
            raise ModelContractError("Microsoft Foundry OpenAI returned an empty response")
        return content, {
            "prompt_tokens": max(0, int(usage.get("input_tokens") or 0)),
            "completion_tokens": max(0, int(usage.get("output_tokens") or 0)),
        }

    @staticmethod
    def _validate(
        raw: str,
        output_model: type[T],
        semantic_validator: Callable[[T], None] | None,
    ) -> T:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Model output root must be an object")
        result = output_model.model_validate(value)
        if semantic_validator is not None:
            try:
                semantic_validator(result)
            except ValueError as error:
                raise ModelPolicyViolationError(
                    "Model output violated deterministic policy"
                ) from error
        return result


def generate_with_provenance(
    *, primary: StructuredModelClient | None, system_instructions: str,
    input_value: dict[str, Any], output_model: type[T], schema_version: str,
    correlation_id: str | None = None,
    semantic_validator: Callable[[T], None] | None = None,
) -> tuple[T, ModelProvenance, ModelRoutingProvenance]:
    """Invoke the sole Foundry route and preserve honest failure provenance."""
    routing = dict(primary_provider=getattr(primary, "provider", None),
                   primary_model=getattr(primary, "model", None), fallback_attempted=False,
                   fallback_provider=None, fallback_model=None, fallback_failure_code=None)
    if primary is None:
        raise ModelRoutesExhaustedError(ModelRoutingProvenance(
            **routing, selected_route="none", primary_failure_code="not_configured"))
    try:
        result, provenance = primary.generate(
            system_instructions=system_instructions, input_value=input_value,
            output_model=output_model, schema_version=schema_version,
            correlation_id=correlation_id, semantic_validator=semantic_validator)
    except (ModelInputBudgetError, ModelPolicyViolationError, ModelUnavailableError, ModelContractError) as error:
        raise ModelRoutesExhaustedError(ModelRoutingProvenance(
            **routing, selected_route="none", primary_failure_code=_safe_failure_code(error))) from error
    return result, provenance, ModelRoutingProvenance(
        **routing, selected_route="primary", primary_failure_code=None,
    )

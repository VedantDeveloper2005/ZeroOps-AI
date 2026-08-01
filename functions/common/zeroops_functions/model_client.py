"""Strict structured inference clients and bounded workload-local failover."""

from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Literal, TypeVar
from uuid import uuid4

import httpx
from pydantic import BaseModel, ValidationError

from .security import canonical_json_bytes, sha256_bytes


T = TypeVar("T", bound=BaseModel)

_GITHUB_MODELS_ENDPOINT = "https://models.github.ai/inference"
_NVIDIA_ENDPOINT = "https://integrate.api.nvidia.com/v1"
_GROQ_ENDPOINT = "https://api.groq.com/openai/v1"
_GROQ_MODEL = "openai/gpt-oss-120b"


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
        if self.provider == "github-models":
            if self.endpoint != _GITHUB_MODELS_ENDPOINT:
                raise ValueError(
                    "GitHub Models endpoint must use the approved inference origin"
                )
            if not self.model.startswith(
                ("openai/", "microsoft/", "meta/", "mistral-ai/")
            ):
                raise ValueError(
                    "Model must be a publisher-qualified GitHub Models ID"
                )
        elif self.provider == "nvidia":
            if self.endpoint != _NVIDIA_ENDPOINT:
                raise ValueError(
                    "NVIDIA endpoint must use the approved inference origin"
                )
            if "/" not in self.model:
                raise ValueError(
                    "NVIDIA model must be a publisher-qualified catalog ID"
                )
        elif self.provider == "groq":
            if self.endpoint != _GROQ_ENDPOINT:
                raise ValueError("Groq endpoint must use the approved inference origin")
            if self.model != _GROQ_MODEL:
                raise ValueError("Groq fallback must use the approved GPT-OSS model")
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
            if self.provider == "groq"
            else output_schema
        )
        schema_json = canonical_json_bytes(provider_output_schema).decode("utf-8")
        strict_schema_enabled = self.provider == "groq"
        bounded_system_instructions = (
            f"{system_instructions.strip()}\n\n"
            "Return exactly one JSON object matching the enforced JSON Schema. "
            "Do not add markdown or unknown fields."
        )
        if not strict_schema_enabled:
            bounded_system_instructions = f"{bounded_system_instructions}\n{schema_json}"
        request_character_count = len(bounded_system_instructions) + len(input_json)
        if strict_schema_enabled:
            # The schema is sent once through Groq's strict response contract.
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
            if self.provider == "groq":
                # The free-plan backup gets one strict-schema attempt. Avoid a
                # hidden second request that could unexpectedly double token use.
                raise ModelContractError(
                    "Model output failed strict validation"
                ) from initial_error
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
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "stream": False,
        }
        if self.provider == "groq":
            payload["max_completion_tokens"] = self.maximum_output_tokens
        else:
            payload["max_tokens"] = self.maximum_output_tokens
        if self.provider == "github-models":
            headers["Accept"] = "application/vnd.github+json"
            if self.api_version:
                headers["X-GitHub-Api-Version"] = self.api_version
            payload["response_format"] = {"type": "json_object"}
        elif self.provider == "groq" and _supports_strict_json_schema(output_schema):
            headers["Accept"] = "application/json"
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "zeroops_structured_response",
                    "strict": True,
                    "schema": output_schema,
                },
            }
        else:
            # NVIDIA Build's OpenAI-compatible catalog does not guarantee
            # response_format support for every model. The schema is already
            # embedded in the bounded system prompt and validation stays local.
            headers["Accept"] = "application/json"
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = client.post(
                    f"{self.endpoint}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                value = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise ModelUnavailableError("Configured model provider request failed") from error
        try:
            choice = value["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ModelContractError("Model provider returned an invalid response envelope") from error
        finish_reason = choice.get("finish_reason")
        if finish_reason not in {None, "stop"}:
            raise ModelContractError("Model provider returned an incomplete response")
        usage = value.get("usage") or {}
        return str(content), {
            "prompt_tokens": max(0, int(usage.get("prompt_tokens") or 0)),
            "completion_tokens": max(0, int(usage.get("completion_tokens") or 0)),
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


def generate_with_fallback(
    *,
    primary: StructuredModelClient | None,
    fallback: StructuredModelClient | None,
    system_instructions: str,
    input_value: dict[str, Any],
    output_model: type[T],
    schema_version: str,
    correlation_id: str | None = None,
    semantic_validator: Callable[[T], None] | None = None,
) -> tuple[T, ModelProvenance, ModelRoutingProvenance]:
    """Try one explicit backup route without crossing the workload boundary."""

    primary_failure_code: str | None = None
    if primary is not None:
        try:
            result, provenance = primary.generate(
                system_instructions=system_instructions,
                input_value=input_value,
                output_model=output_model,
                schema_version=schema_version,
                correlation_id=correlation_id,
                semantic_validator=semantic_validator,
            )
            return result, provenance, ModelRoutingProvenance(
                selected_route="primary",
                fallback_attempted=False,
                primary_provider=getattr(primary, "provider", None),
                primary_model=getattr(primary, "model", None),
                fallback_provider=getattr(fallback, "provider", None),
                fallback_model=getattr(fallback, "model", None),
                primary_failure_code=None,
                fallback_failure_code=None,
            )
        except (ModelInputBudgetError, ModelPolicyViolationError) as error:
            raise ModelRoutesExhaustedError(
                ModelRoutingProvenance(
                    selected_route="none",
                    fallback_attempted=False,
                    primary_provider=getattr(primary, "provider", None),
                    primary_model=getattr(primary, "model", None),
                    fallback_provider=getattr(fallback, "provider", None),
                    fallback_model=getattr(fallback, "model", None),
                    primary_failure_code=_safe_failure_code(error),
                    fallback_failure_code="not_attempted",
                )
            ) from error
        except (ModelUnavailableError, ModelContractError) as error:
            primary_failure_code = _safe_failure_code(error)
    else:
        primary_failure_code = "not_configured"

    if fallback is not None:
        try:
            result, provenance = fallback.generate(
                system_instructions=system_instructions,
                input_value=input_value,
                output_model=output_model,
                schema_version=schema_version,
                correlation_id=correlation_id,
                semantic_validator=semantic_validator,
            )
            return result, provenance, ModelRoutingProvenance(
                selected_route="fallback",
                fallback_attempted=True,
                primary_provider=getattr(primary, "provider", None),
                primary_model=getattr(primary, "model", None),
                fallback_provider=getattr(fallback, "provider", None),
                fallback_model=getattr(fallback, "model", None),
                primary_failure_code=primary_failure_code,
                fallback_failure_code=None,
            )
        except (ModelInputBudgetError, ModelPolicyViolationError) as error:
            fallback_failure_code = _safe_failure_code(error)
        except (ModelUnavailableError, ModelContractError) as error:
            fallback_failure_code = _safe_failure_code(error)
    else:
        fallback_failure_code = "not_configured"

    raise ModelRoutesExhaustedError(
        ModelRoutingProvenance(
            selected_route="none",
            fallback_attempted=fallback is not None,
            primary_provider=getattr(primary, "provider", None),
            primary_model=getattr(primary, "model", None),
            fallback_provider=getattr(fallback, "provider", None),
            fallback_model=getattr(fallback, "model", None),
            primary_failure_code=primary_failure_code,
            fallback_failure_code=fallback_failure_code,
        )
    )

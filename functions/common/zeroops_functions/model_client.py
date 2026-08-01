"""Strict structured inference client for a single configured AI workload."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar
from uuid import uuid4

import httpx
from pydantic import BaseModel, ValidationError

from .security import canonical_json_bytes, sha256_bytes


T = TypeVar("T", bound=BaseModel)

_GITHUB_MODELS_ENDPOINT = "https://models.github.ai/inference"
_NVIDIA_ENDPOINT = "https://integrate.api.nvidia.com/v1"


class ModelUnavailableError(RuntimeError):
    pass


class ModelContractError(RuntimeError):
    pass


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
        schema_json = canonical_json_bytes(output_schema).decode("utf-8")
        bounded_system_instructions = (
            f"{system_instructions.strip()}\n\n"
            "Return exactly one JSON object matching this JSON Schema. "
            "Do not add markdown or unknown fields.\n"
            f"{schema_json}"
        )
        if (
            len(bounded_system_instructions)
            + len(input_json)
            > self.maximum_input_chars
        ):
            raise ModelContractError("Structured model input exceeds the configured limit")
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
        raw, usage = self._request(messages)
        repair_attempted = False
        try:
            result = self._validate(raw, output_model, semantic_validator)
        except (json.JSONDecodeError, ValidationError, ValueError):
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
                raise ModelContractError(
                    "Model output could not be repaired within the configured input limit"
                )
            raw, repair_usage = self._request(repair_messages)
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

    def _request(self, messages: list[dict[str, str]]) -> tuple[str, dict[str, int]]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.maximum_output_tokens,
            "temperature": 0,
            "stream": False,
        }
        if self.provider == "github-models":
            headers["Accept"] = "application/vnd.github+json"
            if self.api_version:
                headers["X-GitHub-Api-Version"] = self.api_version
            payload["response_format"] = {"type": "json_object"}
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
            semantic_validator(result)
        return result

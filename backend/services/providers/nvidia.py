"""NVIDIA Build API provider using its OpenAI-compatible inference endpoint.

Configuration requirements
--------------------------
- api_key must not be empty.
- endpoint must use HTTPS and the host must be ``integrate.api.nvidia.com``.
- endpoint is normalized to ``https://integrate.api.nvidia.com/v1``.
- model must not be empty.

Security requirements
---------------------
- The API key is never included in repr, logs, errors, exceptions, telemetry,
  provenance, or API responses. The ``ProviderConfiguration`` dataclass already
  marks ``api_key`` with ``repr=False``; this module never formats or logs it.
- All SDK exceptions are converted to a safe generic message so that upstream
  error text (which may include headers or request metadata) is never surfaced
  in product logs or API responses.
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlparse

from openai import OpenAI

from backend.services.providers.base import (
    ProviderConfiguration,
    ProviderConfigurationError,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)

# The only accepted inference host for this provider.
_NVIDIA_INFERENCE_HOST = "integrate.api.nvidia.com"
_NVIDIA_NORMALIZED_ENDPOINT = "https://integrate.api.nvidia.com/v1"


def _validated_endpoint(value: str) -> str:
    """Return the canonical NVIDIA endpoint or raise ProviderConfigurationError."""
    endpoint = value.strip().rstrip("/")
    parsed = urlparse(endpoint)
    if parsed.scheme != "https":
        raise ProviderConfigurationError(
            "NVIDIA provider endpoint must use HTTPS."
        )
    if not parsed.netloc:
        raise ProviderConfigurationError(
            "NVIDIA provider endpoint must be a valid HTTPS URL."
        )
    if parsed.netloc.lower() != _NVIDIA_INFERENCE_HOST:
        raise ProviderConfigurationError(
            f"NVIDIA provider routes must use the {_NVIDIA_INFERENCE_HOST} host."
        )
    # Always normalize to the canonical path regardless of what was supplied.
    return _NVIDIA_NORMALIZED_ENDPOINT


class NvidiaProvider:
    """Structured model provider backed by the NVIDIA Build OpenAI-compatible API.

    The ZeroOps model gateway remains authoritative for JSON parsing, schema
    validation, and the single repair attempt. This provider is responsible only
    for making the network call and returning raw text with token counts.
    """

    name = "nvidia"

    def __init__(
        self,
        configuration: ProviderConfiguration,
        *,
        client: Any | None = None,
    ) -> None:
        if not configuration.api_key.strip():
            raise ProviderConfigurationError(
                "The selected AI workload has no NVIDIA API credential."
            )
        if not configuration.model.strip():
            raise ProviderConfigurationError(
                "The selected AI workload has no NVIDIA model configured."
            )

        endpoint = _validated_endpoint(configuration.endpoint)
        # Rebuild the configuration with the normalized endpoint so that
        # provenance always records the canonical host, not a caller-supplied
        # variant.
        self.configuration = ProviderConfiguration(
            provider=configuration.provider,
            endpoint=endpoint,
            model=configuration.model.strip(),
            api_key=configuration.api_key.strip(),
            agent_name=configuration.agent_name,
            api_version=configuration.api_version,
            timeout_seconds=configuration.timeout_seconds,
            max_input_chars=configuration.max_input_chars,
            max_output_tokens=configuration.max_output_tokens,
            prompt_version=configuration.prompt_version,
        )
        # The OpenAI SDK is used only as a transport. max_retries=0 ensures
        # that all retry and repair decisions stay with the ZeroOps gateway.
        self._client: Any = client or OpenAI(
            api_key=self.configuration.api_key,
            base_url=self.configuration.endpoint,
            timeout=self.configuration.timeout_seconds,
            max_retries=0,
        )

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Call the NVIDIA inference endpoint and return a raw text response.

        The gateway is responsible for JSON parsing, Pydantic validation, and
        the single repair attempt. This method only enforces the input budget,
        constructs the bounded system prompt with the schema, and makes the
        network call.
        """
        schema_text = json.dumps(
            request.output_schema,
            sort_keys=True,
            separators=(",", ":"),
        )
        # Bounded system prompt: instruction + full JSON Schema in one message.
        bounded_system_prompt = (
            f"{request.system_prompt}\n\n"
            "Return ONLY a single JSON object matching this JSON Schema exactly. "
            "Do not add any commentary, markdown fences, explanations, or extra fields.\n"
            f"{schema_text}"
        )
        if (
            len(bounded_system_prompt) + len(request.user_prompt)
            > self.configuration.max_input_chars
        ):
            raise ProviderError("AI request exceeds the configured input budget.")

        max_output_tokens = min(
            request.max_output_tokens,
            self.configuration.max_output_tokens,
        )

        started = time.perf_counter()
        try:
            response = self._client.chat.completions.create(
                model=self.configuration.model,
                messages=[
                    {"role": "system", "content": bounded_system_prompt},
                    {"role": "user", "content": request.user_prompt},
                ],
                temperature=request.temperature,
                max_tokens=max_output_tokens,
                stream=False,
            )
        except Exception as error:
            # Provider SDK exceptions may contain request metadata, headers,
            # or partial response text. Never include them in user-visible
            # errors, logs, or API responses.
            raise ProviderError("NVIDIA inference failed.") from error

        try:
            choices = getattr(response, "choices", None)
            content = str(
                choices[0].message.content or "" if choices else ""
            ).strip()
            usage = getattr(response, "usage", None)
            input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        except Exception as error:
            raise ProviderError("NVIDIA returned an invalid response.") from error
        if not content:
            raise ProviderError("NVIDIA returned an empty response.")

        return ProviderResponse(
            content=content,
            model=str(
                getattr(response, "model", None) or self.configuration.model
            ),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=max(0, round((time.perf_counter() - started) * 1_000)),
        )

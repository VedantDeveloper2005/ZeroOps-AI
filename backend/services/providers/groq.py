"""Groq provider for the approved GPT-OSS fallback route.

Only Groq's canonical OpenAI-compatible HTTPS endpoint and the reviewed
``openai/gpt-oss-120b`` model are accepted. The provider deliberately has no
knowledge of primary-route credentials: each workload supplies its own
fallback credential through ``ProviderConfiguration``.
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
    ProviderCredentialUnavailableError,
    ProviderError,
    ProviderInputBudgetError,
    ProviderRequest,
    ProviderResponse,
)


GROQ_API_ENDPOINT = "https://api.groq.com/openai/v1"
GROQ_GPT_OSS_MODEL = "openai/gpt-oss-120b"
_GROQ_API_HOST = "api.groq.com"
_GROQ_API_PATH = "/openai/v1"


def _validated_endpoint(value: str) -> str:
    """Require Groq's exact API origin and canonical OpenAI-compatible path."""
    endpoint = value.strip()
    try:
        parsed = urlparse(endpoint)
        port = parsed.port
    except ValueError as error:
        raise ProviderConfigurationError(
            "Groq provider endpoint must be a valid HTTPS URL."
        ) from error

    if parsed.scheme != "https":
        raise ProviderConfigurationError("Groq provider endpoint must use HTTPS.")
    if (
        parsed.hostname != _GROQ_API_HOST
        or parsed.netloc.lower() != _GROQ_API_HOST
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ProviderConfigurationError(
            f"Groq provider routes must use the exact {_GROQ_API_HOST} origin."
        )
    if parsed.path.rstrip("/") != _GROQ_API_PATH:
        raise ProviderConfigurationError(
            f"Groq provider endpoint must use the {_GROQ_API_PATH} path."
        )
    if parsed.params or parsed.query or parsed.fragment:
        raise ProviderConfigurationError(
            "Groq provider endpoint cannot include parameters, a query, or a fragment."
        )
    return GROQ_API_ENDPOINT


class GroqProvider:
    """Structured fallback provider backed by Groq GPT-OSS 120B."""

    name = "groq"

    def __init__(
        self,
        configuration: ProviderConfiguration,
        *,
        client: Any | None = None,
    ) -> None:
        if not configuration.api_key.strip():
            raise ProviderCredentialUnavailableError(
                "The selected AI fallback route has no Groq API credential."
            )
        if configuration.model.strip() != GROQ_GPT_OSS_MODEL:
            raise ProviderConfigurationError(
                f"Groq fallback routes must use the {GROQ_GPT_OSS_MODEL} model."
            )

        endpoint = _validated_endpoint(configuration.endpoint)
        self.configuration = ProviderConfiguration(
            provider=configuration.provider,
            endpoint=endpoint,
            model=GROQ_GPT_OSS_MODEL,
            api_key=configuration.api_key.strip(),
            agent_name=configuration.agent_name,
            api_version=configuration.api_version,
            timeout_seconds=configuration.timeout_seconds,
            max_input_chars=configuration.max_input_chars,
            max_output_tokens=configuration.max_output_tokens,
            prompt_version=configuration.prompt_version,
        )
        # All retry and repair decisions remain visible and bounded in the
        # model gateway; the transport must never make hidden retries.
        self._client: Any = client or OpenAI(
            api_key=self.configuration.api_key,
            base_url=self.configuration.endpoint,
            timeout=self.configuration.timeout_seconds,
            max_retries=0,
        )

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        schema_text = json.dumps(
            request.output_schema,
            sort_keys=True,
            separators=(",", ":"),
        )
        bounded_system_prompt = (
            f"{request.system_prompt}\n\n"
            "Return ONLY the JSON object required by the response schema. "
            "Do not add commentary, markdown fences, or explanations."
        )
        if (
            len(bounded_system_prompt)
            + len(request.user_prompt)
            + len(schema_text)
            > self.configuration.max_input_chars
        ):
            raise ProviderInputBudgetError(
                "AI request exceeds the configured input budget."
            )

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
                # The gateway supplies a conservative strict-schema subset;
                # Pydantic remains authoritative for full product validation.
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.schema_name,
                        "schema": request.output_schema,
                        "strict": True,
                    },
                },
                temperature=request.temperature,
                max_completion_tokens=max_output_tokens,
                stream=False,
            )
        except Exception as error:
            # SDK exceptions can contain request metadata or headers. Never
            # expose their text through product errors, logs, or provenance.
            raise ProviderError("Groq inference failed.") from error

        try:
            choices = getattr(response, "choices", None)
            content = str(
                choices[0].message.content or "" if choices else ""
            ).strip()
            usage = getattr(response, "usage", None)
            input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        except Exception as error:
            raise ProviderError("Groq returned an invalid response.") from error
        if not content:
            raise ProviderError("Groq returned an empty response.")

        return ProviderResponse(
            content=content,
            model=str(getattr(response, "model", None) or self.configuration.model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=max(0, round((time.perf_counter() - started) * 1_000)),
        )

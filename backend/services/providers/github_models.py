"""GitHub Models provider using its current OpenAI-compatible inference API."""

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


CURRENT_GITHUB_MODELS_ENDPOINT = "https://models.github.ai/inference"


def _validated_endpoint(value: str) -> str:
    endpoint = value.strip().rstrip("/")
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ProviderConfigurationError("GitHub Models endpoint must be an HTTPS URL.")
    if parsed.netloc.lower() != "models.github.ai":
        raise ProviderConfigurationError(
            "GitHub Models routes must use the models.github.ai inference host."
        )
    if not parsed.path.rstrip("/").endswith("/inference"):
        raise ProviderConfigurationError(
            "GitHub Models endpoint must end with /inference."
        )
    return endpoint


class GitHubModelsProvider:
    name = "github-models"

    def __init__(
        self,
        configuration: ProviderConfiguration,
        *,
        client: Any | None = None,
    ) -> None:
        if not configuration.api_key:
            raise ProviderCredentialUnavailableError(
                "The selected AI workload has no GitHub Models credential."
            )
        if "/" not in configuration.model:
            raise ProviderConfigurationError(
                "GitHub Models requires a catalog-qualified model ID such as openai/gpt-4o."
            )

        endpoint = _validated_endpoint(configuration.endpoint)
        self.configuration = ProviderConfiguration(
            provider=configuration.provider,
            endpoint=endpoint,
            model=configuration.model,
            api_key=configuration.api_key,
            agent_name=configuration.agent_name,
            api_version=configuration.api_version,
            timeout_seconds=configuration.timeout_seconds,
            max_input_chars=configuration.max_input_chars,
            max_output_tokens=configuration.max_output_tokens,
            prompt_version=configuration.prompt_version,
        )
        self._client = client or OpenAI(
            api_key=self.configuration.api_key,
            base_url=self.configuration.endpoint,
            timeout=self.configuration.timeout_seconds,
            # Gateway-level repair is explicit and metered. Avoid hidden model
            # retries that could unexpectedly duplicate inference charges.
            max_retries=0,
            default_headers={
                "Accept": "application/vnd.github+json",
                **(
                    {"X-GitHub-Api-Version": self.configuration.api_version}
                    if self.configuration.api_version
                    else {}
                ),
            },
        )

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        schema_text = json.dumps(
            request.output_schema,
            sort_keys=True,
            separators=(",", ":"),
        )
        bounded_system_prompt = (
            f"{request.system_prompt}\n\n"
            "Return only a JSON object matching this JSON Schema exactly:\n"
            f"{schema_text}"
        )
        if len(bounded_system_prompt) + len(request.user_prompt) > self.configuration.max_input_chars:
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
                response_format={"type": "json_object"},
                temperature=request.temperature,
                max_tokens=max_output_tokens,
            )
        except Exception as error:
            # Provider exceptions can include request metadata. Never propagate
            # their text into product logs, API responses, or history.
            raise ProviderError("GitHub Models inference failed.") from error

        content = str(response.choices[0].message.content or "").strip()
        if not content:
            raise ProviderError("GitHub Models returned an empty response.")

        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        return ProviderResponse(
            content=content,
            model=str(getattr(response, "model", None) or self.configuration.model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=max(0, round((time.perf_counter() - started) * 1_000)),
        )

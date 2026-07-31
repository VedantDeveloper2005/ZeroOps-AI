"""Future Microsoft Foundry provider authenticated with managed identity.

The SDK imports are intentionally lazy so GitHub Models testing does not add a
Foundry runtime dependency. This provider supports a prompt agent reference or
a direct Foundry model deployment through the same structured gateway.
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlparse

from backend.services.providers.base import (
    ProviderConfiguration,
    ProviderConfigurationError,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)


class AzureFoundryProvider:
    name = "azure-foundry"

    def __init__(
        self,
        configuration: ProviderConfiguration,
        *,
        openai_client: Any | None = None,
    ) -> None:
        parsed = urlparse(configuration.endpoint.strip())
        if parsed.scheme != "https" or not parsed.netloc:
            raise ProviderConfigurationError("Microsoft Foundry project endpoint must use HTTPS.")
        if configuration.api_key:
            raise ProviderConfigurationError(
                "Microsoft Foundry routes must use managed identity, not an API key."
            )
        if not configuration.agent_name and not configuration.model:
            raise ProviderConfigurationError(
                "Microsoft Foundry requires an agent name or model deployment."
            )

        self.configuration = configuration
        self._openai_client = openai_client

    def _client(self):
        if self._openai_client is not None:
            return self._openai_client
        try:
            from azure.ai.projects import AIProjectClient
            from azure.identity import DefaultAzureCredential
        except ImportError as error:
            raise ProviderConfigurationError(
                "The Microsoft Foundry SDK is not installed for this workload."
            ) from error

        project = AIProjectClient(
            endpoint=self.configuration.endpoint,
            credential=DefaultAzureCredential(
                exclude_interactive_browser_credential=True,
            ),
        )
        self._openai_client = project.get_openai_client()
        return self._openai_client

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        schema_text = json.dumps(
            request.output_schema,
            sort_keys=True,
            separators=(",", ":"),
        )
        if (
            len(request.system_prompt)
            + len(request.user_prompt)
            + len(schema_text)
            > self.configuration.max_input_chars
        ):
            raise ProviderError("AI request exceeds the configured input budget.")

        text_format = {
            "type": "json_schema",
            "name": request.schema_name,
            "strict": True,
            "schema": request.output_schema,
        }
        payload: dict[str, Any] = {
            "input": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "text": {"format": text_format},
            "max_output_tokens": min(
                request.max_output_tokens,
                self.configuration.max_output_tokens,
            ),
            "store": False,
        }
        if self.configuration.agent_name:
            payload["extra_body"] = {
                "agent_reference": {
                    "type": "agent_reference",
                    "name": self.configuration.agent_name,
                }
            }
        else:
            payload["model"] = self.configuration.model

        started = time.perf_counter()
        try:
            response = self._client().responses.create(**payload)
        except Exception as error:
            raise ProviderError("Microsoft Foundry inference failed.") from error

        content = str(getattr(response, "output_text", "") or "").strip()
        if not content:
            raise ProviderError("Microsoft Foundry returned an empty response.")

        usage = getattr(response, "usage", None)
        return ProviderResponse(
            content=content,
            model=str(getattr(response, "model", None) or self.configuration.model or self.configuration.agent_name),
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            latency_ms=max(0, round((time.perf_counter() - started) * 1_000)),
        )

"""Microsoft Foundry / Azure OpenAI v1 provider using a deployment API key.

This route is intentionally distinct from :mod:`azure_foundry`, which invokes
Foundry prompt agents with managed identity.  ``azure-openai`` calls a model
deployment's OpenAI-compatible ``/openai/v1`` endpoint with the workload-local
API key.  This is the default provider for both workloads.
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


def _validated_endpoint(value: str) -> str:
    """Normalize an Azure OpenAI resource URL to its v1 OpenAI endpoint."""
    endpoint = value.strip().rstrip("/")
    try:
        parsed = urlparse(endpoint)
        port = parsed.port
    except ValueError as error:
        raise ProviderConfigurationError(
            "Microsoft Foundry OpenAI endpoint must be a valid HTTPS URL."
        ) from error

    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not hostname.endswith(".openai.azure.com"):
        raise ProviderConfigurationError(
            "Microsoft Foundry OpenAI routes must use an HTTPS *.openai.azure.com endpoint."
        )
    if (
        port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ProviderConfigurationError(
            "Microsoft Foundry OpenAI endpoint cannot include credentials, a port, parameters, a query, or a fragment."
        )
    if parsed.path.rstrip("/") not in {"", "/openai/v1"}:
        raise ProviderConfigurationError(
            "Microsoft Foundry OpenAI endpoint must end at /openai/v1."
        )
    return f"https://{hostname}/openai/v1"


class AzureOpenAIProvider:
    """Structured provider for a Microsoft Foundry Azure OpenAI deployment."""

    name = "azure-openai"

    def __init__(
        self,
        configuration: ProviderConfiguration,
        *,
        client: Any | None = None,
    ) -> None:
        if not configuration.api_key.strip():
            raise ProviderCredentialUnavailableError(
                "The selected AI workload has no Microsoft Foundry OpenAI API key."
            )
        if not configuration.model.strip():
            raise ProviderConfigurationError(
                "The selected AI workload has no Microsoft Foundry OpenAI deployment name."
            )
        if configuration.agent_name.strip():
            raise ProviderConfigurationError(
                "Microsoft Foundry OpenAI deployment routes cannot use an agent name."
            )

        self.configuration = ProviderConfiguration(
            provider="azure-openai",
            endpoint=_validated_endpoint(configuration.endpoint),
            model=configuration.model.strip(),
            api_key=configuration.api_key.strip(),
            timeout_seconds=configuration.timeout_seconds,
            max_input_chars=configuration.max_input_chars,
            max_output_tokens=configuration.max_output_tokens,
            prompt_version=configuration.prompt_version,
        )
        # The v1 endpoint uses the standard OpenAI SDK. max_retries stays zero
        # so retries and the one repair attempt remain visible in ModelGateway.
        self._client: Any = client or OpenAI(
            api_key=self.configuration.api_key,
            base_url=self.configuration.endpoint,
            # Azure documents API-key authentication with the ``api-key``
            # header. The OpenAI SDK also supplies its compatibility auth
            # header; Azure prioritizes this explicit API-key header.
            default_headers={"api-key": self.configuration.api_key},
            timeout=self.configuration.timeout_seconds,
            max_retries=0,
        )

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        schema_text = json.dumps(request.output_schema, sort_keys=True, separators=(",", ":"))
        if (
            len(request.system_prompt) + len(request.user_prompt) + len(schema_text)
            > self.configuration.max_input_chars
        ):
            raise ProviderInputBudgetError("AI request exceeds the configured input budget.")

        started = time.perf_counter()
        try:
            response = self._client.responses.create(
                model=self.configuration.model,
                input=[
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": request.user_prompt},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": request.schema_name,
                        "strict": True,
                        "schema": request.output_schema,
                    }
                },
                max_output_tokens=min(
                    request.max_output_tokens, self.configuration.max_output_tokens
                ),
                store=False,
            )
        except Exception as error:
            raise ProviderError("Microsoft Foundry OpenAI inference failed.") from error

        try:
            content = str(getattr(response, "output_text", "") or "").strip()
            usage = getattr(response, "usage", None)
            input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        except Exception as error:
            raise ProviderError(
                "Microsoft Foundry OpenAI returned an invalid response."
            ) from error
        if not content:
            raise ProviderError("Microsoft Foundry OpenAI returned an empty response.")

        return ProviderResponse(
            content=content,
            model=str(getattr(response, "model", None) or self.configuration.model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=max(0, round((time.perf_counter() - started) * 1_000)),
        )

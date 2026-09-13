"""Microsoft Foundry provider authenticated with managed identity / DefaultAzureCredential.

Invokes the pre-configured Microsoft Foundry Prompt Agent through an agent-bound
client so server-side instructions, File Search (zeroops-knowledge vector store),
and Web Search are actively executed by the agent runtime.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import urlparse

from backend.services.providers.base import (
    ProviderConfiguration,
    ProviderConfigurationError,
    ProviderCredentialUnavailableError,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)

logger = logging.getLogger("zeroops.foundry")
ai_logger = logging.getLogger("zeroops.ai.observability")


def extract_annotations(response: Any) -> list[dict[str, Any]]:
    """Extract tool annotations and citations from a Foundry response object."""
    def field(obj, name, default=None):
        return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)

    annotations = []
    def collect(node):
        for ann in field(node, "annotations", []) or []:
            annotations.append({
                "type": str(field(ann, "type") or "citation"),
                "url": field(ann, "url"),
                "title": field(ann, "title") or field(ann, "filename"),
                "text": field(ann, "text") or field(ann, "quote"),
                "file_id": field(ann, "file_id"),
            })
        for key in ("output", "content"):
            for child in field(node, key, []) or []:
                if not isinstance(child, str):
                    collect(child)
    collect(response)
    return annotations


class AzureFoundryProvider:
    name = "azure-foundry"

    def __init__(
        self,
        configuration: ProviderConfiguration,
        *,
        openai_client: Any | None = None,
        project_client: Any | None = None,
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
        self._project_client = project_client

    def _client(self):
        if self._openai_client is not None:
            return self._openai_client
        try:
            from azure.ai.projects import AIProjectClient
            from backend.services.foundry_identity import foundry_credential
        except ImportError as error:
            raise ProviderConfigurationError(
                "The Microsoft Foundry SDK (azure-ai-projects) is not installed."
            ) from error

        try:
            credential = foundry_credential()
            if self._project_client is None:
                self._project_client = AIProjectClient(
                    endpoint=self.configuration.endpoint,
                    credential=credential,
                    allow_preview=True,
                )

            self._openai_client = self._project_client.get_openai_client(
                agent_name=self.configuration.agent_name or None,
                timeout=self.configuration.timeout_seconds,
                max_retries=0,
            )
        except Exception as error:
            error_str = str(error)
            if "Authentication" in error_str or "Credential" in error_str:
                raise ProviderCredentialUnavailableError(
                    "Azure authentication unavailable for Microsoft Foundry."
                ) from error
            raise ProviderConfigurationError(
                f"Failed to initialize Microsoft Foundry client: {error}"
            ) from error

        return self._openai_client

    def _invoke_with_retry(self, payload: dict[str, Any], max_retries: int = 2) -> Any:
        """Invoke Foundry responses API with bounded exponential backoff for transient errors."""
        client = self._client()
        attempt = 0
        backoff_s = 1.0

        while True:
            try:
                return client.responses.create(**payload)
            except Exception as error:
                error_name = error.__class__.__name__
                error_str = str(error).lower()
                status_code = getattr(error, "status_code", None)

                # 401: Never retry authentication failures
                if status_code == 401 or "authentication" in error_str or "unauthorized" in error_str:
                    logger.error("Microsoft Foundry authentication failed (401).")
                    raise ProviderCredentialUnavailableError(
                        "Microsoft Foundry authentication failed. Ensure valid Azure CLI or Managed Identity credentials."
                    ) from error

                # 403: Never retry RBAC permission failures
                if status_code == 403 or "forbidden" in error_str or "permission" in error_str:
                    logger.error("Microsoft Foundry RBAC authorization failed (403).")
                    raise ProviderError(
                        "Microsoft Foundry access denied. Ensure the Azure identity holds the 'Azure AI Developer' role on the Foundry project."
                    ) from error

                # 404: Not found
                if status_code == 404 or "not found" in error_str:
                    logger.error("Microsoft Foundry resource or agent not found (404).")
                    raise ProviderConfigurationError(
                        f"Microsoft Foundry agent or project not found at endpoint: {self.configuration.endpoint}."
                    ) from error

                # 429: Rate limit — respect Retry-After if present
                if status_code == 429 or "rate limit" in error_str or "too many requests" in error_str:
                    if attempt < max_retries:
                        retry_after = getattr(error, "retry_after", None)
                        sleep_time = float(retry_after) if retry_after is not None else backoff_s
                        sleep_time = min(sleep_time, 15.0)
                        logger.warning(
                            "Microsoft Foundry rate limited (429). Retrying in %.1fs (attempt %d/%d).",
                            sleep_time, attempt + 1, max_retries
                        )
                        time.sleep(sleep_time)
                        attempt += 1
                        backoff_s *= 2.0
                        continue
                    raise ProviderError("Microsoft Foundry rate limit exceeded.") from error

                # 5xx or Timeout: Bounded retry
                if attempt < max_retries and (
                    status_code in {500, 502, 503, 504}
                    or "timeout" in error_str
                    or "connection" in error_str
                ):
                    logger.warning(
                        "Microsoft Foundry transient error (%s). Retrying in %.1fs (attempt %d/%d).",
                        error_name, backoff_s, attempt + 1, max_retries
                    )
                    time.sleep(backoff_s)
                    attempt += 1
                    backoff_s *= 2.0
                    continue

                logger.error("Microsoft Foundry inference failed with %s: %s", error_name, error)
                raise ProviderError("Microsoft Foundry inference failed.") from error

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

        if self.configuration.agent_name:
            combined_prompt = (
                f"{request.system_prompt}\n\n"
                f"{request.user_prompt}\n\n"
                f"Respond with ONLY a valid JSON object matching this schema:\n{schema_text}"
            )
            payload: dict[str, Any] = {
                "input": [
                    {"role": "user", "content": combined_prompt},
                ],
                "max_output_tokens": min(
                    request.max_output_tokens,
                    self.configuration.max_output_tokens,
                ),
                "store": False,
                "extra_body": {
                    "agent_reference": {
                        "type": "agent_reference",
                        "name": self.configuration.agent_name,
                        "version": getattr(self.configuration, "agent_version", "1") or "1",
                    }
                },
            }
        else:
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
                "model": self.configuration.model,
            }

        started = time.perf_counter()
        response = self._invoke_with_retry(payload)
        latency_ms = max(0, round((time.perf_counter() - started) * 1_000))

        content = str(getattr(response, "output_text", "") or "").strip()
        if not content:
            raise ProviderError("Microsoft Foundry returned an empty response.")

        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)

        ai_logger.info(
            "FOUNDRY_REQUEST | agent=%s | model=%s | latency_ms=%d | input_tokens=%d | output_tokens=%d",
            self.configuration.agent_name or "none",
            str(getattr(response, "model", None) or self.configuration.model or self.configuration.agent_name),
            latency_ms,
            input_tokens,
            output_tokens,
        )

        return ProviderResponse(
            content=content,
            model=str(getattr(response, "model", None) or self.configuration.model or self.configuration.agent_name),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )

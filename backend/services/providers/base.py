"""Provider-neutral request and response types for structured AI workloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class ProviderError(RuntimeError):
    """Safe provider error that never includes credentials or response bodies."""


class ProviderConfigurationError(ProviderError):
    """Raised when a workload-specific provider route is incomplete."""


@dataclass(frozen=True)
class ProviderConfiguration:
    provider: str
    endpoint: str
    model: str
    api_key: str = field(default="", repr=False)
    agent_name: str = ""
    api_version: str = ""
    timeout_seconds: int = 30
    max_input_chars: int = 60_000
    max_output_tokens: int = 1_600
    prompt_version: str = "v1"

    def __post_init__(self) -> None:
        if not 1 <= self.timeout_seconds <= 120:
            raise ProviderConfigurationError(
                "AI provider timeout must be between 1 and 120 seconds."
            )
        if not 1 <= self.max_input_chars <= 250_000:
            raise ProviderConfigurationError(
                "AI provider input budget must be between 1 and 250,000 characters."
            )
        if not 1 <= self.max_output_tokens <= 32_768:
            raise ProviderConfigurationError(
                "AI provider output budget must be between 1 and 32,768 tokens."
            )


@dataclass(frozen=True)
class ProviderRequest:
    system_prompt: str
    user_prompt: str
    schema_name: str
    output_schema: dict[str, Any]
    max_output_tokens: int
    temperature: float = 0.0


@dataclass(frozen=True)
class ProviderResponse:
    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


class StructuredModelProvider(Protocol):
    name: str
    configuration: ProviderConfiguration

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Return one structured model response without parsing product contracts."""

"""Structured model provider implementations."""

from backend.services.providers.azure_foundry import AzureFoundryProvider
from backend.services.providers.base import (
    ProviderConfiguration,
    ProviderConfigurationError,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    StructuredModelProvider,
)
from backend.services.providers.github_models import (
    CURRENT_GITHUB_MODELS_ENDPOINT,
    GitHubModelsProvider,
)

__all__ = [
    "AzureFoundryProvider",
    "CURRENT_GITHUB_MODELS_ENDPOINT",
    "GitHubModelsProvider",
    "ProviderConfiguration",
    "ProviderConfigurationError",
    "ProviderError",
    "ProviderRequest",
    "ProviderResponse",
    "StructuredModelProvider",
]

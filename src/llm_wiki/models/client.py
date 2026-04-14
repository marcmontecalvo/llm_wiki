"""Model client abstraction for LLM providers."""

import os
from abc import ABC, abstractmethod
from typing import Any

from llm_wiki.models.config import ModelProviderConfig


class ModelClientError(Exception):
    """Base exception for model client errors."""

    pass


class ModelClient(ABC):
    """Abstract base class for LLM model clients.

    This interface supports multiple LLM providers (OpenAI-compatible, Anthropic, etc.)
    with a unified API for the wiki system.
    """

    def __init__(self, config: ModelProviderConfig):
        """Initialize model client.

        Args:
            config: Model provider configuration
        """
        self.config = config
        self.provider = config.provider
        self.model = config.model
        self.temperature = config.temperature
        self.max_tokens = config.max_tokens
        self.timeout = config.timeout

    @abstractmethod
    def chat_completion(
        self,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Request a chat completion from the model.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            response_format: Optional response format specification (e.g., JSON schema)

        Returns:
            Model response as string

        Raises:
            ModelClientError: If the request fails
        """
        pass

    @abstractmethod
    def validate_config(self) -> None:
        """Validate the configuration and credentials.

        Raises:
            ModelClientError: If configuration is invalid or credentials missing
        """
        pass


class OpenAICompatibleClient(ModelClient):
    """Client for OpenAI-compatible APIs (OpenAI, Ollama, LM Studio, etc.)."""

    def __init__(self, config: ModelProviderConfig):
        """Initialize OpenAI-compatible client.

        Args:
            config: Model provider configuration

        Raises:
            ModelClientError: If configuration is invalid
        """
        super().__init__(config)
        self.api_key = self._get_api_key()
        self.base_url = self._get_base_url()

    def _get_api_key(self) -> str | None:
        """Get API key from environment.

        Returns:
            API key if found, None for local providers (Ollama, LM Studio)
        """
        # For local providers, API key is optional
        if self.provider in ("ollama", "lmstudio", "local"):
            return None

        # For OpenAI and others, try to get from environment
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key and self.provider == "openai":
            raise ModelClientError("OPENAI_API_KEY environment variable not set")

        return api_key

    def _get_base_url(self) -> str:
        """Get base URL for the API.

        Returns:
            Base URL for the provider
        """
        base_urls = {
            "openai": "https://api.openai.com/v1",
            "ollama": "http://localhost:11434/v1",
            "lmstudio": "http://localhost:1234/v1",
            "local": os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1"),
        }
        return base_urls.get(self.provider, os.environ.get("LLM_BASE_URL", ""))

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Request a chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            response_format: Optional response format (e.g., {"type": "json_object"})

        Returns:
            Model response content

        Raises:
            ModelClientError: If request fails or dependencies missing
        """
        raise NotImplementedError(
            "OpenAI client implementation requires openai package. "
            "This will be implemented when needed for extraction features."
        )

    def validate_config(self) -> None:
        """Validate configuration.

        Raises:
            ModelClientError: If configuration is invalid
        """
        if not self.base_url:
            raise ModelClientError(f"No base URL configured for provider: {self.provider}")

        if self.provider == "openai" and not self.api_key:
            raise ModelClientError("OpenAI provider requires OPENAI_API_KEY")


def create_model_client(config: ModelProviderConfig) -> ModelClient:
    """Factory function to create appropriate model client.

    Args:
        config: Model provider configuration

    Returns:
        Model client instance

    Raises:
        ModelClientError: If provider is unsupported
    """
    # For now, we only support OpenAI-compatible providers
    # Future: Add Anthropic, other providers as needed
    if config.provider in ("openai", "ollama", "lmstudio", "local"):
        return OpenAICompatibleClient(config)

    raise ModelClientError(f"Unsupported provider: {config.provider}")

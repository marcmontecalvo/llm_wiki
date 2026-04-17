"""Model client abstraction for LLM providers."""

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, cast

from openai import APIError, APITimeoutError, OpenAI, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from llm_wiki.models.config import ModelProviderConfig

logger = logging.getLogger(__name__)


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

        # Initialize OpenAI client
        self.client = OpenAI(
            api_key=self.api_key or "dummy-key",  # Local providers don't need real key
            base_url=self.base_url,
            timeout=self.timeout,
        )

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

    @retry(
        retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _make_api_call(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Make API call with retries.

        Args:
            messages: List of message dicts
            response_format: Optional response format

        Returns:
            Model response content

        Raises:
            ModelClientError: If request fails after retries
        """
        try:
            logger.debug(f"Calling {self.provider} model {self.model}")

            # Build request parameters
            params: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }

            if response_format:
                params["response_format"] = response_format

            # Make API call
            response = self.client.chat.completions.create(**params)

            # Extract content from response
            if not response.choices:
                raise ModelClientError("No choices in response")

            content = response.choices[0].message.content
            if content is None:
                raise ModelClientError("No content in response")

            logger.debug(f"Received response: {len(content)} characters")
            return cast(str, content)

        except (RateLimitError, APITimeoutError, APIError) as e:
            logger.warning(f"Retriable API error: {e}")
            raise  # Will be retried by tenacity
        except Exception as e:
            raise ModelClientError(f"API request failed: {e}") from e

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
            ModelClientError: If request fails after retries
        """
        return cast(str, self._make_api_call(messages, response_format))

    def validate_config(self) -> None:
        """Validate configuration.

        Raises:
            ModelClientError: If configuration is invalid
        """
        if not self.base_url:
            raise ModelClientError(f"No base URL configured for provider: {self.provider}")

        if self.provider == "openai" and not self.api_key:
            raise ModelClientError("OpenAI provider requires OPENAI_API_KEY")


class ClaudeAgentSDKClient(ModelClient):
    """Client backed by the Claude Agent SDK.

    Useful for users on Claude Max/Team/Enterprise subscriptions — extraction
    runs under the existing subscription rather than consuming separate API
    credits. The SDK is an optional dependency; import is deferred to
    ``__init__`` so users who don't need it aren't required to install it.
    """

    def __init__(self, config: ModelProviderConfig):
        """Initialize the Claude Agent SDK client.

        Args:
            config: Model provider configuration.

        Raises:
            ModelClientError: If the ``claude-agent-sdk`` package is not installed.
        """
        super().__init__(config)
        try:
            # Imported lazily — keep the package optional.
            import claude_agent_sdk  # type: ignore[import-not-found]
        except ImportError as e:
            raise ModelClientError(
                "claude-agent-sdk not installed. "
                "Install with: pip install 'llm-wiki[claude-agent]'"
            ) from e

        self._sdk = claude_agent_sdk

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Dispatch a chat completion via the Claude Agent SDK.

        The SDK exposes a ``query(prompt=...)`` entry point that returns an async
        iterator of messages. We concatenate system + user messages into a single
        prompt and collect the assistant's text response.

        Args:
            messages: Chat messages to send.
            response_format: Optional response format hint. When
                ``{"type": "json_object"}``, we suffix the prompt with an
                instruction to return JSON only — the SDK does not enforce
                structured output natively.

        Returns:
            Assistant response as a string.

        Raises:
            ModelClientError: If the SDK call fails.
        """
        import asyncio

        # Flatten messages to a single prompt string. The Claude Agent SDK's
        # ``query`` interface is designed for one prompt per turn, not a full
        # message history, but extractors in this project send a single user
        # message so flattening is safe.
        parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"[System]\n{content}")
            elif role == "assistant":
                parts.append(f"[Assistant]\n{content}")
            else:
                parts.append(content)
        prompt = "\n\n".join(p for p in parts if p)

        if response_format and response_format.get("type") == "json_object":
            prompt += (
                "\n\nReturn ONLY valid JSON matching the requested shape. "
                "Do not wrap the output in markdown fences or prose."
            )

        async def _run() -> str:
            chunks: list[str] = []
            # The SDK's ``query`` yields messages; collect assistant text blocks.
            async for message in self._sdk.query(prompt=prompt):
                content = getattr(message, "content", None)
                if isinstance(content, str):
                    chunks.append(content)
                    continue
                if isinstance(content, list):
                    for block in content:
                        text = getattr(block, "text", None)
                        if isinstance(text, str):
                            chunks.append(text)
            return "".join(chunks).strip()

        # Event-loop-safe dispatch. ``asyncio.run`` raises when called from a
        # thread that already has a running loop (e.g. inside Jupyter, FastAPI,
        # APScheduler's async executor). Detect a running loop and, if present,
        # spin the coroutine on a fresh loop in a worker thread.
        try:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                # No running loop — safe to use asyncio.run directly.
                result = asyncio.run(_run())
            else:
                import concurrent.futures

                def _in_thread() -> str:
                    return asyncio.run(_run())

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    result = pool.submit(_in_thread).result()
        except Exception as e:
            raise ModelClientError(f"Claude Agent SDK request failed: {e}") from e

        if not result:
            raise ModelClientError("Claude Agent SDK returned empty response")
        return result

    def validate_config(self) -> None:
        """Validate Claude Agent SDK configuration.

        The SDK authenticates via the Claude Code CLI session and does not
        require an API key. Import success is verified in ``__init__`` — if
        the SDK were missing, constructing the client would have already
        raised ``ModelClientError``, so there's nothing further to check here.
        """
        return None


def create_model_client(config: ModelProviderConfig) -> ModelClient:
    """Factory function to create appropriate model client.

    Args:
        config: Model provider configuration

    Returns:
        Model client instance

    Raises:
        ModelClientError: If provider is unsupported
    """
    if config.provider in ("openai", "ollama", "lmstudio", "local"):
        return OpenAICompatibleClient(config)
    if config.provider in ("claude_agent_sdk", "claude-agent-sdk", "claude_agent"):
        return ClaudeAgentSDKClient(config)

    raise ModelClientError(f"Unsupported provider: {config.provider}")

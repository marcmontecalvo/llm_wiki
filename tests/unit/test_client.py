"""Tests for LLM model client."""

from unittest.mock import Mock, patch

import pytest
from openai import APITimeoutError, RateLimitError

from llm_wiki.models.client import (
    ModelClientError,
    OpenAICompatibleClient,
    create_model_client,
)
from llm_wiki.models.config import ModelProviderConfig


class TestOpenAICompatibleClient:
    """Tests for OpenAICompatibleClient."""

    @pytest.fixture
    def openai_config(self) -> ModelProviderConfig:
        """Create OpenAI provider config."""
        return ModelProviderConfig(
            provider="openai",
            model="gpt-4",
            temperature=0.7,
            max_tokens=1000,
            timeout=30,
        )

    @pytest.fixture
    def local_config(self) -> ModelProviderConfig:
        """Create local provider config."""
        return ModelProviderConfig(
            provider="ollama",
            model="llama2",
            temperature=0.7,
            max_tokens=500,
            timeout=60,
        )

    def test_init_openai_without_api_key(self, openai_config: ModelProviderConfig):
        """Test OpenAI initialization without API key raises error."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ModelClientError, match="OPENAI_API_KEY"):
                OpenAICompatibleClient(openai_config)

    def test_init_openai_with_api_key(self, openai_config: ModelProviderConfig):
        """Test OpenAI initialization with API key."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test123"}):
            client = OpenAICompatibleClient(openai_config)

            assert client.api_key == "sk-test123"
            assert client.base_url == "https://api.openai.com/v1"
            assert client.model == "gpt-4"
            assert client.temperature == 0.7

    def test_init_local_provider(self, local_config: ModelProviderConfig):
        """Test local provider initialization (no API key required)."""
        client = OpenAICompatibleClient(local_config)

        assert client.api_key is None
        assert client.base_url == "http://localhost:11434/v1"
        assert client.model == "llama2"

    def test_chat_completion_success(self, local_config: ModelProviderConfig):
        """Test successful chat completion."""
        client = OpenAICompatibleClient(local_config)

        # Mock the OpenAI client
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Hello, world!"

        client.client.chat.completions.create = Mock(return_value=mock_response)

        # Call chat_completion
        messages = [{"role": "user", "content": "Hello"}]
        response = client.chat_completion(messages)

        assert response == "Hello, world!"
        client.client.chat.completions.create.assert_called_once()

    def test_chat_completion_with_response_format(self, local_config: ModelProviderConfig):
        """Test chat completion with JSON response format."""
        client = OpenAICompatibleClient(local_config)

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"result": "data"}'

        client.client.chat.completions.create = Mock(return_value=mock_response)

        messages = [{"role": "user", "content": "Generate JSON"}]
        response_format = {"type": "json_object"}
        response = client.chat_completion(messages, response_format)

        assert response == '{"result": "data"}'

        # Verify response_format was passed
        call_args = client.client.chat.completions.create.call_args
        assert call_args[1]["response_format"] == response_format

    def test_chat_completion_empty_choices(self, local_config: ModelProviderConfig):
        """Test error when API returns empty choices."""
        client = OpenAICompatibleClient(local_config)

        mock_response = Mock()
        mock_response.choices = []

        client.client.chat.completions.create = Mock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hello"}]
        with pytest.raises(ModelClientError, match="No choices"):
            client.chat_completion(messages)

    def test_chat_completion_none_content(self, local_config: ModelProviderConfig):
        """Test error when API returns None content."""
        client = OpenAICompatibleClient(local_config)

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = None

        client.client.chat.completions.create = Mock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hello"}]
        with pytest.raises(ModelClientError, match="No content"):
            client.chat_completion(messages)

    def test_chat_completion_retries_on_rate_limit(self, local_config: ModelProviderConfig):
        """Test retries on rate limit error."""
        client = OpenAICompatibleClient(local_config)

        # First call raises RateLimitError, second succeeds
        mock_success = Mock()
        mock_success.choices = [Mock()]
        mock_success.choices[0].message.content = "Success"

        # Create mock httpx response for error
        mock_error_response = Mock()
        mock_error_response.request = Mock()

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RateLimitError("Rate limit exceeded", response=mock_error_response, body=None)
            return mock_success

        client.client.chat.completions.create = Mock(side_effect=side_effect)

        messages = [{"role": "user", "content": "Hello"}]
        response = client.chat_completion(messages)

        assert response == "Success"
        assert call_count == 2  # Retried once

    def test_chat_completion_retries_on_timeout(self, local_config: ModelProviderConfig):
        """Test retries on timeout error."""
        client = OpenAICompatibleClient(local_config)

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Success"

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise APITimeoutError("Request timeout")
            return mock_response

        client.client.chat.completions.create = Mock(side_effect=side_effect)

        messages = [{"role": "user", "content": "Hello"}]
        response = client.chat_completion(messages)

        assert response == "Success"
        assert call_count == 2

    def test_chat_completion_max_retries(self, local_config: ModelProviderConfig):
        """Test max retries are exhausted."""
        client = OpenAICompatibleClient(local_config)

        # Create mock httpx response for error
        mock_error_response = Mock()
        mock_error_response.request = Mock()

        # Always raise RateLimitError
        def side_effect(*args, **kwargs):
            raise RateLimitError("Always rate limited", response=mock_error_response, body=None)

        client.client.chat.completions.create = Mock(side_effect=side_effect)

        messages = [{"role": "user", "content": "Hello"}]
        with pytest.raises(RateLimitError):
            client.chat_completion(messages)

        # Should have retried 3 times total
        assert client.client.chat.completions.create.call_count == 3

    def test_validate_config_openai(self):
        """Test validate_config for OpenAI provider."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            config = ModelProviderConfig(provider="openai", model="gpt-4")
            client = OpenAICompatibleClient(config)

            # Should not raise
            client.validate_config()

    def test_validate_config_missing_api_key(self):
        """Test validate_config fails without API key for OpenAI."""
        config = ModelProviderConfig(provider="openai", model="gpt-4")

        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ModelClientError, match="OPENAI_API_KEY"):
                OpenAICompatibleClient(config)

    def test_validate_config_local_provider(self, local_config: ModelProviderConfig):
        """Test validate_config for local provider."""
        client = OpenAICompatibleClient(local_config)

        # Should not raise (local providers don't need API key)
        client.validate_config()

    def test_parameters_passed_to_api(self, local_config: ModelProviderConfig):
        """Test that config parameters are passed to API."""
        client = OpenAICompatibleClient(local_config)

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Response"

        client.client.chat.completions.create = Mock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hello"}]
        client.chat_completion(messages)

        # Check parameters
        call_args = client.client.chat.completions.create.call_args
        assert call_args[1]["model"] == "llama2"
        assert call_args[1]["temperature"] == 0.7
        assert call_args[1]["max_tokens"] == 500
        assert call_args[1]["messages"] == messages


class TestCreateModelClient:
    """Tests for create_model_client factory."""

    def test_create_openai_client(self):
        """Test creating OpenAI client."""
        config = ModelProviderConfig(provider="openai", model="gpt-4")

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            client = create_model_client(config)

            assert isinstance(client, OpenAICompatibleClient)
            assert client.provider == "openai"

    def test_create_ollama_client(self):
        """Test creating Ollama client."""
        config = ModelProviderConfig(provider="ollama", model="llama2")

        client = create_model_client(config)

        assert isinstance(client, OpenAICompatibleClient)
        assert client.provider == "ollama"

    def test_create_unsupported_provider(self):
        """Test error for unsupported provider."""
        config = ModelProviderConfig(provider="unknown", model="test")

        with pytest.raises(ModelClientError, match="Unsupported provider"):
            create_model_client(config)

"""Tests for model client abstraction."""

import os
from unittest.mock import patch

import pytest

from llm_wiki.models.client import (
    ModelClientError,
    OpenAICompatibleClient,
    create_model_client,
)
from llm_wiki.models.config import ModelProviderConfig


class TestOpenAICompatibleClient:
    """Tests for OpenAICompatibleClient."""

    def test_create_ollama_client(self):
        """Test creating client for Ollama (no API key needed)."""
        config = ModelProviderConfig(
            provider="ollama",
            model="llama2",
            temperature=0.1,
        )
        client = OpenAICompatibleClient(config)

        assert client.provider == "ollama"
        assert client.model == "llama2"
        assert client.api_key is None
        assert client.base_url == "http://localhost:11434/v1"

    def test_create_lmstudio_client(self):
        """Test creating client for LM Studio."""
        config = ModelProviderConfig(
            provider="lmstudio",
            model="local-model",
            temperature=0.1,
        )
        client = OpenAICompatibleClient(config)

        assert client.provider == "lmstudio"
        assert client.api_key is None
        assert client.base_url == "http://localhost:1234/v1"

    def test_create_local_client_with_env(self):
        """Test creating local client with custom base URL."""
        with patch.dict(os.environ, {"LLM_BASE_URL": "http://custom:5000/v1"}):
            config = ModelProviderConfig(
                provider="local",
                model="custom-model",
                temperature=0.1,
            )
            client = OpenAICompatibleClient(config)

            assert client.base_url == "http://custom:5000/v1"

    def test_create_openai_client_with_key(self):
        """Test creating OpenAI client with API key."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test123"}):
            config = ModelProviderConfig(
                provider="openai",
                model="gpt-4",
                temperature=0.1,
            )
            client = OpenAICompatibleClient(config)

            assert client.provider == "openai"
            assert client.api_key == "sk-test123"
            assert client.base_url == "https://api.openai.com/v1"

    def test_create_openai_client_without_key(self):
        """Test creating OpenAI client without API key raises error."""
        with patch.dict(os.environ, {}, clear=True):
            config = ModelProviderConfig(
                provider="openai",
                model="gpt-4",
                temperature=0.1,
            )
            with pytest.raises(ModelClientError, match="OPENAI_API_KEY"):
                OpenAICompatibleClient(config)

    def test_validate_config_success(self):
        """Test validating valid configuration."""
        config = ModelProviderConfig(
            provider="ollama",
            model="llama2",
            temperature=0.1,
        )
        client = OpenAICompatibleClient(config)
        client.validate_config()  # Should not raise

    def test_validate_config_missing_base_url(self):
        """Test validation fails with missing base URL."""
        config = ModelProviderConfig(
            provider="unknown",
            model="test",
            temperature=0.1,
        )
        with patch.dict(os.environ, {}, clear=True):
            client = OpenAICompatibleClient(config)
            client.base_url = ""  # Simulate missing base URL
            with pytest.raises(ModelClientError, match="No base URL"):
                client.validate_config()

    def test_chat_completion_not_implemented(self):
        """Test chat_completion raises NotImplementedError for v1."""
        config = ModelProviderConfig(
            provider="ollama",
            model="llama2",
            temperature=0.1,
        )
        client = OpenAICompatibleClient(config)

        with pytest.raises(NotImplementedError, match="openai package"):
            client.chat_completion([{"role": "user", "content": "test"}])

    def test_config_properties(self):
        """Test client properly stores config properties."""
        config = ModelProviderConfig(
            provider="ollama",
            model="llama2",
            temperature=0.7,
            max_tokens=1000,
            timeout=60,
        )
        client = OpenAICompatibleClient(config)

        assert client.temperature == 0.7
        assert client.max_tokens == 1000
        assert client.timeout == 60


class TestCreateModelClient:
    """Tests for create_model_client factory function."""

    def test_create_openai_client(self):
        """Test factory creates OpenAI client."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            config = ModelProviderConfig(
                provider="openai",
                model="gpt-4",
                temperature=0.1,
            )
            client = create_model_client(config)

            assert isinstance(client, OpenAICompatibleClient)
            assert client.provider == "openai"

    def test_create_ollama_client(self):
        """Test factory creates Ollama client."""
        config = ModelProviderConfig(
            provider="ollama",
            model="llama2",
            temperature=0.1,
        )
        client = create_model_client(config)

        assert isinstance(client, OpenAICompatibleClient)
        assert client.provider == "ollama"

    def test_create_unsupported_provider(self):
        """Test factory raises error for unsupported provider."""
        config = ModelProviderConfig(
            provider="anthropic",  # Not yet supported
            model="claude-3",
            temperature=0.1,
        )

        with pytest.raises(ModelClientError, match="Unsupported provider"):
            create_model_client(config)


class TestModelClientInterface:
    """Tests for ModelClient abstract interface."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that ModelClient cannot be instantiated directly."""
        from llm_wiki.models.client import ModelClient

        config = ModelProviderConfig(
            provider="test",
            model="test",
            temperature=0.1,
        )

        with pytest.raises(TypeError):
            ModelClient(config)  # type: ignore

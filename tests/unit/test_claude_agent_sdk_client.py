"""Tests for ClaudeAgentSDKClient and factory dispatch."""

import pytest

from llm_wiki.models.client import (
    ClaudeAgentSDKClient,
    ModelClientError,
    create_model_client,
)
from llm_wiki.models.config import ModelProviderConfig


class TestCreateModelClientDispatch:
    """Tests for provider dispatch in create_model_client."""

    def test_dispatches_claude_agent_sdk(self, monkeypatch):
        """provider=claude_agent_sdk routes to ClaudeAgentSDKClient."""
        # Inject a fake claude_agent_sdk module so the import succeeds.
        import sys
        import types

        fake = types.ModuleType("claude_agent_sdk")

        async def _query(prompt):
            # Dummy async generator; body never executed in this test.
            if False:
                yield None

        fake.query = _query  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)

        config = ModelProviderConfig(
            provider="claude_agent_sdk",
            model="claude-sonnet-4-6",
        )
        client = create_model_client(config)
        assert isinstance(client, ClaudeAgentSDKClient)

    def test_unsupported_provider_raises(self):
        """Unknown provider raises ModelClientError."""
        config = ModelProviderConfig(provider="totally-fake", model="x")
        with pytest.raises(ModelClientError):
            create_model_client(config)


class TestClaudeAgentSDKClientMissingSDK:
    """Tests for the missing-dependency error path."""

    def test_raises_when_sdk_not_installed(self, monkeypatch):
        """Constructor raises a helpful ModelClientError when SDK missing."""
        import sys

        # Ensure the module is not importable. Stash any existing entry,
        # then insert a sentinel that raises ImportError on access.
        monkeypatch.delitem(sys.modules, "claude_agent_sdk", raising=False)

        # Block imports via meta_path finder
        class _Blocker:
            def find_module(self, name, path=None):
                if name == "claude_agent_sdk":
                    return self
                return None

            def load_module(self, name):
                raise ImportError(f"blocked: {name}")

            def find_spec(self, name, path, target=None):
                if name == "claude_agent_sdk":
                    raise ImportError("blocked")
                return None

        blocker = _Blocker()
        monkeypatch.setattr(
            sys, "meta_path", [blocker] + sys.meta_path, raising=False
        )

        config = ModelProviderConfig(provider="claude_agent_sdk", model="m")
        with pytest.raises(ModelClientError, match="claude-agent-sdk"):
            ClaudeAgentSDKClient(config)


class TestClaudeAgentSDKClientChatCompletion:
    """Tests for the chat_completion flow using a stub SDK."""

    def _install_fake_sdk(self, monkeypatch, responses: list[str]):
        """Install a fake claude_agent_sdk.query that yields given responses."""
        import sys
        import types

        fake = types.ModuleType("claude_agent_sdk")

        class _Block:
            def __init__(self, text: str):
                self.text = text

        class _Message:
            def __init__(self, text: str):
                self.content = [_Block(text)]

        async def _query(prompt):
            for r in responses:
                yield _Message(r)

        fake.query = _query  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)

    def test_chat_completion_concatenates_chunks(self, monkeypatch):
        """Text blocks across multiple messages are concatenated."""
        self._install_fake_sdk(monkeypatch, ["hello ", "world"])
        config = ModelProviderConfig(provider="claude_agent_sdk", model="m")
        client = ClaudeAgentSDKClient(config)

        result = client.chat_completion([{"role": "user", "content": "hi"}])
        assert result == "hello world"

    def test_empty_response_raises(self, monkeypatch):
        """An SDK run that produces no text raises ModelClientError."""
        self._install_fake_sdk(monkeypatch, [""])
        config = ModelProviderConfig(provider="claude_agent_sdk", model="m")
        client = ClaudeAgentSDKClient(config)

        with pytest.raises(ModelClientError, match="empty response"):
            client.chat_completion([{"role": "user", "content": "hi"}])

    def test_json_response_format_appends_instruction(self, monkeypatch):
        """JSON response_format adds JSON-only instruction to the prompt."""
        import sys
        import types

        captured_prompts: list[str] = []

        fake = types.ModuleType("claude_agent_sdk")

        class _Block:
            def __init__(self, text: str):
                self.text = text

        class _Message:
            def __init__(self, text: str):
                self.content = [_Block(text)]

        async def _query(prompt):
            captured_prompts.append(prompt)
            yield _Message("{}")

        fake.query = _query  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)

        config = ModelProviderConfig(provider="claude_agent_sdk", model="m")
        client = ClaudeAgentSDKClient(config)

        client.chat_completion(
            [{"role": "user", "content": "extract"}],
            response_format={"type": "json_object"},
        )

        assert captured_prompts
        assert "valid JSON" in captured_prompts[0]

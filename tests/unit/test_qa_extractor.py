"""Tests for QAExtractor."""

import json
from unittest.mock import MagicMock

from llm_wiki.extraction.qa import QAExtractor


class _FakeClient:
    """Minimal ModelClient stub returning a canned JSON response."""

    def __init__(self, response: str):
        self._response = response
        self.calls: list[dict] = []

    def chat_completion(self, messages, response_format=None):
        self.calls.append({"messages": messages, "response_format": response_format})
        return self._response


class TestQAExtractor:
    """Tests for QAExtractor behavior."""

    def test_extracts_valid_pairs(self):
        """Well-formed JSON with pairs yields the same pairs."""
        payload = {
            "pairs": [
                {
                    "question": "How do I X?",
                    "answer": "Do Y.",
                    "tags": ["python", "tutorial"],
                },
                {
                    "question": "Why does Z happen?",
                    "answer": "Because A.",
                    "tags": [],
                },
            ]
        }
        client = _FakeClient(json.dumps(payload))
        extractor = QAExtractor(client)

        pairs = extractor.extract_qa_pairs("some content", {"title": "Session"})

        assert len(pairs) == 2
        assert pairs[0]["question"] == "How do I X?"
        assert pairs[0]["tags"] == ["python", "tutorial"]
        assert pairs[1]["tags"] == []

    def test_filters_empty_pairs(self):
        """Pairs with blank question or answer are dropped."""
        payload = {
            "pairs": [
                {"question": "", "answer": "A"},
                {"question": "Q", "answer": ""},
                {"question": "Q", "answer": "A"},
            ]
        }
        client = _FakeClient(json.dumps(payload))
        extractor = QAExtractor(client)

        pairs = extractor.extract_qa_pairs("content", {})
        assert len(pairs) == 1

    def test_accepts_bare_list(self):
        """A bare JSON array response is also accepted."""
        payload = [{"question": "Q", "answer": "A"}]
        client = _FakeClient(json.dumps(payload))
        extractor = QAExtractor(client)

        pairs = extractor.extract_qa_pairs("content", {})
        assert len(pairs) == 1

    def test_returns_empty_on_bad_json(self):
        """Invalid JSON → empty list, no exception."""
        client = _FakeClient("not json at all")
        extractor = QAExtractor(client)

        pairs = extractor.extract_qa_pairs("content", {})
        assert pairs == []

    def test_returns_empty_on_unknown_shape(self):
        """Response without 'pairs' field and not a list → empty list."""
        client = _FakeClient(json.dumps({"unexpected": "value"}))
        extractor = QAExtractor(client)

        pairs = extractor.extract_qa_pairs("content", {})
        assert pairs == []

    def test_cap_at_20_pairs(self):
        """Returns at most 20 pairs."""
        payload = {
            "pairs": [
                {"question": f"Q{i}", "answer": f"A{i}"} for i in range(50)
            ]
        }
        client = _FakeClient(json.dumps(payload))
        extractor = QAExtractor(client)

        pairs = extractor.extract_qa_pairs("content", {})
        assert len(pairs) == 20

    def test_uses_json_response_format(self):
        """Extractor requests JSON object response format from client."""
        client = _FakeClient(json.dumps({"pairs": []}))
        extractor = QAExtractor(client)

        extractor.extract_qa_pairs("content", {"title": "T"})
        assert client.calls[0]["response_format"] == {"type": "json_object"}

    def test_exception_in_client_returns_empty(self):
        """Client exceptions are swallowed, empty list returned."""
        client = MagicMock()
        client.chat_completion.side_effect = RuntimeError("boom")
        extractor = QAExtractor(client)

        pairs = extractor.extract_qa_pairs("content", {})
        assert pairs == []

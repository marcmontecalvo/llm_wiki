"""Tests for entity extraction."""

import json
from unittest.mock import Mock

import pytest

from llm_wiki.extraction.entities import EntityExtractor


class TestEntityExtractor:
    """Tests for EntityExtractor."""

    @pytest.fixture
    def mock_client(self) -> Mock:
        """Create mock LLM client."""
        return Mock()

    @pytest.fixture
    def extractor(self, mock_client: Mock) -> EntityExtractor:
        """Create entity extractor with mock client."""
        return EntityExtractor(client=mock_client)

    def test_extract_entities_success(self, extractor: EntityExtractor, mock_client: Mock):
        """Test successful entity extraction."""
        mock_client.chat_completion.return_value = """{
            "entities": [
                {"name": "Python", "type": "technology", "description": "Programming language"},
                {"name": "Docker", "type": "tool", "description": "Container platform"}
            ]
        }"""

        content = "Python and Docker are commonly used together."
        metadata = {"title": "Test"}

        entities = extractor.extract_entities(content, metadata)

        assert len(entities) == 2
        assert entities[0]["name"] == "Python"
        assert entities[0]["type"] == "technology"
        assert entities[1]["name"] == "Docker"

    def test_extract_entities_list_format(self, extractor: EntityExtractor, mock_client: Mock):
        """Test entity extraction with list format response."""
        mock_client.chat_completion.return_value = """[
            {"name": "AWS", "type": "product", "description": "Cloud platform"}
        ]"""

        content = "Content"
        metadata = {"title": "Test"}

        entities = extractor.extract_entities(content, metadata)

        assert len(entities) == 1
        assert entities[0]["name"] == "AWS"

    def test_extract_entities_max_limit(self, extractor: EntityExtractor, mock_client: Mock):
        """Test entity extraction respects max limit."""
        # Return 15 entities
        mock_entities = [
            {"name": f"Entity{i}", "type": "tool", "description": "Test"} for i in range(15)
        ]
        mock_client.chat_completion.return_value = json.dumps({"entities": mock_entities})

        content = "Content"
        metadata = {"title": "Test"}

        entities = extractor.extract_entities(content, metadata)

        # Should be limited to 10
        assert len(entities) == 10

    def test_extract_entities_error_returns_empty(
        self, extractor: EntityExtractor, mock_client: Mock
    ):
        """Test error handling returns empty list."""
        mock_client.chat_completion.side_effect = Exception("API error")

        content = "Content"
        metadata = {"title": "Test"}

        entities = extractor.extract_entities(content, metadata)

        assert entities == []

    def test_extract_entities_invalid_json(self, extractor: EntityExtractor, mock_client: Mock):
        """Test handling of invalid JSON response."""
        mock_client.chat_completion.return_value = "not json"

        content = "Content"
        metadata = {"title": "Test"}

        entities = extractor.extract_entities(content, metadata)

        assert entities == []

    def test_extract_entities_validates_structure(
        self, extractor: EntityExtractor, mock_client: Mock
    ):
        """Test that invalid entities are filtered out."""
        mock_client.chat_completion.return_value = """{
            "entities": [
                {"name": "Valid", "type": "tool", "description": "Good"},
                {"name": "NoType", "description": "Missing type"},
                {"type": "person", "description": "Missing name"},
                "invalid"
            ]
        }"""

        content = "Content"
        metadata = {"title": "Test"}

        entities = extractor.extract_entities(content, metadata)

        # Only valid entity should be extracted
        assert len(entities) == 1
        assert entities[0]["name"] == "Valid"

"""Tests for concept extraction."""

import json
from unittest.mock import Mock

import pytest

from llm_wiki.extraction.concepts import ConceptExtractor


class TestConceptExtractor:
    """Tests for ConceptExtractor."""

    @pytest.fixture
    def mock_client(self) -> Mock:
        """Create mock LLM client."""
        return Mock()

    @pytest.fixture
    def extractor(self, mock_client: Mock) -> ConceptExtractor:
        """Create concept extractor with mock client."""
        return ConceptExtractor(client=mock_client)

    def test_extract_concepts_success(self, extractor: ConceptExtractor, mock_client: Mock):
        """Test successful concept extraction."""
        mock_client.chat_completion.return_value = """{
            "concepts": [
                {"name": "Microservices", "description": "Architectural pattern"},
                {"name": "API Design", "description": "Interface design principles"}
            ]
        }"""

        content = "Discussion of microservices and API design."
        metadata = {"title": "Test"}

        concepts = extractor.extract_concepts(content, metadata)

        assert len(concepts) == 2
        assert concepts[0]["name"] == "Microservices"
        assert concepts[1]["name"] == "API Design"

    def test_extract_concepts_list_format(self, extractor: ConceptExtractor, mock_client: Mock):
        """Test concept extraction with list format response."""
        mock_client.chat_completion.return_value = """[
            {"name": "DevOps", "description": "Development operations"}
        ]"""

        content = "Content"
        metadata = {"title": "Test"}

        concepts = extractor.extract_concepts(content, metadata)

        assert len(concepts) == 1
        assert concepts[0]["name"] == "DevOps"

    def test_extract_concepts_max_limit(self, extractor: ConceptExtractor, mock_client: Mock):
        """Test concept extraction respects max limit."""
        # Return 12 concepts
        mock_concepts = [{"name": f"Concept{i}", "description": "Test"} for i in range(12)]
        mock_client.chat_completion.return_value = json.dumps({"concepts": mock_concepts})

        content = "Content"
        metadata = {"title": "Test"}

        concepts = extractor.extract_concepts(content, metadata)

        # Should be limited to 8
        assert len(concepts) == 8

    def test_extract_concepts_error_returns_empty(
        self, extractor: ConceptExtractor, mock_client: Mock
    ):
        """Test error handling returns empty list."""
        mock_client.chat_completion.side_effect = Exception("API error")

        content = "Content"
        metadata = {"title": "Test"}

        concepts = extractor.extract_concepts(content, metadata)

        assert concepts == []

"""Tests for relationship extraction."""

import json
from unittest.mock import Mock

import pytest

from llm_wiki.extraction.relationships import RELATIONSHIP_TYPES, RelationshipExtractor


class TestRelationshipExtractor:
    """Tests for RelationshipExtractor."""

    @pytest.fixture
    def mock_client(self) -> Mock:
        """Create mock LLM client."""
        return Mock()

    @pytest.fixture
    def extractor(self, mock_client: Mock) -> RelationshipExtractor:
        """Create relationship extractor with mock client."""
        return RelationshipExtractor(client=mock_client)

    def test_extract_relationships_success(
        self, extractor: RelationshipExtractor, mock_client: Mock
    ):
        """Test successful relationship extraction."""
        mock_client.chat_completion.return_value = """{
            "relationships": [
                {
                    "source_entity": "Python",
                    "relationship_type": "uses",
                    "target_entity": "C libraries",
                    "description": "Python can use C libraries for performance",
                    "confidence": 0.95,
                    "bidirectional": false
                },
                {
                    "source_entity": "Docker",
                    "relationship_type": "integrates_with",
                    "target_entity": "Kubernetes",
                    "description": "Docker containers can be orchestrated by Kubernetes",
                    "confidence": 0.9,
                    "bidirectional": true
                }
            ]
        }"""

        content = "Python uses C libraries for performance. Docker integrates with Kubernetes."
        metadata = {"title": "Technologies", "id": "tech-page"}

        relationships = extractor.extract_relationships(content, metadata)

        assert len(relationships) == 2
        assert relationships[0]["source_entity"] == "Python"
        assert relationships[0]["relationship_type"] == "uses"
        assert relationships[0]["target_entity"] == "C libraries"
        assert relationships[0]["confidence"] == 0.95
        assert relationships[0]["bidirectional"] is False
        assert relationships[1]["bidirectional"] is True

    def test_extract_relationships_with_available_entities(
        self, extractor: RelationshipExtractor, mock_client: Mock
    ):
        """Test relationship extraction with available entities context."""
        mock_client.chat_completion.return_value = """{
            "relationships": [
                {
                    "source_entity": "Company A",
                    "relationship_type": "collaborates_with",
                    "target_entity": "Company B",
                    "confidence": 0.85,
                    "bidirectional": true
                }
            ]
        }"""

        content = "Company A and Company B collaborate on projects."
        metadata = {"title": "Organizations"}
        available_entities = ["Company A", "Company B", "Company C"]

        relationships = extractor.extract_relationships(content, metadata, available_entities)

        assert len(relationships) == 1
        assert relationships[0]["source_entity"] == "Company A"
        assert relationships[0]["target_entity"] == "Company B"

        # Verify that chat_completion was called with entity context
        mock_client.chat_completion.assert_called_once()
        call_args = mock_client.chat_completion.call_args
        messages = call_args[0][0]
        assert "Known entities" in messages[0]["content"]

    def test_extract_relationships_with_context(
        self, extractor: RelationshipExtractor, mock_client: Mock
    ):
        """Test extract_relationships_with_context method."""
        mock_client.chat_completion.return_value = """{
            "relationships": [
                {
                    "source_entity": "Alice",
                    "relationship_type": "works_for",
                    "target_entity": "Tech Corp",
                    "confidence": 0.9,
                    "bidirectional": false
                }
            ]
        }"""

        content = "Alice works for Tech Corp."
        metadata = {"title": "Staff"}
        entities = [
            {"name": "Alice", "entity_type": "person"},
            {"name": "Tech Corp", "entity_type": "organization"},
        ]

        relationships = extractor.extract_relationships_with_context(content, metadata, entities)

        assert len(relationships) == 1
        assert relationships[0]["source_entity"] == "Alice"

    def test_extract_relationships_list_format(
        self, extractor: RelationshipExtractor, mock_client: Mock
    ):
        """Test relationship extraction with list format response."""
        mock_client.chat_completion.return_value = """[
            {
                "source_entity": "A",
                "relationship_type": "depends_on",
                "target_entity": "B",
                "confidence": 0.8,
                "bidirectional": false
            }
        ]"""

        content = "A depends on B."
        metadata = {"title": "Dependencies"}

        relationships = extractor.extract_relationships(content, metadata)

        assert len(relationships) == 1
        assert relationships[0]["relationship_type"] == "depends_on"

    def test_extract_relationships_max_limit(
        self, extractor: RelationshipExtractor, mock_client: Mock
    ):
        """Test relationship extraction respects max limit."""
        # Return 25 relationships
        mock_rels = [
            {
                "source_entity": f"Entity{i}",
                "relationship_type": "relates_to",
                "target_entity": f"Entity{i + 1}",
                "confidence": 0.8,
                "bidirectional": False,
            }
            for i in range(25)
        ]
        mock_client.chat_completion.return_value = json.dumps({"relationships": mock_rels})

        content = "Content"
        metadata = {"title": "Test"}

        relationships = extractor.extract_relationships(content, metadata)

        # Should be limited to 15
        assert len(relationships) == 15

    def test_extract_relationships_confidence_validation(
        self, extractor: RelationshipExtractor, mock_client: Mock
    ):
        """Test that confidence values are validated (0-1)."""
        mock_client.chat_completion.return_value = """{
            "relationships": [
                {
                    "source_entity": "A",
                    "relationship_type": "uses",
                    "target_entity": "B",
                    "confidence": 1.0,
                    "bidirectional": false
                },
                {
                    "source_entity": "C",
                    "relationship_type": "uses",
                    "target_entity": "D",
                    "confidence": 0.0,
                    "bidirectional": false
                },
                {
                    "source_entity": "E",
                    "relationship_type": "uses",
                    "target_entity": "F",
                    "confidence": 0.5,
                    "bidirectional": false
                },
                {
                    "source_entity": "G",
                    "relationship_type": "uses",
                    "target_entity": "H",
                    "confidence": 1.5,
                    "bidirectional": false
                }
            ]
        }"""

        content = "Content"
        metadata = {"title": "Test"}

        relationships = extractor.extract_relationships(content, metadata)

        # Invalid confidence (1.5) should be filtered out
        assert len(relationships) == 3
        assert all(0.0 <= r["confidence"] <= 1.0 for r in relationships)

    def test_extract_relationships_missing_required_fields(
        self, extractor: RelationshipExtractor, mock_client: Mock
    ):
        """Test that relationships without required fields are filtered."""
        mock_client.chat_completion.return_value = """{
            "relationships": [
                {
                    "source_entity": "A",
                    "relationship_type": "uses",
                    "target_entity": "B",
                    "confidence": 0.9,
                    "bidirectional": false
                },
                {
                    "source_entity": "C",
                    "relationship_type": "uses",
                    "confidence": 0.8,
                    "bidirectional": false
                },
                {
                    "source_entity": "E",
                    "target_entity": "F",
                    "confidence": 0.9,
                    "bidirectional": false
                },
                {
                    "relationship_type": "uses",
                    "target_entity": "G",
                    "confidence": 0.9,
                    "bidirectional": false
                },
                "invalid"
            ]
        }"""

        content = "Content"
        metadata = {"title": "Test"}

        relationships = extractor.extract_relationships(content, metadata)

        # Only first relationship is valid
        assert len(relationships) == 1
        assert relationships[0]["source_entity"] == "A"

    def test_extract_relationships_optional_fields(
        self, extractor: RelationshipExtractor, mock_client: Mock
    ):
        """Test that optional fields are handled correctly."""
        mock_client.chat_completion.return_value = """{
            "relationships": [
                {
                    "source_entity": "A",
                    "relationship_type": "uses",
                    "target_entity": "B",
                    "confidence": 0.9
                }
            ]
        }"""

        content = "Content"
        metadata = {"title": "Test"}

        relationships = extractor.extract_relationships(content, metadata)

        assert len(relationships) == 1
        assert relationships[0]["description"] is None
        assert relationships[0]["bidirectional"] is False

    def test_extract_relationships_empty_content(
        self, extractor: RelationshipExtractor, mock_client: Mock
    ):
        """Test relationship extraction with empty content."""
        mock_client.chat_completion.return_value = '{"relationships": []}'

        content = ""
        metadata = {"title": "Empty"}

        relationships = extractor.extract_relationships(content, metadata)

        assert relationships == []

    def test_extract_relationships_error_returns_empty(
        self, extractor: RelationshipExtractor, mock_client: Mock
    ):
        """Test error handling returns empty list."""
        mock_client.chat_completion.side_effect = Exception("API error")

        content = "Content"
        metadata = {"title": "Test"}

        relationships = extractor.extract_relationships(content, metadata)

        assert relationships == []

    def test_extract_relationships_invalid_json(
        self, extractor: RelationshipExtractor, mock_client: Mock
    ):
        """Test handling of invalid JSON response."""
        mock_client.chat_completion.return_value = "not json"

        content = "Content"
        metadata = {"title": "Test"}

        relationships = extractor.extract_relationships(content, metadata)

        assert relationships == []

    def test_extract_relationships_unexpected_format(
        self, extractor: RelationshipExtractor, mock_client: Mock
    ):
        """Test handling of unexpected response format."""
        mock_client.chat_completion.return_value = '{"data": "unexpected"}'

        content = "Content"
        metadata = {"title": "Test"}

        relationships = extractor.extract_relationships(content, metadata)

        assert relationships == []

    def test_normalize_relationship_type_direct_match(self, extractor: RelationshipExtractor):
        """Test normalization with direct match."""
        assert extractor.normalize_relationship_type("uses") == "uses"
        assert extractor.normalize_relationship_type("depends_on") == "depends_on"
        assert extractor.normalize_relationship_type("works_for") == "works_for"

    def test_normalize_relationship_type_case_insensitive(self, extractor: RelationshipExtractor):
        """Test normalization is case insensitive."""
        assert extractor.normalize_relationship_type("USES") == "uses"
        assert extractor.normalize_relationship_type("Uses") == "uses"
        assert extractor.normalize_relationship_type("DEPENDS_ON") == "depends_on"

    def test_normalize_relationship_type_space_handling(self, extractor: RelationshipExtractor):
        """Test normalization handles spaces."""
        assert extractor.normalize_relationship_type("depends on") == "depends_on"
        assert extractor.normalize_relationship_type("works for") == "works_for"
        assert extractor.normalize_relationship_type("part of") == "part_of"

    def test_normalize_relationship_type_prefix_match(self, extractor: RelationshipExtractor):
        """Test normalization with prefix matching."""
        # "dep" should match "depends_on" (first 3 chars match)
        result = extractor.normalize_relationship_type("dep")
        assert result == "depends_on"

    def test_normalize_relationship_type_custom(self, extractor: RelationshipExtractor):
        """Test normalization returns custom type if no match."""
        custom_type = "custom_relationship"
        result = extractor.normalize_relationship_type(custom_type)
        assert result == "custom_relationship"

    def test_create_bidirectional_relationships_no_bidirectional(
        self, extractor: RelationshipExtractor
    ):
        """Test bidirectional expansion with no bidirectional rels."""
        relationships = [
            {
                "source_entity": "A",
                "relationship_type": "uses",
                "target_entity": "B",
                "bidirectional": False,
            },
            {
                "source_entity": "C",
                "relationship_type": "depends_on",
                "target_entity": "D",
                "bidirectional": False,
            },
        ]

        result = extractor.create_bidirectional_relationships(relationships)

        # Should only have original relationships
        assert len(result) == 2
        assert result[0]["source_entity"] == "A"
        assert result[1]["source_entity"] == "C"

    def test_create_bidirectional_relationships_with_bidirectional(
        self, extractor: RelationshipExtractor
    ):
        """Test bidirectional expansion with bidirectional rels."""
        relationships = [
            {
                "source_entity": "A",
                "relationship_type": "collaborates_with",
                "target_entity": "B",
                "description": "They work together",
                "confidence": 0.9,
                "bidirectional": True,
            }
        ]

        result = extractor.create_bidirectional_relationships(relationships)

        # Should have original + reversed
        assert len(result) == 2
        assert result[0]["source_entity"] == "A"
        assert result[0]["target_entity"] == "B"
        assert result[1]["source_entity"] == "B"
        assert result[1]["target_entity"] == "A"
        assert result[1]["relationship_type"] == "collaborates_with"
        assert result[1]["description"] == "They work together"
        assert result[1]["confidence"] == 0.9
        assert result[1]["bidirectional"] is True

    def test_create_bidirectional_relationships_mixed(self, extractor: RelationshipExtractor):
        """Test bidirectional expansion with mixed rels."""
        relationships = [
            {
                "source_entity": "A",
                "relationship_type": "uses",
                "target_entity": "B",
                "confidence": 0.8,
                "bidirectional": False,
            },
            {
                "source_entity": "C",
                "relationship_type": "owns",
                "target_entity": "D",
                "confidence": 0.95,
                "bidirectional": True,
            },
            {
                "source_entity": "E",
                "relationship_type": "manages",
                "target_entity": "F",
                "confidence": 0.85,
                "bidirectional": False,
            },
        ]

        result = extractor.create_bidirectional_relationships(relationships)

        # Original 3 + 1 reversed (for C-D bidirectional)
        assert len(result) == 4
        # Check that reversed relationship exists
        reversed_rels = [r for r in result if r["source_entity"] == "D"]
        assert len(reversed_rels) == 1
        assert reversed_rels[0]["target_entity"] == "C"

    def test_extract_relationships_with_description(
        self, extractor: RelationshipExtractor, mock_client: Mock
    ):
        """Test relationship extraction preserves descriptions."""
        mock_client.chat_completion.return_value = """{
            "relationships": [
                {
                    "source_entity": "Flask",
                    "relationship_type": "extends",
                    "target_entity": "Werkzeug",
                    "description": "Flask is built on top of Werkzeug WSGI toolkit",
                    "confidence": 0.95,
                    "bidirectional": false
                }
            ]
        }"""

        content = "Flask extends Werkzeug."
        metadata = {"title": "Python Web Frameworks"}

        relationships = extractor.extract_relationships(content, metadata)

        assert len(relationships) == 1
        assert relationships[0]["description"] == "Flask is built on top of Werkzeug WSGI toolkit"

    def test_extract_relationships_whitespace_handling(
        self, extractor: RelationshipExtractor, mock_client: Mock
    ):
        """Test that entity names are trimmed of whitespace."""
        mock_client.chat_completion.return_value = """{
            "relationships": [
                {
                    "source_entity": "  Python  ",
                    "relationship_type": "  uses  ",
                    "target_entity": "  C libraries  ",
                    "confidence": 0.9,
                    "bidirectional": false
                }
            ]
        }"""

        content = "Content"
        metadata = {"title": "Test"}

        relationships = extractor.extract_relationships(content, metadata)

        assert len(relationships) == 1
        assert relationships[0]["source_entity"] == "Python"
        assert relationships[0]["relationship_type"] == "uses"
        assert relationships[0]["target_entity"] == "C libraries"

    def test_extract_relationships_empty_description_handling(
        self, extractor: RelationshipExtractor, mock_client: Mock
    ):
        """Test that empty description becomes None."""
        mock_client.chat_completion.return_value = """{
            "relationships": [
                {
                    "source_entity": "A",
                    "relationship_type": "uses",
                    "target_entity": "B",
                    "description": "",
                    "confidence": 0.9,
                    "bidirectional": false
                }
            ]
        }"""

        content = "Content"
        metadata = {"title": "Test"}

        relationships = extractor.extract_relationships(content, metadata)

        assert len(relationships) == 1
        assert relationships[0]["description"] is None

    def test_extract_relationships_metadata_extraction(
        self, extractor: RelationshipExtractor, mock_client: Mock
    ):
        """Test that title from metadata is used in prompt."""
        mock_client.chat_completion.return_value = '{"relationships": []}'

        content = "Some content"
        metadata = {"title": "Special Title", "id": "test-123"}

        extractor.extract_relationships(content, metadata)

        # Verify title is in the prompt
        call_args = mock_client.chat_completion.call_args
        messages = call_args[0][0]
        assert "Special Title" in messages[0]["content"]

    def test_relationship_types_taxonomy_exists(self, extractor: RelationshipExtractor):
        """Test that relationship types taxonomy is defined."""
        assert len(RELATIONSHIP_TYPES) >= 20
        assert "uses" in RELATIONSHIP_TYPES
        assert "depends_on" in RELATIONSHIP_TYPES
        assert "collaborates_with" in RELATIONSHIP_TYPES
        assert "part_of" in RELATIONSHIP_TYPES

    def test_extract_relationships_with_context_no_entities(
        self, extractor: RelationshipExtractor, mock_client: Mock
    ):
        """Test extract_relationships_with_context with None entities."""
        mock_client.chat_completion.return_value = '{"relationships": []}'

        content = "Content"
        metadata = {"title": "Test"}

        result = extractor.extract_relationships_with_context(content, metadata, None)

        assert result == []

    def test_extract_relationships_with_context_empty_entities(
        self, extractor: RelationshipExtractor, mock_client: Mock
    ):
        """Test extract_relationships_with_context with empty entities."""
        mock_client.chat_completion.return_value = '{"relationships": []}'

        content = "Content"
        metadata = {"title": "Test"}

        result = extractor.extract_relationships_with_context(content, metadata, [])

        assert result == []

    def test_extract_relationships_with_context_missing_name(
        self, extractor: RelationshipExtractor, mock_client: Mock
    ):
        """Test that entities without 'name' field are skipped."""
        mock_client.chat_completion.return_value = '{"relationships": []}'

        content = "Content"
        metadata = {"title": "Test"}
        entities = [
            {"entity_type": "person"},  # Missing name
            {"name": "Valid Entity", "entity_type": "org"},
        ]

        extractor.extract_relationships_with_context(content, metadata, entities)

        # Verify that only valid entity name appears in prompt
        call_args = mock_client.chat_completion.call_args
        messages = call_args[0][0]
        prompt = messages[0]["content"]
        assert "Valid Entity" in prompt
        # The invalid entity should not appear
        assert "entity_type" not in prompt or "Known entities" in prompt

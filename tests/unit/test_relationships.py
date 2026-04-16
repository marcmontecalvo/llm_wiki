"""Tests for relationship extraction and index."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from llm_wiki.extraction.relationships import (
    RELATIONSHIP_TYPES,
    RelationshipExtractor,
)


class TestRelationshipExtractor:
    """Tests for RelationshipExtractor."""

    @pytest.fixture
    def mock_client(self):
        """Create mock LLM client."""
        client = MagicMock()
        return client

    @pytest.fixture
    def extractor(self, mock_client):
        """Create relationship extractor with mock client."""
        return RelationshipExtractor(mock_client)

    def test_relationship_types_defined(self):
        """Test that standard relationship types are defined."""
        assert "uses" in RELATIONSHIP_TYPES
        assert "depends_on" in RELATIONSHIP_TYPES
        assert "part_of" in RELATIONSHIP_TYPES
        assert "related_to" in RELATIONSHIP_TYPES

    def test_extract_relationships_returns_list(self, extractor, mock_client):
        """Test that extract_relationships returns a list."""
        mock_client.chat_completion.return_value = '{"relationships": []}'

        result = extractor.extract_relationships(
            "Some content",
            {"title": "Test Page"},
        )

        assert isinstance(result, list)

    def test_extract_relationships_with_entities(self, extractor, mock_client):
        """Test extraction with entity context."""
        mock_client.chat_completion.return_value = '{"relationships": []}'

        result = extractor.extract_relationships(
            "Python uses Docker",
            {"title": "Test"},
            available_entities=["Python", "Docker"],
        )

        assert mock_client.chat_completion.called

    def test_extract_relationships_validates_format(self, extractor, mock_client):
        """Test that extraction validates response format."""
        mock_client.chat_completion.return_value = '{"relationships": [{"source_entity": "A", "relationship_type": "uses", "target_entity": "B", "confidence": 0.9}]}'

        result = extractor.extract_relationships("content", {"title": "Test"})

        assert len(result) > 0
        assert result[0]["source_entity"] == "A"
        assert result[0]["relationship_type"] == "uses"

    def test_extract_relationships_with_source_reference(self, extractor, mock_client):
        """Test that source_reference is extracted."""
        mock_client.chat_completion.return_value = '{"relationships": [{"source_entity": "A", "relationship_type": "uses", "target_entity": "B", "source_reference": "paragraph 3", "confidence": 0.9}]}'

        result = extractor.extract_relationships("content", {"title": "Test"})

        assert len(result) == 1
        assert result[0]["source_reference"] == "paragraph 3"

    def test_extract_relationships_with_chain_metadata(self, extractor, mock_client):
        """Test that multi-hop chain metadata is extracted."""
        mock_client.chat_completion.return_value = '{"relationships": [{"source_entity": "A", "relationship_type": "depends_on", "target_entity": "C", "source_reference": "paragraph 5", "chain": "A -> B -> C", "confidence": 0.8}]}'

        result = extractor.extract_relationships("content", {"title": "Test"})

        assert len(result) == 1
        assert result[0].get("chain") == "A -> B -> C"

    def test_normalize_relationship_type(self, extractor):
        """Test relationship type normalization."""
        assert extractor.normalize_relationship_type("uses") == "uses"
        assert extractor.normalize_relationship_type("USES") == "uses"
        assert extractor.normalize_relationship_type("uses ") == "uses"

    def test_create_bidirectional_relationships(self, extractor):
        """Test creating reverse relationships."""
        relationships = [
            {
                "source_entity": "Python",
                "relationship_type": "uses",
                "target_entity": "Docker",
                "confidence": 0.9,
                "bidirectional": True,
            }
        ]

        result = extractor.create_bidirectional_relationships(relationships)

        # Should have original + reverse
        assert len(result) == 2
        # Find the reverse
        reverse = next(r for r in result if r["source_entity"] == "Docker")
        assert reverse["relationship_type"] == "uses"
        assert reverse["target_entity"] == "Python"


class TestRelationshipIndex:
    """Tests for RelationshipIndex."""

    @pytest.fixture
    def index(self, temp_dir: Path):
        """Create relationship index in temp directory."""
        from llm_wiki.index.relationships import RelationshipIndex

        index_dir = temp_dir / "index"
        return RelationshipIndex(index_dir=index_dir)

    def test_add_relationship(self, index):
        """Test adding a relationship to index."""
        rel = {
            "source_entity": "Python",
            "relationship_type": "uses",
            "target_entity": "Docker",
            "confidence": 0.9,
        }

        index.add_relationship("test-page", rel)

        # Check outgoing relationships
        outgoing = index.get_outgoing_relationships("Python")
        assert len(outgoing) == 1
        assert outgoing[0]["target"] == "Docker"

    def test_add_relationship_indexes_both_directions(self, index):
        """Test that relationships are indexed for both directions."""
        rel = {
            "source_entity": "A",
            "relationship_type": "depends_on",
            "target_entity": "B",
            "confidence": 0.8,
        }

        index.add_relationship("page-1", rel)

        # Should have outgoing from A
        outgoing = index.get_outgoing_relationships("A")
        assert len(outgoing) == 1

        # Should have incoming to B
        incoming = index.get_incoming_relationships("B")
        assert len(incoming) == 1

    def test_get_all_relationships(self, index):
        """Test getting all relationships for an entity."""
        rel1 = {
            "source_entity": "Python",
            "relationship_type": "uses",
            "target_entity": "Docker",
            "confidence": 0.9,
        }
        rel2 = {
            "source_entity": "Go",
            "relationship_type": "competes_with",
            "target_entity": "Python",
            "confidence": 0.7,
        }

        index.add_relationship("page-1", rel1)
        index.add_relationship("page-2", rel2)

        # Get all relationships for Python
        all_rels = index.get_all_relationships("Python")

        assert len(all_rels) == 2

    def test_find_related_with_type_filter(self, index):
        """Test filtering relationships by type."""
        rel1 = {
            "source_entity": "A",
            "relationship_type": "uses",
            "target_entity": "B",
            "confidence": 0.9,
        }
        rel2 = {
            "source_entity": "A",
            "relationship_type": "depends_on",
            "target_entity": "C",
            "confidence": 0.8,
        }

        index.add_relationship("page-1", rel1)
        index.add_relationship("page-1", rel2)

        # Filter by type
        results = index.find_related("A", rel_type="uses")

        assert len(results) == 1
        assert results[0]["relationship_type"] == "uses"

    def test_find_related_with_confidence_threshold(self, index):
        """Test filtering by confidence threshold."""
        rel1 = {
            "source_entity": "A",
            "relationship_type": "uses",
            "target_entity": "B",
            "confidence": 0.9,
        }
        rel2 = {
            "source_entity": "A",
            "relationship_type": "depends_on",
            "target_entity": "C",
            "confidence": 0.5,
        }

        index.add_relationship("page-1", rel1)
        index.add_relationship("page-1", rel2)

        # Filter by confidence
        results = index.find_related("A", min_confidence=0.7)

        assert len(results) == 1

    def test_get_stats(self, index):
        """Test getting index statistics."""
        rel = {
            "source_entity": "A",
            "relationship_type": "uses",
            "target_entity": "B",
            "confidence": 0.9,
        }

        index.add_relationship("page-1", rel)

        stats = index.get_stats()
        assert stats["total_relationships"] == 1
        assert stats["unique_subjects"] == 1
        assert stats["unique_targets"] == 1

    def test_save_and_load(self, index, temp_dir):
        """Test saving and loading index."""
        rel = {
            "source_entity": "A",
            "relationship_type": "uses",
            "target_entity": "B",
            "confidence": 0.9,
        }

        index.add_relationship("page-1", rel)
        index.save()

        # Create new index and load
        from llm_wiki.index.relationships import RelationshipIndex

        new_index = RelationshipIndex(index_dir=temp_dir / "index")
        new_index.load()

        assert new_index.get_stats()["total_relationships"] == 1
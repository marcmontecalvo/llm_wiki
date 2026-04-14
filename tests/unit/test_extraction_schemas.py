"""Tests for extraction schemas."""

import pytest
from pydantic import ValidationError

from llm_wiki.models.extraction import (
    ClaimExtraction,
    ConceptExtraction,
    EntityExtraction,
    ExtractionResult,
    RelationshipExtraction,
)


class TestEntityExtraction:
    """Tests for EntityExtraction schema."""

    def test_create_minimal_entity(self):
        """Test creating entity with minimal fields."""
        entity = EntityExtraction(
            name="Apple Inc.",
            entity_type="company",
        )

        assert entity.name == "Apple Inc."
        assert entity.entity_type == "company"
        assert entity.description is None
        assert entity.aliases == []
        assert entity.confidence == 1.0

    def test_create_full_entity(self):
        """Test creating entity with all fields."""
        entity = EntityExtraction(
            name="Apple Inc.",
            entity_type="company",
            description="Technology company",
            aliases=["Apple", "Apple Computer"],
            confidence=0.95,
            source_reference="doc-123",
            context="Founded in 1976...",
        )

        assert entity.description == "Technology company"
        assert entity.aliases == ["Apple", "Apple Computer"]
        assert entity.confidence == 0.95
        assert entity.source_reference == "doc-123"
        assert entity.context == "Founded in 1976..."

    def test_confidence_bounds(self):
        """Test confidence validation."""
        with pytest.raises(ValidationError):
            EntityExtraction(
                name="Test",
                entity_type="test",
                confidence=1.5,
            )


class TestConceptExtraction:
    """Tests for ConceptExtraction schema."""

    def test_create_minimal_concept(self):
        """Test creating concept with minimal fields."""
        concept = ConceptExtraction(name="Machine Learning")

        assert concept.name == "Machine Learning"
        assert concept.definition is None
        assert concept.category is None
        assert concept.related_concepts == []
        assert concept.confidence == 1.0

    def test_create_full_concept(self):
        """Test creating concept with all fields."""
        concept = ConceptExtraction(
            name="Machine Learning",
            definition="A field of AI focused on learning from data",
            category="Artificial Intelligence",
            related_concepts=["Deep Learning", "Neural Networks"],
            confidence=0.9,
            source_reference="doc-456",
            examples=["Image recognition", "Natural language processing"],
        )

        assert concept.definition == "A field of AI focused on learning from data"
        assert concept.category == "Artificial Intelligence"
        assert concept.related_concepts == ["Deep Learning", "Neural Networks"]
        assert concept.examples == ["Image recognition", "Natural language processing"]


class TestClaimExtraction:
    """Tests for ClaimExtraction schema."""

    def test_create_minimal_claim(self):
        """Test creating claim with minimal fields."""
        claim = ClaimExtraction(
            claim="Python was created in 1991",
            source_reference="doc-789",
        )

        assert claim.claim == "Python was created in 1991"
        assert claim.source_reference == "doc-789"
        assert claim.subject is None
        assert claim.confidence == 1.0

    def test_create_full_claim(self):
        """Test creating claim with all fields."""
        claim = ClaimExtraction(
            claim="Python was created by Guido van Rossum in 1991",
            subject="Python",
            predicate="was created by",
            object="Guido van Rossum",
            confidence=0.99,
            source_reference="doc-789",
            temporal_context="1991",
            qualifiers=["first release"],
        )

        assert claim.subject == "Python"
        assert claim.predicate == "was created by"
        assert claim.object == "Guido van Rossum"
        assert claim.temporal_context == "1991"
        assert claim.qualifiers == ["first release"]

    def test_claim_requires_source_reference(self):
        """Test claim requires source reference."""
        with pytest.raises(ValidationError):
            ClaimExtraction(claim="Some claim")  # type: ignore


class TestRelationshipExtraction:
    """Tests for RelationshipExtraction schema."""

    def test_create_minimal_relationship(self):
        """Test creating relationship with minimal fields."""
        rel = RelationshipExtraction(
            source_entity="Python",
            relationship_type="created_by",
            target_entity="Guido van Rossum",
        )

        assert rel.source_entity == "Python"
        assert rel.relationship_type == "created_by"
        assert rel.target_entity == "Guido van Rossum"
        assert rel.bidirectional is False
        assert rel.confidence == 1.0

    def test_create_full_relationship(self):
        """Test creating relationship with all fields."""
        rel = RelationshipExtraction(
            source_entity="Python",
            relationship_type="influences",
            target_entity="Ruby",
            description="Python influenced Ruby's design",
            confidence=0.85,
            source_reference="doc-abc",
            bidirectional=False,
        )

        assert rel.description == "Python influenced Ruby's design"
        assert rel.confidence == 0.85
        assert rel.source_reference == "doc-abc"
        assert rel.bidirectional is False

    def test_bidirectional_relationship(self):
        """Test bidirectional relationship."""
        rel = RelationshipExtraction(
            source_entity="Alice",
            relationship_type="collaborates_with",
            target_entity="Bob",
            bidirectional=True,
        )

        assert rel.bidirectional is True


class TestExtractionResult:
    """Tests for ExtractionResult schema."""

    def test_create_empty_result(self):
        """Test creating empty extraction result."""
        result = ExtractionResult()

        assert result.entities == []
        assert result.concepts == []
        assert result.claims == []
        assert result.relationships == []
        assert result.extraction_metadata == {}
        assert not result.has_extractions()
        assert result.total_count() == 0

    def test_create_result_with_extractions(self):
        """Test creating result with extractions."""
        result = ExtractionResult(
            entities=[
                EntityExtraction(name="Test Entity", entity_type="test"),
            ],
            concepts=[
                ConceptExtraction(name="Test Concept"),
            ],
            claims=[
                ClaimExtraction(claim="Test claim", source_reference="doc-1"),
            ],
            relationships=[
                RelationshipExtraction(
                    source_entity="A",
                    relationship_type="relates_to",
                    target_entity="B",
                ),
            ],
            extraction_metadata={"model": "gpt-4", "timestamp": "2026-04-13"},
        )

        assert len(result.entities) == 1
        assert len(result.concepts) == 1
        assert len(result.claims) == 1
        assert len(result.relationships) == 1
        assert result.has_extractions()
        assert result.total_count() == 4
        assert result.extraction_metadata["model"] == "gpt-4"

    def test_has_extractions_with_entities_only(self):
        """Test has_extractions returns True with just entities."""
        result = ExtractionResult(entities=[EntityExtraction(name="Test", entity_type="test")])
        assert result.has_extractions()

    def test_has_extractions_with_concepts_only(self):
        """Test has_extractions returns True with just concepts."""
        result = ExtractionResult(concepts=[ConceptExtraction(name="Test")])
        assert result.has_extractions()

    def test_has_extractions_with_claims_only(self):
        """Test has_extractions returns True with just claims."""
        result = ExtractionResult(claims=[ClaimExtraction(claim="Test", source_reference="doc")])
        assert result.has_extractions()

    def test_has_extractions_with_relationships_only(self):
        """Test has_extractions returns True with just relationships."""
        result = ExtractionResult(
            relationships=[
                RelationshipExtraction(
                    source_entity="A", relationship_type="relates", target_entity="B"
                )
            ]
        )
        assert result.has_extractions()

    def test_total_count(self):
        """Test total_count sums all extractions."""
        result = ExtractionResult(
            entities=[
                EntityExtraction(name="E1", entity_type="t"),
                EntityExtraction(name="E2", entity_type="t"),
            ],
            concepts=[ConceptExtraction(name="C1")],
            claims=[
                ClaimExtraction(claim="Claim1", source_reference="d"),
                ClaimExtraction(claim="Claim2", source_reference="d"),
                ClaimExtraction(claim="Claim3", source_reference="d"),
            ],
            relationships=[
                RelationshipExtraction(source_entity="A", relationship_type="r", target_entity="B")
            ],
        )

        assert result.total_count() == 7  # 2 + 1 + 3 + 1

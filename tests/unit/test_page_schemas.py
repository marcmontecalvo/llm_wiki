"""Tests for page frontmatter schemas."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from llm_wiki.models.page import (
    ConceptFrontmatter,
    EntityFrontmatter,
    PageFrontmatter,
    SourceFrontmatter,
    create_frontmatter,
)


class TestPageFrontmatter:
    """Tests for base PageFrontmatter schema."""

    def test_create_minimal_page(self):
        """Test creating page with minimal required fields."""
        now = datetime.now(UTC)
        page = PageFrontmatter(
            id="test-page",
            kind="page",
            title="Test Page",
            domain="general",
            updated_at=now,
        )

        assert page.id == "test-page"
        assert page.kind == "page"
        assert page.title == "Test Page"
        assert page.domain == "general"
        assert page.status == "draft"  # Default
        assert page.confidence == 0.0  # Default
        assert page.sources == []
        assert page.links == []

    def test_create_page_with_all_fields(self):
        """Test creating page with all fields."""
        now = datetime.now(UTC)
        page = PageFrontmatter(
            id="test-page",
            kind="page",
            title="Test Page",
            domain="general",
            status="published",
            confidence=0.95,
            sources=["source1", "source2"],
            links=["page1", "page2"],
            updated_at=now,
            created_at=now,
            tags=["tag1", "tag2"],
        )

        assert page.status == "published"
        assert page.confidence == 0.95
        assert page.sources == ["source1", "source2"]
        assert page.links == ["page1", "page2"]
        assert page.tags == ["tag1", "tag2"]

    def test_invalid_kind(self):
        """Test invalid page kind raises error."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            PageFrontmatter(
                id="test",
                kind="invalid",  # type: ignore
                title="Test",
                domain="general",
                updated_at=now,
            )

    def test_invalid_status(self):
        """Test invalid status raises error."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            PageFrontmatter(
                id="test",
                kind="page",
                title="Test",
                domain="general",
                status="invalid",  # type: ignore
                updated_at=now,
            )

    def test_confidence_bounds(self):
        """Test confidence must be between 0 and 1."""
        now = datetime.now(UTC)

        # Too high
        with pytest.raises(ValidationError):
            PageFrontmatter(
                id="test",
                kind="page",
                title="Test",
                domain="general",
                confidence=1.5,
                updated_at=now,
            )

        # Too low
        with pytest.raises(ValidationError):
            PageFrontmatter(
                id="test",
                kind="page",
                title="Test",
                domain="general",
                confidence=-0.1,
                updated_at=now,
            )

    def test_empty_id_validation(self):
        """Test empty ID is rejected."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError, match="cannot be empty"):
            PageFrontmatter(
                id="",
                kind="page",
                title="Test",
                domain="general",
                updated_at=now,
            )

    def test_empty_title_validation(self):
        """Test empty title is rejected."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError, match="cannot be empty"):
            PageFrontmatter(
                id="test",
                kind="page",
                title="",
                domain="general",
                updated_at=now,
            )

    def test_empty_domain_validation(self):
        """Test empty domain is rejected."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError, match="cannot be empty"):
            PageFrontmatter(
                id="test",
                kind="page",
                title="Test",
                domain="",
                updated_at=now,
            )


class TestEntityFrontmatter:
    """Tests for EntityFrontmatter schema."""

    def test_create_entity(self):
        """Test creating entity page."""
        now = datetime.now(UTC)
        entity = EntityFrontmatter(
            id="test-entity",
            title="Test Entity",
            domain="general",
            entity_type="organization",
            updated_at=now,
        )

        assert entity.kind == "entity"
        assert entity.entity_type == "organization"
        assert entity.aliases == []

    def test_create_entity_with_aliases(self):
        """Test creating entity with aliases."""
        now = datetime.now(UTC)
        entity = EntityFrontmatter(
            id="test-entity",
            title="Apple Inc.",
            domain="general",
            entity_type="company",
            aliases=["Apple", "Apple Computer"],
            updated_at=now,
        )

        assert entity.aliases == ["Apple", "Apple Computer"]

    def test_missing_entity_type(self):
        """Test entity requires entity_type."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            EntityFrontmatter(
                id="test",
                title="Test",
                domain="general",
                updated_at=now,
            )  # type: ignore

    def test_empty_entity_type(self):
        """Test empty entity_type is rejected."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError, match="cannot be empty"):
            EntityFrontmatter(
                id="test",
                title="Test",
                domain="general",
                entity_type="",
                updated_at=now,
            )


class TestConceptFrontmatter:
    """Tests for ConceptFrontmatter schema."""

    def test_create_concept(self):
        """Test creating concept page."""
        now = datetime.now(UTC)
        concept = ConceptFrontmatter(
            id="test-concept",
            title="Test Concept",
            domain="general",
            updated_at=now,
        )

        assert concept.kind == "concept"
        assert concept.related_concepts == []

    def test_create_concept_with_related(self):
        """Test creating concept with related concepts."""
        now = datetime.now(UTC)
        concept = ConceptFrontmatter(
            id="test-concept",
            title="Test Concept",
            domain="general",
            related_concepts=["concept1", "concept2"],
            updated_at=now,
        )

        assert concept.related_concepts == ["concept1", "concept2"]


class TestSourceFrontmatter:
    """Tests for SourceFrontmatter schema."""

    def test_create_source(self):
        """Test creating source page."""
        now = datetime.now(UTC)
        source = SourceFrontmatter(
            id="test-source",
            title="Test Source",
            domain="general",
            source_type="markdown",
            source_path="/path/to/source.md",
            ingested_at=now,
            updated_at=now,
        )

        assert source.kind == "source"
        assert source.source_type == "markdown"
        assert source.source_path == "/path/to/source.md"
        assert source.adapter is None

    def test_create_source_with_adapter(self):
        """Test creating source with adapter info."""
        now = datetime.now(UTC)
        source = SourceFrontmatter(
            id="test-source",
            title="Test Source",
            domain="general",
            source_type="transcript",
            source_path="/path/to/transcript.txt",
            ingested_at=now,
            updated_at=now,
            adapter="claude-code-adapter",
        )

        assert source.adapter == "claude-code-adapter"

    def test_missing_source_type(self):
        """Test source requires source_type."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            SourceFrontmatter(
                id="test",
                title="Test",
                domain="general",
                source_path="/path",
                ingested_at=now,
                updated_at=now,
            )  # type: ignore

    def test_missing_source_path(self):
        """Test source requires source_path."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            SourceFrontmatter(
                id="test",
                title="Test",
                domain="general",
                source_type="markdown",
                ingested_at=now,
                updated_at=now,
            )  # type: ignore

    def test_empty_source_type(self):
        """Test empty source_type is rejected."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError, match="cannot be empty"):
            SourceFrontmatter(
                id="test",
                title="Test",
                domain="general",
                source_type="",
                source_path="/path",
                ingested_at=now,
                updated_at=now,
            )

    def test_empty_source_path(self):
        """Test empty source_path is rejected."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError, match="cannot be empty"):
            SourceFrontmatter(
                id="test",
                title="Test",
                domain="general",
                source_type="markdown",
                source_path="",
                ingested_at=now,
                updated_at=now,
            )


class TestCreateFrontmatter:
    """Tests for create_frontmatter factory function."""

    def test_create_page(self):
        """Test factory creates PageFrontmatter."""
        now = datetime.now(UTC)
        page = create_frontmatter(
            kind="page",
            id="test",
            title="Test",
            domain="general",
            updated_at=now,
        )

        assert isinstance(page, PageFrontmatter)
        assert page.kind == "page"

    def test_create_entity(self):
        """Test factory creates EntityFrontmatter."""
        now = datetime.now(UTC)
        entity = create_frontmatter(
            kind="entity",
            id="test",
            title="Test",
            domain="general",
            entity_type="person",
            updated_at=now,
        )

        assert isinstance(entity, EntityFrontmatter)
        assert entity.kind == "entity"

    def test_create_concept(self):
        """Test factory creates ConceptFrontmatter."""
        now = datetime.now(UTC)
        concept = create_frontmatter(
            kind="concept",
            id="test",
            title="Test",
            domain="general",
            updated_at=now,
        )

        assert isinstance(concept, ConceptFrontmatter)
        assert concept.kind == "concept"

    def test_create_source(self):
        """Test factory creates SourceFrontmatter."""
        now = datetime.now(UTC)
        source = create_frontmatter(
            kind="source",
            id="test",
            title="Test",
            domain="general",
            source_type="markdown",
            source_path="/path",
            ingested_at=now,
            updated_at=now,
        )

        assert isinstance(source, SourceFrontmatter)
        assert source.kind == "source"

    def test_create_invalid_kind(self):
        """Test factory raises error for invalid kind."""
        now = datetime.now(UTC)
        with pytest.raises(ValueError, match="Invalid page kind"):
            create_frontmatter(
                kind="invalid",
                id="test",
                title="Test",
                domain="general",
                updated_at=now,
            )

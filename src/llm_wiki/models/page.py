"""Page frontmatter schemas for wiki pages."""

from datetime import datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, Field, field_validator


class PageFrontmatter(BaseModel):
    """Base frontmatter schema for all wiki pages."""

    id: str = Field(..., description="Unique page identifier")
    kind: Literal["page", "entity", "concept", "source", "qa"] = Field(
        ..., description="Page type"
    )
    title: str = Field(..., description="Page title")
    domain: str = Field(..., description="Domain this page belongs to")
    status: Literal["draft", "published", "archived", "review"] = Field(
        default="draft", description="Page status"
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score (0-1)")
    sources: list[str] = Field(default_factory=list, description="Source references")
    links: list[str] = Field(default_factory=list, description="Links to other pages")
    updated_at: datetime = Field(..., description="Last update timestamp")
    created_at: datetime | None = Field(default=None, description="Creation timestamp")
    tags: list[str] = Field(default_factory=list, description="Tags")
    relationships: list[dict[str, Any]] = Field(
        default_factory=list, description="Relationships to other pages/entities"
    )

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Validate page ID is not empty."""
        if not v or not v.strip():
            raise ValueError("Page ID cannot be empty")
        return v

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate page title is not empty."""
        if not v or not v.strip():
            raise ValueError("Page title cannot be empty")
        return v

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        """Validate domain is not empty."""
        if not v or not v.strip():
            raise ValueError("Domain cannot be empty")
        return v


class EntityFrontmatter(PageFrontmatter):
    """Frontmatter schema for entity pages."""

    kind: Literal["entity"] = Field(default="entity", description="Page type")
    entity_type: str = Field(..., description="Type of entity (person, org, product, etc.)")
    aliases: list[str] = Field(
        default_factory=list, description="Alternative names for this entity"
    )

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        """Validate entity type is not empty."""
        if not v or not v.strip():
            raise ValueError("Entity type cannot be empty")
        return v


class ConceptFrontmatter(PageFrontmatter):
    """Frontmatter schema for concept pages."""

    kind: Literal["concept"] = Field(default="concept", description="Page type")
    related_concepts: list[str] = Field(
        default_factory=list, description="Related concept page IDs"
    )


class SourceFrontmatter(PageFrontmatter):
    """Frontmatter schema for source document pages."""

    kind: Literal["source"] = Field(default="source", description="Page type")
    source_type: str = Field(..., description="Type of source (markdown, transcript, text, etc.)")
    source_path: str = Field(..., description="Original source file path")
    ingested_at: datetime = Field(..., description="Ingestion timestamp")
    adapter: str | None = Field(default=None, description="Adapter used for ingestion")

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        """Validate source type is not empty."""
        if not v or not v.strip():
            raise ValueError("Source type cannot be empty")
        return v

    @field_validator("source_path")
    @classmethod
    def validate_source_path(cls, v: str) -> str:
        """Validate source path is not empty."""
        if not v or not v.strip():
            raise ValueError("Source path cannot be empty")
        return v


class QAFrontmatter(PageFrontmatter):
    """Frontmatter schema for Q&A pages.

    Q&A pages capture a specific question and its practical answer, distinct
    from free-form pages or concepts. They're the natural shape for knowledge
    extracted from assistant sessions ("how do I X?" → "do Y").
    """

    kind: Literal["qa"] = Field(default="qa", description="Page type")
    question: str = Field(..., description="The question being answered")
    answer: str = Field(..., description="Practical answer to the question")
    related_pages: list[str] = Field(
        default_factory=list, description="Related page IDs (concepts, entities)"
    )

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        """Validate question is not empty."""
        if not v or not v.strip():
            raise ValueError("Question cannot be empty")
        return v

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, v: str) -> str:
        """Validate answer is not empty."""
        if not v or not v.strip():
            raise ValueError("Answer cannot be empty")
        return v


def create_frontmatter(kind: str, **kwargs) -> PageFrontmatter:
    """Factory function to create appropriate frontmatter based on kind.

    Args:
        kind: Page kind (page, entity, concept, source, qa)
        **kwargs: Frontmatter fields

    Returns:
        Appropriate frontmatter instance

    Raises:
        ValueError: If kind is invalid
    """
    frontmatter_classes = {
        "page": PageFrontmatter,
        "entity": EntityFrontmatter,
        "concept": ConceptFrontmatter,
        "source": SourceFrontmatter,
        "qa": QAFrontmatter,
    }

    if kind not in frontmatter_classes:
        raise ValueError(f"Invalid page kind: {kind}")

    return cast(PageFrontmatter, frontmatter_classes[kind](kind=kind, **kwargs))

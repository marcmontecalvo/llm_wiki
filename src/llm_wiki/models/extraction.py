"""Extraction schemas for model-generated structured data."""

from pydantic import BaseModel, Field


class EntityExtraction(BaseModel):
    """Schema for extracted entity information."""

    name: str = Field(..., description="Entity name")
    entity_type: str = Field(..., description="Type of entity (person, org, product, etc.)")
    description: str | None = Field(default=None, description="Brief description of the entity")
    aliases: list[str] = Field(default_factory=list, description="Alternative names or aliases")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Extraction confidence (0-1)"
    )
    source_reference: str | None = Field(
        default=None, description="Reference to source where entity was found"
    )
    context: str | None = Field(default=None, description="Context where entity appeared")


class ConceptExtraction(BaseModel):
    """Schema for extracted concept information."""

    name: str = Field(..., description="Concept name")
    definition: str | None = Field(default=None, description="Concept definition")
    category: str | None = Field(default=None, description="Concept category or domain")
    related_concepts: list[str] = Field(default_factory=list, description="Related concept names")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Extraction confidence (0-1)"
    )
    source_reference: str | None = Field(
        default=None, description="Reference to source where concept was found"
    )
    examples: list[str] = Field(default_factory=list, description="Example uses of the concept")


class ClaimExtraction(BaseModel):
    """Schema for extracted factual claim information."""

    claim: str = Field(..., description="The factual claim statement")
    subject: str | None = Field(default=None, description="Subject of the claim")
    predicate: str | None = Field(default=None, description="Predicate/relationship")
    object: str | None = Field(default=None, description="Object of the claim")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Extraction confidence (0-1)"
    )
    source_reference: str = Field(..., description="Reference to source (required for claims)")
    temporal_context: str | None = Field(default=None, description="When this claim is/was true")
    qualifiers: list[str] = Field(
        default_factory=list, description="Qualifiers or conditions on the claim"
    )


class RelationshipExtraction(BaseModel):
    """Schema for extracted relationship between entities/concepts."""

    source_entity: str = Field(..., description="Source entity/concept")
    relationship_type: str = Field(..., description="Type of relationship")
    target_entity: str = Field(..., description="Target entity/concept")
    description: str | None = Field(default=None, description="Description of the relationship")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Extraction confidence (0-1)"
    )
    source_reference: str | None = Field(
        default=None, description="Reference to source where relationship was found"
    )
    bidirectional: bool = Field(default=False, description="Whether relationship goes both ways")


class ExtractionResult(BaseModel):
    """Combined result from all extraction passes."""

    entities: list[EntityExtraction] = Field(default_factory=list, description="Extracted entities")
    concepts: list[ConceptExtraction] = Field(
        default_factory=list, description="Extracted concepts"
    )
    claims: list[ClaimExtraction] = Field(default_factory=list, description="Extracted claims")
    relationships: list[RelationshipExtraction] = Field(
        default_factory=list, description="Extracted relationships"
    )
    extraction_metadata: dict[str, str] = Field(
        default_factory=dict, description="Metadata about the extraction process"
    )

    def has_extractions(self) -> bool:
        """Check if any extractions were made.

        Returns:
            True if at least one extraction exists
        """
        return bool(self.entities or self.concepts or self.claims or self.relationships)

    def total_count(self) -> int:
        """Get total number of extractions.

        Returns:
            Total count of all extractions
        """
        return len(self.entities) + len(self.concepts) + len(self.claims) + len(self.relationships)

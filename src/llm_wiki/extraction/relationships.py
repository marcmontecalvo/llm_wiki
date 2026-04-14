"""Relationship extraction from content."""

import json
import logging
from typing import Any

from llm_wiki.models.client import ModelClient

logger = logging.getLogger(__name__)

# Standard relationship types taxonomy
RELATIONSHIP_TYPES = {
    # Technical relationships
    "uses": "A uses B (direct dependency or application)",
    "depends_on": "A depends on B (requires B to function)",
    "implements": "A implements B (concrete implementation of abstraction)",
    "extends": "A extends B (builds upon or adds to B)",
    "integrates_with": "A integrates with B (works together)",
    "requires": "A requires B (needs B as prerequisite)",
    "provides": "A provides B (offers or supplies B)",
    "wraps": "A wraps B (encapsulates B)",
    # Organizational relationships
    "works_for": "A works for B (employment relationship)",
    "manages": "A manages B (has authority/responsibility over B)",
    "reports_to": "A reports to B (supervisory relationship)",
    "collaborates_with": "A collaborates with B (works together)",
    "competes_with": "A competes with B (rivals)",
    "owns": "A owns B (possesses/controls B)",
    # Temporal relationships
    "before": "A comes before B (in time)",
    "after": "A comes after B (in time)",
    "during": "A happens during B (temporal overlap)",
    "influences": "A influences B (affects behavior/development)",
    # Spatial/structural relationships
    "located_in": "A is located in B (geographical or organizational location)",
    "part_of": "A is part of B (component relationship)",
    "contains": "A contains B (has B as component)",
    "includes": "A includes B (membership or composition)",
    # Knowledge/reference relationships
    "cites": "A cites B (references or quotes B)",
    "references": "A references B (points to or mentions B)",
    "related_to": "A is related to B (general connection)",
    "similar_to": "A is similar to B (shares characteristics)",
    "contrasts_with": "A contrasts with B (has opposing characteristics)",
}


class RelationshipExtractor:
    """Extracts relationships from content using LLM."""

    def __init__(self, client: ModelClient):
        """Initialize relationship extractor.

        Args:
            client: LLM client for extraction
        """
        self.client = client

    def extract_relationships(
        self, content: str, metadata: dict[str, Any], available_entities: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Extract relationships between entities from content.

        Args:
            content: Page content (markdown)
            metadata: Page metadata
            available_entities: List of known entity names to focus on (optional)

        Returns:
            List of relationship dictionaries with source_entity, relationship_type, target_entity, etc.

        Raises:
            Exception: If extraction fails
        """
        title = metadata.get("title", "Untitled")

        # Build entity context if provided
        entity_context = ""
        if available_entities:
            entity_context = "\nKnown entities to look for relationships between:\n"
            entity_context += "\n".join(f"- {entity}" for entity in available_entities[:20])

        # Build relationship types info for prompt
        relationship_types_info = "Possible relationship types:\n"
        for rel_type, description in list(RELATIONSHIP_TYPES.items())[:15]:
            relationship_types_info += f"- {rel_type}: {description}\n"

        prompt = f"""Extract key relationships between entities from this content.

A relationship consists of:
- Source entity: The subject of the relationship
- Relationship type: The type of connection
- Target entity: The object of the relationship
- Bidirectional: Whether the relationship goes both ways

{relationship_types_info}

For each relationship, provide:
- source_entity: Name of source entity
- relationship_type: One of the types listed above, or a custom type
- target_entity: Name of target entity
- description: Brief description of the relationship (optional)
- confidence: Confidence score 0.0-1.0 based on how clearly stated it is
- bidirectional: true if relationship goes both ways, false otherwise

Title: {title}
{entity_context}

Content:
{content[:3000]}

Respond with JSON object:
{{"relationships": [{{"source_entity": "...", "relationship_type": "...", "target_entity": "...", "description": "...", "confidence": 0.9, "bidirectional": false}}]}}"""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.client.chat_completion(
                messages, response_format={"type": "json_object"}
            )

            data = json.loads(response)

            # Handle different response formats
            if isinstance(data, dict) and "relationships" in data:
                relationships = data["relationships"]
            elif isinstance(data, list):
                relationships = data
            else:
                logger.warning(f"Unexpected relationship response format: {data}")
                return []

            # Validate and clean relationships
            validated = []
            for rel in relationships:
                if (
                    isinstance(rel, dict)
                    and "source_entity" in rel
                    and "relationship_type" in rel
                    and "target_entity" in rel
                ):
                    validated_rel = {
                        "source_entity": str(rel["source_entity"]).strip(),
                        "relationship_type": str(rel["relationship_type"]).strip().lower(),
                        "target_entity": str(rel["target_entity"]).strip(),
                        "description": str(rel.get("description", "")).strip() or None,
                        "confidence": float(rel.get("confidence", 0.9)),
                        "bidirectional": bool(rel.get("bidirectional", False)),
                    }

                    # Validate confidence is in range
                    conf = validated_rel["confidence"]
                    if isinstance(conf, (int, float)) and 0.0 <= conf <= 1.0:
                        validated.append(validated_rel)

            return validated[:15]  # Max 15 relationships

        except Exception as e:
            logger.error(f"Failed to extract relationships: {e}")
            return []  # Don't fail completely

    def extract_relationships_with_context(
        self,
        content: str,
        metadata: dict[str, Any],
        entities: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Extract relationships with entity context.

        Args:
            content: Page content (markdown)
            metadata: Page metadata
            entities: List of extracted entities with names

        Returns:
            List of relationships

        Raises:
            Exception: If extraction fails
        """
        entity_names: list[str] = []
        if entities:
            entity_names = [
                str(entity.get("name"))
                for entity in entities
                if "name" in entity and entity.get("name")
            ]

        return self.extract_relationships(content, metadata, entity_names)

    def normalize_relationship_type(self, rel_type: str) -> str:
        """Normalize relationship type to standard taxonomy.

        Args:
            rel_type: Raw relationship type string

        Returns:
            Normalized relationship type
        """
        normalized = rel_type.strip().lower().replace(" ", "_")

        # Direct match
        if normalized in RELATIONSHIP_TYPES:
            return normalized

        # Try to find similar match
        for standard_type in RELATIONSHIP_TYPES:
            if standard_type.startswith(normalized[:3]):
                return standard_type

        # Return as-is if no match (custom type)
        return normalized

    def create_bidirectional_relationships(
        self, relationships: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Create reverse relationships for bidirectional ones.

        Args:
            relationships: List of extracted relationships

        Returns:
            List with bidirectional relationships doubled
        """
        result = list(relationships)

        for rel in relationships:
            if rel.get("bidirectional"):
                reverse_rel = {
                    "source_entity": rel["target_entity"],
                    "relationship_type": rel["relationship_type"],
                    "target_entity": rel["source_entity"],
                    "description": rel.get("description"),
                    "confidence": rel.get("confidence", 0.9),
                    "bidirectional": True,
                }
                result.append(reverse_rel)

        return result

"""Relationship index for fast querying of entity relationships."""

import json
import logging
from pathlib import Path
from typing import Any

from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


class RelationshipIndex:
    """Index for relationships between wiki pages/entities."""

    def __init__(self, index_dir: Path | None = None):
        """Initialize relationship index.

        Args:
            index_dir: Directory to store index (defaults to wiki_system/index)
        """
        self.index_dir = index_dir or Path("wiki_system/index")
        self.index_dir.mkdir(parents=True, exist_ok=True)

        # In-memory indexes
        # subject -> list of {relationship_type, target, source_page, confidence}
        self.by_subject: dict[str, list[dict[str, Any]]] = {}
        # target -> list of {relationship_type, subject, source_page, confidence}
        self.by_target: dict[str, list[dict[str, Any]]] = {}
        # relationship_type -> list of (subject, target, source_page)
        self.by_type: dict[str, list[tuple[str, str, str]]] = {}

    def add_relationship(
        self,
        source_page: str,
        relationship: dict[str, Any],
    ) -> None:
        """Add a relationship to the index.

        Args:
            source_page: Page ID where relationship was found
            relationship: Relationship dictionary
        """
        source_entity = relationship.get("source_entity", "")
        target_entity = relationship.get("target_entity", "")
        rel_type = relationship.get("relationship_type", "")
        confidence = relationship.get("confidence", 0.9)

        if not source_entity or not target_entity:
            return

        # Normalize entity names for indexing
        source_key = source_entity.lower().strip()
        target_key = target_entity.lower().strip()
        rel_type_key = rel_type.lower().strip()

        # Index by subject
        if source_key not in self.by_subject:
            self.by_subject[source_key] = []
        self.by_subject[source_key].append({
            "relationship_type": rel_type,
            "target": target_entity,
            "source_page": source_page,
            "confidence": confidence,
            "description": relationship.get("description"),
        })

        # Index by target (for reverse lookups)
        if target_key not in self.by_target:
            self.by_target[target_key] = []
        self.by_target[target_key].append({
            "relationship_type": rel_type,
            "subject": source_entity,
            "source_page": source_page,
            "confidence": confidence,
            "description": relationship.get("description"),
        })

        # Index by relationship type
        if rel_type_key not in self.by_type:
            self.by_type[rel_type_key] = []
        self.by_type[rel_type_key].append((source_key, target_key, source_page))

    def add_page_relationships(
        self,
        page_id: str,
        relationships: list[dict[str, Any]],
    ) -> None:
        """Add all relationships from a page.

        Args:
            page_id: Page identifier
            relationships: List of relationship dictionaries
        """
        for rel in relationships:
            self.add_relationship(page_id, rel)

    def get_outgoing_relationships(self, entity: str) -> list[dict[str, Any]]:
        """Get all relationships where entity is the subject.

        Args:
            entity: Entity name to search for

        Returns:
            List of relationship dictionaries
        """
        key = entity.lower().strip()
        return self.by_subject.get(key, [])

    def get_incoming_relationships(self, entity: str) -> list[dict[str, Any]]:
        """Get all relationships where entity is the target.

        Args:
            entity: Entity name to search for

        Returns:
            List of relationship dictionaries
        """
        key = entity.lower().strip()
        return self.by_target.get(key, [])

    def get_relationships_by_type(
        self,
        rel_type: str,
    ) -> list[dict[str, Any]]:
        """Get all relationships of a specific type.

        Args:
            rel_type: Relationship type to search for

        Returns:
            List of relationship dictionaries
        """
        key = rel_type.lower().strip()
        results = []
        for source_key, target_key, source_page in self.by_type.get(key, []):
            # Get full relationship data from by_subject
            for rel in self.by_subject.get(source_key, []):
                if rel["target"].lower() == target_key and rel["source_page"] == source_page:
                    results.append({
                        "subject": source_key,
                        "target": target_key,
                        **rel,
                    })
        return results

    def get_all_relationships(self, entity: str) -> list[dict[str, Any]]:
        """Get all relationships involving an entity (both incoming and outgoing).

        Args:
            entity: Entity name to search for

        Returns:
            List of relationship dictionaries with direction indicated
        """
        outgoing = self.get_outgoing_relationships(entity)
        incoming = self.get_incoming_relationships(entity)

        # Mark direction
        for rel in outgoing:
            rel["direction"] = "outgoing"
        for rel in incoming:
            rel["direction"] = "incoming"

        return outgoing + incoming

    def find_related(
        self,
        entity: str,
        rel_type: str | None = None,
        min_confidence: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Find entities related to the given entity.

        Args:
            entity: Entity to find relations for
            rel_type: Optional relationship type filter
            min_confidence: Minimum confidence threshold

        Returns:
            List of related entity dictionaries
        """
        all_rels = self.get_all_relationships(entity)

        # Filter by relationship type if specified
        if rel_type:
            all_rels = [
                r for r in all_rels
                if r.get("relationship_type", "").lower() == rel_type.lower()
            ]

        # Filter by confidence
        all_rels = [
            r for r in all_rels
            if r.get("confidence", 0.0) >= min_confidence
        ]

        return all_rels

    def get_stats(self) -> dict[str, int]:
        """Get relationship index statistics.

        Returns:
            Dictionary with index statistics
        """
        return {
            "unique_subjects": len(self.by_subject),
            "unique_targets": len(self.by_target),
            "unique_types": len(self.by_type),
            "total_relationships": sum(len(v) for v in self.by_subject.values()),
        }

    def save(self) -> None:
        """Save index to disk."""
        index_file = self.index_dir / "relationships.json"

        data = {
            "by_subject": self.by_subject,
            "by_target": self.by_target,
            "by_type": {k: list(v) for k, v in self.by_type.items()},
        }

        with index_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        stats = self.get_stats()
        logger.info(f"Saved relationship index ({stats['total_relationships']} relationships)")

    def load(self) -> None:
        """Load index from disk."""
        index_file = self.index_dir / "relationships.json"

        if not index_file.exists():
            logger.info("No existing relationship index found")
            return

        with index_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        self.by_subject = data.get("by_subject", {})
        self.by_target = data.get("by_target", {})
        # Convert lists back to sets of tuples (tuples were saved as lists in JSON)
        by_type_data = data.get("by_type", {})
        self.by_type = {}
        for k, v_list in by_type_data.items():
            self.by_type[k] = set(tuple(v) if isinstance(v, list) else v for v in v_list)

        stats = self.get_stats()
        logger.info(f"Loaded relationship index ({stats['total_relationships']} relationships)")

    def rebuild_from_pages(self, wiki_base: Path | None = None) -> int:
        """Rebuild index from all wiki pages.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)

        Returns:
            Number of relationships indexed
        """
        wiki_base = wiki_base or Path("wiki_system")

        # Clear existing index
        self.by_subject.clear()
        self.by_target.clear()
        self.by_type.clear()

        count = 0
        domains_dir = wiki_base / "domains"
        if not domains_dir.exists():
            logger.warning(f"Domains directory not found: {domains_dir}")
            return 0

        # Scan all domains
        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            pages_dir = domain_dir / "pages"
            if not pages_dir.exists():
                continue

            # Index all markdown files
            for page_file in pages_dir.glob("*.md"):
                try:
                    content = page_file.read_text(encoding="utf-8")
                    metadata, _ = parse_frontmatter(content)

                    page_id = metadata.get("id", page_file.stem)
                    relationships = metadata.get("relationships", [])

                    if relationships:
                        self.add_page_relationships(page_id, relationships)
                        count += len(relationships)

                except Exception as e:
                    logger.error(f"Failed to index relationships from {page_file}: {e}")

        # Also check shared pages
        shared_dir = wiki_base / "shared" / "pages"
        if shared_dir.exists():
            for page_file in shared_dir.glob("*.md"):
                try:
                    content = page_file.read_text(encoding="utf-8")
                    metadata, _ = parse_frontmatter(content)

                    page_id = metadata.get("id", page_file.stem)
                    relationships = metadata.get("relationships", [])

                    if relationships:
                        self.add_page_relationships(page_id, relationships)
                        count += len(relationships)

                except Exception as e:
                    logger.error(f"Failed to index relationships from {page_file}: {e}")

        logger.info(f"Rebuilt relationship index: {count} relationships")
        return count
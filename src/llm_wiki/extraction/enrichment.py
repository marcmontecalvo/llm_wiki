"""Page enrichment with extracted metadata."""

import logging
from pathlib import Path
from typing import Any

from llm_wiki.utils.frontmatter import parse_frontmatter, write_frontmatter

logger = logging.getLogger(__name__)


class PageEnricher:
    """Enriches pages with extracted metadata."""

    def enrich_page(
        self,
        filepath: Path,
        extracted_metadata: dict[str, Any],
        entities: list[dict[str, Any]] | None = None,
        concepts: list[dict[str, Any]] | None = None,
        relationships: list[dict[str, Any]] | None = None,
    ) -> Path:
        """Enrich a page with extracted metadata.

        Args:
            filepath: Path to page file
            extracted_metadata: Metadata from ContentExtractor
            entities: Extracted entities (optional)
            concepts: Extracted concepts (optional)
            relationships: Extracted relationships (optional)

        Returns:
            Path to enriched page

        Raises:
            Exception: If enrichment fails
        """
        try:
            # Read existing page
            content_text = filepath.read_text(encoding="utf-8")
            existing_metadata, body = parse_frontmatter(content_text)

            # Merge metadata (existing takes precedence for most fields)
            enriched_metadata = self._merge_metadata(
                existing_metadata, extracted_metadata, entities, concepts, relationships
            )

            # Write enriched page
            enriched_content = write_frontmatter(enriched_metadata, body)
            filepath.write_text(enriched_content, encoding="utf-8")

            logger.info(f"Enriched page: {filepath.name}")
            return filepath

        except Exception as e:
            logger.error(f"Failed to enrich page {filepath}: {e}")
            raise

    def _merge_metadata(
        self,
        existing: dict[str, Any],
        extracted: dict[str, Any],
        entities: list[dict[str, Any]] | None,
        concepts: list[dict[str, Any]] | None,
        relationships: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Merge existing and extracted metadata.

        Args:
            existing: Existing frontmatter
            extracted: Extracted metadata
            entities: Extracted entities
            concepts: Extracted concepts
            relationships: Extracted relationships

        Returns:
            Merged metadata dictionary
        """
        # Start with existing metadata
        merged = dict(existing)

        # Add/update extracted fields (only if not already present)
        for key in ["kind", "summary"]:
            if key not in merged or not merged[key]:
                if key in extracted:
                    merged[key] = extracted[key]

        # Merge tags (combine existing and extracted)
        existing_tags = set(merged.get("tags", []))
        extracted_tags = set(extracted.get("tags", []))
        all_tags = list(existing_tags | extracted_tags)
        if all_tags:
            merged["tags"] = sorted(all_tags)[:10]  # Max 10 tags

        # Add entities if extracted
        if entities:
            merged["entities"] = entities

        # Add concepts if extracted
        if concepts:
            merged["concepts"] = concepts

        # Add relationships if extracted
        if relationships:
            merged["relationships"] = relationships

        # Update status
        merged["status"] = "enriched"

        return merged

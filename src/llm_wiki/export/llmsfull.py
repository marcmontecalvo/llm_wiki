"""llms-full.txt exporter with comprehensive page data for LLM consumption."""

import json
import logging
from pathlib import Path
from typing import Any

from llm_wiki.index.backlinks import BacklinkIndex
from llm_wiki.models.extraction import ExtractionResult
from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


class LLMSFullExporter:
    """Exporter for llms-full.txt format (comprehensive LLM-optimized context)."""

    def __init__(self, wiki_base: Path | None = None):
        """Initialize llms-full.txt exporter.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)
        """
        self.wiki_base = wiki_base or Path("wiki_system")
        self.backlink_index = BacklinkIndex(index_dir=self.wiki_base / "index")

    def _load_extraction_data(self, page_id: str) -> ExtractionResult | None:
        """Load extracted data (claims, relationships, entities, concepts) for a page.

        Args:
            page_id: Page identifier

        Returns:
            ExtractionResult if extraction data exists, None otherwise
        """
        extraction_file = self.wiki_base / "index" / f"{page_id}_extraction.json"

        if not extraction_file.exists():
            return None

        try:
            data = json.loads(extraction_file.read_text(encoding="utf-8"))
            return ExtractionResult(**data)
        except Exception as e:
            logger.debug(f"Failed to load extraction data for {page_id}: {e}")
            return None

    def _format_metadata_section(self, metadata: dict[str, Any]) -> str:
        """Format metadata section for a page.

        Args:
            metadata: Page metadata dictionary

        Returns:
            Formatted metadata section
        """
        lines = []
        lines.append("<!-- Metadata -->")

        # Core metadata
        for key in ["id", "domain", "kind", "status", "confidence"]:
            if key in metadata and metadata[key] is not None:
                value = metadata[key]
                lines.append(f"- {key}: {value}")

        # Dates
        if "created_at" in metadata and metadata["created_at"]:
            lines.append(f"- created_at: {metadata['created_at']}")
        if "updated_at" in metadata and metadata["updated_at"]:
            lines.append(f"- updated_at: {metadata['updated_at']}")

        # Entity-specific metadata
        if "entity_type" in metadata and metadata["entity_type"]:
            lines.append(f"- entity_type: {metadata['entity_type']}")
        if "aliases" in metadata and metadata["aliases"]:
            lines.append(f"- aliases: {', '.join(metadata['aliases'])}")

        # Concept-specific metadata
        if "related_concepts" in metadata and metadata["related_concepts"]:
            lines.append(f"- related_concepts: {', '.join(metadata['related_concepts'])}")

        # Source metadata
        if "source_type" in metadata and metadata["source_type"]:
            lines.append(f"- source_type: {metadata['source_type']}")

        # Tags
        if "tags" in metadata and metadata["tags"]:
            lines.append(f"- tags: {', '.join(metadata['tags'])}")

        # Sources
        if "sources" in metadata and metadata["sources"]:
            lines.append(f"- sources: {'; '.join(metadata['sources'])}")

        lines.append("")
        return "\n".join(lines)

    def _format_summary_section(self, metadata: dict[str, Any]) -> str | None:
        """Format summary section if available.

        Args:
            metadata: Page metadata dictionary

        Returns:
            Formatted summary section or None
        """
        if "summary" not in metadata or not metadata["summary"]:
            return None

        lines = []
        lines.append("<!-- Summary -->")
        lines.append(f"> {metadata['summary']}")
        lines.append("")
        return "\n".join(lines)

    def _format_entities_section(self, extraction: ExtractionResult) -> str | None:
        """Format extracted entities section.

        Args:
            extraction: Extraction result

        Returns:
            Formatted entities section or None
        """
        if not extraction.entities:
            return None

        lines = []
        lines.append("<!-- Entities -->")
        lines.append("")

        for entity in extraction.entities:
            lines.append(f"#### {entity.name}")
            lines.append(f"- Type: {entity.entity_type}")
            if entity.description:
                lines.append(f"- Description: {entity.description}")
            if entity.aliases:
                lines.append(f"- Aliases: {', '.join(entity.aliases)}")
            if entity.confidence < 1.0:
                lines.append(f"- Confidence: {entity.confidence:.2f}")
            if entity.context:
                lines.append(f"- Context: {entity.context}")
            lines.append("")

        return "\n".join(lines)

    def _format_concepts_section(self, extraction: ExtractionResult) -> str | None:
        """Format extracted concepts section.

        Args:
            extraction: Extraction result

        Returns:
            Formatted concepts section or None
        """
        if not extraction.concepts:
            return None

        lines = []
        lines.append("<!-- Concepts -->")
        lines.append("")

        for concept in extraction.concepts:
            lines.append(f"#### {concept.name}")
            if concept.definition:
                lines.append(f"- Definition: {concept.definition}")
            if concept.category:
                lines.append(f"- Category: {concept.category}")
            if concept.related_concepts:
                lines.append(f"- Related: {', '.join(concept.related_concepts)}")
            if concept.confidence < 1.0:
                lines.append(f"- Confidence: {concept.confidence:.2f}")
            if concept.examples:
                lines.append(f"- Examples: {'; '.join(concept.examples[:3])}")
            lines.append("")

        return "\n".join(lines)

    def _format_claims_section(self, extraction: ExtractionResult) -> str | None:
        """Format extracted claims section.

        Args:
            extraction: Extraction result

        Returns:
            Formatted claims section or None
        """
        if not extraction.claims:
            return None

        lines = []
        lines.append("<!-- Claims -->")
        lines.append("")

        for claim in extraction.claims:
            # Format: "claim statement (confidence)"
            confidence_pct = f"{claim.confidence:.0%}"
            lines.append(f"- {claim.claim} ({confidence_pct})")

            # Add details if available
            if claim.subject or claim.predicate or claim.object:
                detail_parts = []
                if claim.subject:
                    detail_parts.append(f"subject={claim.subject}")
                if claim.predicate:
                    detail_parts.append(f"predicate={claim.predicate}")
                if claim.object:
                    detail_parts.append(f"object={claim.object}")
                lines.append(f"  - {', '.join(detail_parts)}")

            if claim.temporal_context:
                lines.append(f"  - temporal: {claim.temporal_context}")

            if claim.qualifiers:
                lines.append(f"  - qualifiers: {'; '.join(claim.qualifiers)}")

        lines.append("")
        return "\n".join(lines)

    def _format_relationships_section(self, extraction: ExtractionResult) -> str | None:
        """Format extracted relationships section.

        Args:
            extraction: Extraction result

        Returns:
            Formatted relationships section or None
        """
        if not extraction.relationships:
            return None

        lines = []
        lines.append("<!-- Relationships -->")
        lines.append("")

        for rel in extraction.relationships:
            # Format: "source --[relationship_type]--> target (confidence)"
            confidence_pct = f"{rel.confidence:.0%}"
            if rel.bidirectional:
                lines.append(
                    f"- {rel.source_entity} <--[{rel.relationship_type}]--> "
                    f"{rel.target_entity} ({confidence_pct})"
                )
            else:
                lines.append(
                    f"- {rel.source_entity} --[{rel.relationship_type}]--> "
                    f"{rel.target_entity} ({confidence_pct})"
                )

            if rel.description:
                lines.append(f"  - {rel.description}")

        lines.append("")
        return "\n".join(lines)

    def _format_links_section(self, page_id: str, metadata: dict[str, Any]) -> str | None:
        """Format forward links and backlinks section.

        Args:
            page_id: Page identifier
            metadata: Page metadata

        Returns:
            Formatted links section or None
        """
        forward_links = self.backlink_index.get_forward_links(page_id)
        backlinks = self.backlink_index.get_backlinks(page_id)
        broken_links = self.backlink_index.get_broken_links(page_id)

        # Include links from metadata as well
        metadata_links = metadata.get("links", [])

        has_content = bool(forward_links or backlinks or broken_links or metadata_links)

        if not has_content:
            return None

        lines = []
        lines.append("<!-- Links -->")
        lines.append("")

        if metadata_links:
            lines.append("**Links (from metadata):**")
            for link in metadata_links:
                lines.append(f"- [[{link}]]")
            lines.append("")

        if forward_links:
            lines.append("**Forward links:**")
            for link in forward_links:
                lines.append(f"- [[{link}]]")
            lines.append("")

        if backlinks:
            lines.append("**Backlinks:**")
            for link in backlinks:
                lines.append(f"- [[{link}]]")
            lines.append("")

        if broken_links:
            lines.append("**Broken links (targets not found):**")
            for link in broken_links:
                lines.append(f"- [[{link}]]")
            lines.append("")

        return "\n".join(lines)

    def export_page(
        self,
        page_file: Path,
        include_extractions: bool = True,
        include_links: bool = True,
    ) -> str:
        """Export a single page to llms-full.txt format.

        Args:
            page_file: Path to markdown file
            include_extractions: Include extracted data (entities, concepts, claims, relationships)
            include_links: Include backlink information

        Returns:
            Formatted llms-full.txt content for this page
        """
        try:
            content = page_file.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(content)
        except Exception as e:
            logger.error(f"Failed to export {page_file}: {e}")
            return ""

        page_id = metadata.get("id", page_file.stem)
        lines = []

        # Title
        title = metadata.get("title", page_file.stem)
        lines.append(f"# {title}")
        lines.append("")

        # Metadata section
        metadata_section = self._format_metadata_section(metadata)
        lines.append(metadata_section)

        # Summary section (if available)
        summary_section = self._format_summary_section(metadata)
        if summary_section:
            lines.append(summary_section)

        # Content section
        lines.append("<!-- Content -->")
        lines.append("")
        lines.append(body.strip())
        lines.append("")
        lines.append("")

        # Load extraction data if requested
        extraction = None
        if include_extractions:
            extraction = self._load_extraction_data(page_id)

        # Extracted data sections (if available)
        if extraction and extraction.has_extractions():
            entities_section = self._format_entities_section(extraction)
            if entities_section:
                lines.append(entities_section)
                lines.append("")

            concepts_section = self._format_concepts_section(extraction)
            if concepts_section:
                lines.append(concepts_section)
                lines.append("")

            claims_section = self._format_claims_section(extraction)
            if claims_section:
                lines.append(claims_section)
                lines.append("")

            relationships_section = self._format_relationships_section(extraction)
            if relationships_section:
                lines.append(relationships_section)
                lines.append("")

        # Links section (if requested)
        if include_links:
            links_section = self._format_links_section(page_id, metadata)
            if links_section:
                lines.append(links_section)
                lines.append("")

        return "\n".join(lines)

    def export_domain(
        self,
        domain_name: str,
        output_file: Path | None = None,
        min_quality: float = 0.0,
        max_pages: int | None = None,
        since_date: str | None = None,
    ) -> Path:
        """Export all pages in a domain to llms-full.txt.

        Args:
            domain_name: Domain identifier
            output_file: Optional output file path
            min_quality: Minimum confidence score to include (0.0-1.0)
            max_pages: Maximum number of pages to export (None = all)
            since_date: Only include pages updated at or after this ISO date (e.g. "2024-01-01")

        Returns:
            Path to generated llms-full.txt file
        """
        domain_dir = self.wiki_base / "domains" / domain_name
        pages_dir = domain_dir / "pages"

        if not pages_dir.exists():
            logger.warning(f"Pages directory not found: {pages_dir}")
            return output_file or Path(f"{domain_name}_llms-full.txt")

        # Load backlink index so link data is available during export
        self.backlink_index.load()

        # Collect all page exports
        exports = []
        exported_count = 0

        for page_file in sorted(pages_dir.glob("*.md")):
            # Check max pages limit
            if max_pages and exported_count >= max_pages:
                break

            # Check quality and date filters
            try:
                content = page_file.read_text(encoding="utf-8")
                metadata, _ = parse_frontmatter(content)
                confidence = metadata.get("confidence", 0.0)
                if confidence < min_quality:
                    continue
                if since_date:
                    updated_at = metadata.get("updated_at") or metadata.get("created_at", "")
                    if updated_at and str(updated_at) < since_date:
                        continue
            except Exception as e:
                logger.debug(f"Failed to check quality for {page_file}: {e}")
                continue

            page_export = self.export_page(page_file)
            if page_export:
                exports.append(page_export)
                exports.append("---\n")
                exported_count += 1

        # Determine output path
        if not output_file:
            exports_dir = self.wiki_base / "exports"
            exports_dir.mkdir(exist_ok=True)
            output_file = exports_dir / f"{domain_name}_llms-full.txt"
        else:
            # Ensure parent directory exists
            output_file.parent.mkdir(parents=True, exist_ok=True)

        # Write output
        content = "\n".join(exports)
        output_file.write_text(content, encoding="utf-8")

        logger.info(f"Exported {exported_count} pages to {output_file}")

        return output_file

    def export_all(
        self,
        output_file: Path | None = None,
        min_quality: float = 0.0,
        max_pages: int | None = None,
        since_date: str | None = None,
    ) -> Path:
        """Export all domains to single llms-full.txt.

        Args:
            output_file: Optional output file path
            min_quality: Minimum confidence score to include (0.0-1.0)
            max_pages: Maximum number of pages to export (None = all)
            since_date: Only include pages updated at or after this ISO date (e.g. "2024-01-01")

        Returns:
            Path to generated llms-full.txt file
        """
        domains_dir = self.wiki_base / "domains"

        if not domains_dir.exists():
            logger.warning(f"Domains directory not found: {domains_dir}")
            return output_file or Path("llms-full.txt")

        # Load backlink index
        self.backlink_index.load()

        # Collect exports by domain
        exports = []
        total_pages = 0
        remaining_pages = max_pages

        for domain_dir in sorted(domains_dir.iterdir()):
            if not domain_dir.is_dir():
                continue

            domain_name = domain_dir.name
            pages_dir = domain_dir / "pages"

            if not pages_dir.exists():
                continue

            # Domain header
            exports.append(f"# Domain: {domain_name}")
            exports.append("")
            exports.append("---\n")

            # Export pages
            domain_pages = 0
            for page_file in sorted(pages_dir.glob("*.md")):
                # Check max pages limit
                if max_pages and remaining_pages is not None and remaining_pages <= 0:
                    break

                # Check quality and date filters
                try:
                    content = page_file.read_text(encoding="utf-8")
                    metadata, _ = parse_frontmatter(content)
                    confidence = metadata.get("confidence", 0.0)
                    if confidence < min_quality:
                        continue
                    if since_date:
                        updated_at = metadata.get("updated_at") or metadata.get("created_at", "")
                        if updated_at and str(updated_at) < since_date:
                            continue
                except Exception as e:
                    logger.debug(f"Failed to check quality for {page_file}: {e}")
                    continue

                page_export = self.export_page(page_file)
                if page_export:
                    exports.append(page_export)
                    exports.append("---\n")
                    domain_pages += 1
                    total_pages += 1

                    if remaining_pages is not None:
                        remaining_pages -= 1

            if domain_pages > 0:
                exports.append("\n")

        # Determine output path
        if not output_file:
            exports_dir = self.wiki_base / "exports"
            exports_dir.mkdir(exist_ok=True)
            output_file = exports_dir / "llms-full.txt"
        else:
            # Ensure parent directory exists
            output_file.parent.mkdir(parents=True, exist_ok=True)

        # Write output
        content = "\n".join(exports)
        output_file.write_text(content, encoding="utf-8")

        logger.info(f"Exported {total_pages} pages from all domains to {output_file}")

        return output_file

    def get_export_stats(self) -> dict[str, Any]:
        """Get statistics about what will be exported.

        Returns:
            Dictionary with statistics
        """
        domains_dir = self.wiki_base / "domains"

        if not domains_dir.exists():
            return {
                "total_pages": 0,
                "total_domains": 0,
                "pages_with_extractions": 0,
                "pages_with_backlinks": 0,
            }

        # Load backlink index
        self.backlink_index.load()

        total_pages = 0
        total_domains = 0
        pages_with_extractions = 0
        pages_with_backlinks = 0

        index_dir = self.wiki_base / "index"

        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            pages_dir = domain_dir / "pages"
            if not pages_dir.exists():
                continue

            total_domains += 1

            for page_file in pages_dir.glob("*.md"):
                total_pages += 1

                try:
                    metadata, _ = parse_frontmatter(page_file.read_text(encoding="utf-8"))
                    page_id = metadata.get("id", page_file.stem)

                    # Check for extractions
                    extraction_file = index_dir / f"{page_id}_extraction.json"
                    if extraction_file.exists():
                        pages_with_extractions += 1

                    # Check for backlinks
                    if self.backlink_index.get_backlinks(page_id):
                        pages_with_backlinks += 1
                except Exception:
                    pass

        return {
            "total_pages": total_pages,
            "total_domains": total_domains,
            "pages_with_extractions": pages_with_extractions,
            "pages_with_backlinks": pages_with_backlinks,
        }

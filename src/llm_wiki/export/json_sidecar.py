"""JSON sidecar exporter for machine-readable metadata."""

import json
import logging
from pathlib import Path

from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


class JSONSidecarExporter:
    """Exporter for JSON sidecars (per-page metadata files)."""

    def __init__(self, wiki_base: Path | None = None):
        """Initialize JSON sidecar exporter.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)
        """
        self.wiki_base = wiki_base or Path("wiki_system")

    def export_page(self, page_file: Path, output_file: Path | None = None) -> Path:
        """Export page metadata to JSON sidecar.

        Args:
            page_file: Path to markdown file
            output_file: Optional output file path

        Returns:
            Path to generated JSON file
        """
        try:
            content = page_file.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(content)
        except Exception as e:
            logger.error(f"Failed to export {page_file}: {e}")
            return output_file or page_file.with_suffix(".json")

        # Compute additional fields
        word_count = len(body.split())
        char_count = len(body)

        # Build JSON structure
        json_data = dict(metadata)
        json_data["_computed"] = {
            "word_count": word_count,
            "char_count": char_count,
            "has_content": word_count > 0,
        }

        # Determine output path
        if not output_file:
            output_file = page_file.with_suffix(".json")

        # Write JSON
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        return output_file

    def export_domain(self, domain_name: str) -> int:
        """Export JSON sidecars for all pages in a domain.

        Args:
            domain_name: Domain identifier

        Returns:
            Number of files exported
        """
        domain_dir = self.wiki_base / "domains" / domain_name
        pages_dir = domain_dir / "pages"

        if not pages_dir.exists():
            logger.warning(f"Pages directory not found: {pages_dir}")
            return 0

        count = 0
        for page_file in pages_dir.glob("*.md"):
            self.export_page(page_file)
            count += 1

        logger.info(f"Exported {count} JSON sidecars for domain '{domain_name}'")

        return count

    def export_all(self) -> int:
        """Export JSON sidecars for all pages.

        Returns:
            Total number of files exported
        """
        domains_dir = self.wiki_base / "domains"

        if not domains_dir.exists():
            logger.warning(f"Domains directory not found: {domains_dir}")
            return 0

        total = 0
        for domain_dir in domains_dir.iterdir():
            if domain_dir.is_dir():
                total += self.export_domain(domain_dir.name)

        logger.info(f"Exported {total} JSON sidecars total")

        return total

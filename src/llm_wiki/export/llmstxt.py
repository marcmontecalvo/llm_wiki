"""llms.txt exporter for LLM-optimized context files."""

import logging
from pathlib import Path

from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


class LLMSTxtExporter:
    """Exporter for llms.txt format (LLM-optimized context)."""

    def __init__(self, wiki_base: Path | None = None):
        """Initialize llms.txt exporter.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)
        """
        self.wiki_base = wiki_base or Path("wiki_system")

    def export_page(self, page_file: Path) -> str:
        """Export a single page to llms.txt format.

        Args:
            page_file: Path to markdown file

        Returns:
            Formatted llms.txt content
        """
        try:
            content = page_file.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(content)
        except Exception as e:
            logger.error(f"Failed to export {page_file}: {e}")
            return ""

        # Build llms.txt format
        lines = []

        # Header with metadata
        lines.append(f"# {metadata.get('title', page_file.stem)}")
        lines.append("")

        # Add metadata as structured comments
        if "id" in metadata:
            lines.append(f"<!-- id: {metadata['id']} -->")
        if "domain" in metadata:
            lines.append(f"<!-- domain: {metadata['domain']} -->")
        if "kind" in metadata:
            lines.append(f"<!-- kind: {metadata['kind']} -->")
        if "tags" in metadata and metadata["tags"]:
            tags_str = ", ".join(metadata["tags"])
            lines.append(f"<!-- tags: {tags_str} -->")

        lines.append("")

        # Add summary if present
        if "summary" in metadata and metadata["summary"]:
            lines.append(f"> {metadata['summary']}")
            lines.append("")

        # Add body content
        lines.append(body.strip())
        lines.append("")

        return "\n".join(lines)

    def export_domain(self, domain_name: str, output_file: Path | None = None) -> Path:
        """Export all pages in a domain to llms.txt.

        Args:
            domain_name: Domain identifier
            output_file: Optional output file path

        Returns:
            Path to generated llms.txt file
        """
        domain_dir = self.wiki_base / "domains" / domain_name
        pages_dir = domain_dir / "pages"

        if not pages_dir.exists():
            logger.warning(f"Pages directory not found: {pages_dir}")
            return output_file or Path(f"{domain_name}.txt")

        # Collect all page exports
        exports = []

        for page_file in sorted(pages_dir.glob("*.md")):
            page_export = self.export_page(page_file)
            if page_export:
                exports.append(page_export)
                exports.append("---\n")  # Page separator

        # Determine output path
        if not output_file:
            exports_dir = self.wiki_base / "exports"
            exports_dir.mkdir(exist_ok=True)
            output_file = exports_dir / f"{domain_name}_llms.txt"

        # Write output
        content = "\n".join(exports)
        output_file.write_text(content, encoding="utf-8")

        logger.info(f"Exported {len(exports) // 2} pages to {output_file}")

        return output_file

    def export_all(self, output_file: Path | None = None) -> Path:
        """Export all domains to single llms.txt.

        Args:
            output_file: Optional output file path

        Returns:
            Path to generated llms.txt file
        """
        domains_dir = self.wiki_base / "domains"

        if not domains_dir.exists():
            logger.warning(f"Domains directory not found: {domains_dir}")
            return output_file or Path("llms.txt")

        # Collect exports by domain
        exports = []
        total_pages = 0

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

            # Export pages
            for page_file in sorted(pages_dir.glob("*.md")):
                page_export = self.export_page(page_file)
                if page_export:
                    exports.append(page_export)
                    exports.append("---\n")
                    total_pages += 1

            exports.append("\n")

        # Determine output path
        if not output_file:
            exports_dir = self.wiki_base / "exports"
            exports_dir.mkdir(exist_ok=True)
            output_file = exports_dir / "llms.txt"

        # Write output
        content = "\n".join(exports)
        output_file.write_text(content, encoding="utf-8")

        logger.info(f"Exported {total_pages} pages from all domains to {output_file}")

        return output_file

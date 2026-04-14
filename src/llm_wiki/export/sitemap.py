"""Sitemap generator for wiki pages."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


class SitemapGenerator:
    """Generator for sitemap.xml."""

    def __init__(self, wiki_base: Path | None = None, base_url: str = ""):
        """Initialize sitemap generator.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)
            base_url: Base URL for wiki pages
        """
        self.wiki_base = wiki_base or Path("wiki_system")
        self.base_url = base_url or "https://example.com/wiki"

    def generate(self, output_file: Path | None = None) -> Path:
        """Generate sitemap.xml.

        Args:
            output_file: Optional output file path

        Returns:
            Path to generated sitemap.xml
        """
        # Create XML structure
        urlset = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")

        domains_dir = self.wiki_base / "domains"

        if not domains_dir.exists():
            logger.warning(f"Domains directory not found: {domains_dir}")
            return output_file or Path("sitemap.xml")

        page_count = 0

        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            pages_dir = domain_dir / "pages"
            if not pages_dir.exists():
                continue

            for page_file in pages_dir.glob("*.md"):
                try:
                    content = page_file.read_text(encoding="utf-8")
                    metadata, _ = parse_frontmatter(content)

                    page_id = metadata.get("id", page_file.stem)
                    url = f"{self.base_url}/{domain_dir.name}/{page_id}"

                    # Create URL element
                    url_elem = ET.SubElement(urlset, "url")
                    ET.SubElement(url_elem, "loc").text = url

                    # Add lastmod if available
                    updated = metadata.get("updated")
                    if updated:
                        ET.SubElement(url_elem, "lastmod").text = str(updated)
                    else:
                        # Use file modification time
                        mtime = datetime.fromtimestamp(page_file.stat().st_mtime, tz=UTC)
                        ET.SubElement(url_elem, "lastmod").text = mtime.strftime("%Y-%m-%d")

                    page_count += 1

                except Exception as e:
                    logger.error(f"Failed to process {page_file}: {e}")

        # Determine output path
        if not output_file:
            exports_dir = self.wiki_base / "exports"
            exports_dir.mkdir(exist_ok=True)
            output_file = exports_dir / "sitemap.xml"

        # Write XML
        tree = ET.ElementTree(urlset)
        ET.indent(tree, space="  ")
        tree.write(output_file, encoding="utf-8", xml_declaration=True)

        logger.info(f"Generated sitemap with {page_count} pages")

        return output_file

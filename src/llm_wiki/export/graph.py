"""Graph exporter for wiki relationships."""

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path

from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


class _DateTimeEncoder(json.JSONEncoder):
    def default(self, obj: object) -> object:
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


class GraphExporter:
    """Exporter for graph representation (nodes and edges)."""

    def __init__(self, wiki_base: Path | None = None):
        """Initialize graph exporter.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)
        """
        self.wiki_base = wiki_base or Path("wiki_system")

    def export_json(self, output_file: Path | None = None) -> Path:
        """Export wiki as JSON graph.

        Args:
            output_file: Optional output file path

        Returns:
            Path to generated JSON file
        """
        nodes = []
        edges = []
        page_ids = set()

        domains_dir = self.wiki_base / "domains"

        if not domains_dir.exists():
            logger.warning(f"Domains directory not found: {domains_dir}")
            return output_file or Path("graph.json")

        # Collect nodes
        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            pages_dir = domain_dir / "pages"
            if not pages_dir.exists():
                continue

            for page_file in pages_dir.glob("*.md"):
                try:
                    content = page_file.read_text(encoding="utf-8")
                    metadata, body = parse_frontmatter(content)

                    page_id = metadata.get("id", page_file.stem)
                    page_ids.add(page_id)

                    # Extract links from body
                    links = self._extract_links(body)

                    nodes.append(
                        {
                            "id": page_id,
                            "label": metadata.get("title", page_id),
                            "domain": metadata.get("domain", domain_dir.name),
                            "kind": metadata.get("kind", "page"),
                            "tags": metadata.get("tags", []),
                        }
                    )

                    # Add edges for links
                    for link in links:
                        edges.append(
                            {
                                "source": page_id,
                                "target": link,
                                "type": "link",
                            }
                        )

                except Exception as e:
                    logger.error(f"Failed to process {page_file}: {e}")

        # Filter edges to only valid targets
        edges = [e for e in edges if e["target"] in page_ids]

        # Determine output path
        if not output_file:
            exports_dir = self.wiki_base / "exports"
            exports_dir.mkdir(exist_ok=True)
            output_file = exports_dir / "graph.json"

        # Write output
        graph_data = {
            "nodes": nodes,
            "edges": edges,
        }

        with output_file.open("w", encoding="utf-8") as f:
            json.dump(graph_data, f, indent=2, cls=_DateTimeEncoder)

        logger.info(f"Exported graph: {len(nodes)} nodes, {len(edges)} edges")

        return output_file

    def _extract_links(self, content: str) -> list[str]:
        """Extract wiki links from content.

        Args:
            content: Page content

        Returns:
            List of linked page IDs
        """
        # Extract [[page-id]] style links
        links = re.findall(r"\[\[([^\]]+)\]\]", content)
        return links

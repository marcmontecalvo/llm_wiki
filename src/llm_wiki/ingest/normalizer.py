"""Normalization pipeline for source file ingestion."""

from pathlib import Path
from typing import Any

from llm_wiki.adapters.base import AdapterRegistry
from llm_wiki.config.loader import load_config
from llm_wiki.ingest.router import DomainRouter
from llm_wiki.utils.frontmatter import write_frontmatter
from llm_wiki.utils.id_gen import generate_page_id


class NormalizationPipeline:
    """Pipeline for normalizing source files to wiki pages."""

    def __init__(
        self,
        adapter_registry: AdapterRegistry,
        config_dir: Path | None = None,
    ):
        """Initialize normalization pipeline.

        Args:
            adapter_registry: Registry of source adapters
            config_dir: Path to config directory (defaults to ./config)
        """
        self.adapter_registry = adapter_registry
        self.config = load_config(config_dir or Path("config"))
        self.router = DomainRouter(self.config)

    def _determine_domain(self, metadata: dict[str, Any]) -> str:
        """Determine target domain for content.

        Args:
            metadata: Extracted metadata from source file

        Returns:
            Domain ID to route content to
        """
        return self.router.route(metadata)

    def process_file(self, filepath: Path) -> Path:
        """Process a source file through normalization pipeline.

        Args:
            filepath: Path to source file

        Returns:
            Path to queued normalized page

        Raises:
            ValueError: If no adapter can handle the file
            OSError: If file cannot be read or written
        """
        # Find appropriate adapter
        adapter = self.adapter_registry.get_adapter(filepath)
        if adapter is None:
            raise ValueError(f"No adapter found for file: {filepath}")

        # Process file to extract metadata and normalize content
        metadata, markdown = adapter.process(filepath)

        # Determine target domain
        domain = self._determine_domain(metadata)

        # Generate page ID
        title = metadata.get("title", filepath.stem)
        page_id = generate_page_id(title, domain)

        # Add generated fields to metadata
        metadata["id"] = page_id
        metadata["domain"] = domain
        metadata["status"] = "queued"
        metadata["kind"] = "source"  # Mark as source file for initial ingestion

        # Create final page content with frontmatter
        final_content = write_frontmatter(metadata, markdown)

        # Write to domain queue
        queue_dir = Path("wiki_system") / "domains" / domain / "queue"
        queue_dir.mkdir(parents=True, exist_ok=True)

        output_path = queue_dir / f"{page_id}.md"
        output_path.write_text(final_content, encoding="utf-8")

        return output_path

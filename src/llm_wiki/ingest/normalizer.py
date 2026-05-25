"""Normalization pipeline for source file ingestion."""

from pathlib import Path
from typing import Any

from llm_wiki.adapters.base import AdapterRegistry
from llm_wiki.config.loader import load_config
from llm_wiki.ingest.classifier import Classifier
from llm_wiki.utils.frontmatter import write_frontmatter
from llm_wiki.utils.id_gen import generate_page_id


class RoutingError(Exception):
    """Raised when a file cannot be routed to any configured domain."""


class NormalizationPipeline:
    """Pipeline for normalizing source files to wiki pages."""

    def __init__(
        self,
        adapter_registry: AdapterRegistry,
        config_dir: Path | None = None,
        wiki_base: Path | None = None,
    ):
        """Initialize normalization pipeline.

        Args:
            adapter_registry: Registry of source adapters
            config_dir: Path to config directory (defaults to ./config)
            wiki_base: Base wiki directory (defaults to wiki_system/)
        """
        self.adapter_registry = adapter_registry
        self.config = load_config(config_dir or Path("config"))
        self._wiki_base = wiki_base
        self._classifier = Classifier(config_dir=config_dir)

    def _determine_domain(self, content: str, metadata: dict[str, Any]) -> str:
        """Determine target domain for content based on file content.

        Uses LLM when available, falls back to keyword heuristics.

        Args:
            content: Normalized markdown body content
            metadata: Extracted metadata from source file

        Returns:
            Domain ID to route content to

        Raises:
            RoutingError: When classification returns no domain (shouldn't happen)
        """
        domain = self._classifier.classify(content, metadata)
        if not domain:
            source = metadata.get("source_path", "<unknown>")
            raise RoutingError(f"Classification returned no domain for: {source}")
        return domain

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
        metadata, body = adapter.process(filepath)

        # Determine target domain based on file content
        domain = self._determine_domain(body, metadata)

        # Generate page ID
        title = metadata.get("title", filepath.stem)
        page_id = generate_page_id(title, domain)

        # Add generated fields to metadata
        metadata["id"] = page_id
        metadata["domain"] = domain
        metadata["status"] = "queued"
        metadata["kind"] = "source"  # Mark as source file for initial ingestion

        # Create final page content with frontmatter
        final_content = write_frontmatter(metadata, body)

        # Write to domain queue (mirror the wiki_base structure from the input path)
        _wb = self._wiki_base or (filepath.parent.parent.parent)
        queue_dir = _wb / "domains" / domain / "queue"
        queue_dir.mkdir(parents=True, exist_ok=True)

        output_path = queue_dir / f"{page_id}.md"
        output_path.write_text(final_content, encoding="utf-8")

        return output_path

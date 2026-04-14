"""Base adapter interface for source file ingestion."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class SourceAdapter(ABC):
    """Base class for source file adapters.

    Adapters convert various input formats (markdown, text, transcripts, etc.)
    into a normalized markdown format with standardized frontmatter.
    """

    @classmethod
    @abstractmethod
    def can_parse(cls, filepath: Path) -> bool:
        """Check if this adapter can parse the given file.

        Args:
            filepath: Path to the file to check

        Returns:
            True if this adapter can parse the file
        """
        pass

    @abstractmethod
    def extract_metadata(self, filepath: Path, content: str) -> dict[str, Any]:
        """Extract metadata from the source file.

        Args:
            filepath: Path to the source file
            content: File content

        Returns:
            Dictionary of metadata (title, source_type, etc.)
        """
        pass

    @abstractmethod
    def normalize_to_markdown(self, filepath: Path, content: str) -> str:
        """Normalize the source content to markdown.

        Args:
            filepath: Path to the source file
            content: File content

        Returns:
            Normalized markdown content (without frontmatter)
        """
        pass

    def process(self, filepath: Path) -> tuple[dict[str, Any], str]:
        """Process a source file into metadata and markdown content.

        This is the main entry point for adapters. It reads the file,
        extracts metadata, and normalizes the content.

        Args:
            filepath: Path to the source file

        Returns:
            Tuple of (metadata dict, markdown content)

        Raises:
            OSError: If file cannot be read
        """
        # Read file content
        try:
            content = filepath.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Try with latin-1 as fallback
            content = filepath.read_text(encoding="latin-1")

        # Extract metadata
        metadata = self.extract_metadata(filepath, content)

        # Normalize to markdown
        markdown = self.normalize_to_markdown(filepath, content)

        return metadata, markdown


class AdapterRegistry:
    """Registry for source adapters."""

    def __init__(self):
        """Initialize adapter registry."""
        self._adapters: list[type[SourceAdapter]] = []

    def register(self, adapter_class: type[SourceAdapter]) -> None:
        """Register an adapter.

        Args:
            adapter_class: Adapter class to register
        """
        self._adapters.append(adapter_class)

    def get_adapter(self, filepath: Path) -> SourceAdapter | None:
        """Get the appropriate adapter for a file.

        Args:
            filepath: Path to the file

        Returns:
            Adapter instance or None if no adapter can handle the file
        """
        for adapter_class in self._adapters:
            if adapter_class.can_parse(filepath):
                return adapter_class()
        return None

    def get_all_adapters(self) -> list[type[SourceAdapter]]:
        """Get all registered adapters.

        Returns:
            List of adapter classes
        """
        return list(self._adapters)

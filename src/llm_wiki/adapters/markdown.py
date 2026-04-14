"""Markdown source adapter."""

from pathlib import Path
from typing import Any

from llm_wiki.adapters.base import SourceAdapter
from llm_wiki.utils.frontmatter import has_frontmatter, parse_frontmatter


class MarkdownAdapter(SourceAdapter):
    """Adapter for markdown (.md) files."""

    @classmethod
    def can_parse(cls, filepath: Path) -> bool:
        """Check if file is markdown.

        Args:
            filepath: Path to check

        Returns:
            True if file has .md or .markdown extension
        """
        return filepath.suffix.lower() in {".md", ".markdown"}

    def extract_metadata(self, filepath: Path, content: str) -> dict[str, Any]:
        """Extract metadata from markdown file.

        Args:
            filepath: Path to the markdown file
            content: File content

        Returns:
            Metadata dictionary
        """
        metadata: dict[str, Any] = {
            "source_type": "markdown",
            "source_path": str(filepath),
        }

        # If file has frontmatter, extract it
        if has_frontmatter(content):
            try:
                fm_dict, _ = parse_frontmatter(content)
                # Merge frontmatter into metadata
                metadata.update(fm_dict)
            except Exception:
                # If frontmatter parsing fails, continue without it
                pass

        # Generate title from filename if not in frontmatter
        if "title" not in metadata:
            # Use filename without extension as title
            metadata["title"] = filepath.stem.replace("-", " ").replace("_", " ").title()

        return metadata

    def normalize_to_markdown(self, filepath: Path, content: str) -> str:
        """Normalize markdown content.

        For markdown files, this mostly preserves the original content,
        but strips any existing frontmatter (which was extracted separately).

        Args:
            filepath: Path to the markdown file
            content: File content

        Returns:
            Normalized markdown (without frontmatter)
        """
        # If file has frontmatter, strip it and return body only
        if has_frontmatter(content):
            try:
                _, body = parse_frontmatter(content)
                return body.strip()
            except Exception:
                # If parsing fails, return original content
                pass

        # No frontmatter, return as-is
        return content.strip()

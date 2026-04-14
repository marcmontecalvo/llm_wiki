"""Text source adapter."""

from pathlib import Path
from typing import Any

from llm_wiki.adapters.base import SourceAdapter


class TextAdapter(SourceAdapter):
    """Adapter for plain text (.txt) files."""

    @classmethod
    def can_parse(cls, filepath: Path) -> bool:
        """Check if file is plain text.

        Args:
            filepath: Path to check

        Returns:
            True if file has .txt extension
        """
        return filepath.suffix.lower() == ".txt"

    def extract_metadata(self, filepath: Path, content: str) -> dict[str, Any]:
        """Extract metadata from text file.

        Args:
            filepath: Path to the text file
            content: File content

        Returns:
            Metadata dictionary
        """
        metadata: dict[str, Any] = {
            "source_type": "text",
            "source_path": str(filepath),
        }

        # Try to extract title from first line if it looks like a title
        lines = content.strip().split("\n")
        if lines:
            first_line = lines[0].strip()
            # Use first line as title if it's short and doesn't look like body text
            if first_line and len(first_line) < 100 and not first_line.endswith("."):
                metadata["title"] = first_line
            else:
                # Fall back to filename
                metadata["title"] = filepath.stem.replace("-", " ").replace("_", " ").title()
        else:
            # Empty file, use filename
            metadata["title"] = filepath.stem.replace("-", " ").replace("_", " ").title()

        return metadata

    def normalize_to_markdown(self, filepath: Path, content: str) -> str:
        """Normalize text content to markdown.

        Wraps plain text content in markdown formatting.

        Args:
            filepath: Path to the text file
            content: File content

        Returns:
            Markdown-formatted content
        """
        lines = content.strip().split("\n")
        if not lines:
            return ""

        # Check if first line should be the title (and was extracted as metadata)
        first_line = lines[0].strip()
        remaining_lines = lines

        # If first line looks like a title (short, no period), use it as H1
        if first_line and len(first_line) < 100 and not first_line.endswith("."):
            # Use first line as title, rest as content
            markdown_lines = [f"# {first_line}", ""]
            remaining_lines = lines[1:]
        else:
            # Generate title from filename
            title = filepath.stem.replace("-", " ").replace("_", " ").title()
            markdown_lines = [f"# {title}", ""]
            remaining_lines = lines

        # Add the content
        # Preserve paragraph breaks (double newlines) but wrap text
        if remaining_lines:
            # Join content, preserving structure
            body = "\n".join(remaining_lines).strip()
            markdown_lines.append(body)

        return "\n".join(markdown_lines)

"""Obsidian vault source adapter."""

import re
from pathlib import Path
from typing import Any

from llm_wiki.adapters.base import SourceAdapter
from llm_wiki.utils.frontmatter import has_frontmatter, parse_frontmatter


class ObsidianVaultAdapter(SourceAdapter):
    """Adapter for Obsidian vault markdown files.

    This adapter handles Obsidian-specific markdown formats including:
    - Standard Obsidian frontmatter (YAML properties)
    - Wikilinks: [[page-id]] and [[page-id|display]]
    - Embedded files: ![page-id]]
    - Hash tags: #tag syntax
    - Page ID derived from filename
    """

    # Regex for wikilinks: [[page-id]] or [[page-id|display]]
    WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

    # Regex for embedded files: ![page-id]] or ![page-id|display]]
    # Note: Obsidian embeds use ![[page-id]] syntax
    EMBEDDED_PATTERN = re.compile(r"!\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

    # Regex for hash tags: #tag
    HASHTAG_PATTERN = re.compile(r"(?:#)([a-zA-Z0-9_\-]+)")

    @classmethod
    def can_parse(cls, filepath: Path) -> bool:
        """Check if file is a valid Obsidian vault markdown file.

        Args:
            filepath: Path to check

        Returns:
            True if file has .md extension
        """
        return filepath.suffix.lower() == ".md"

    def extract_metadata(self, filepath: Path, content: str) -> dict[str, Any]:
        """Extract metadata from Obsidian vault file.

        Args:
            filepath: Path to the Obsidian file
            content: File content

        Returns:
            Metadata dictionary
        """
        metadata: dict[str, Any] = {
            "source_type": "obsidian",
            "source_path": str(filepath),
        }

        # Extract page ID from filename (filename without extension)
        page_id = filepath.stem
        metadata["page_id"] = page_id

        # If file has frontmatter, parse it (Obsidian uses properties format)
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
            metadata["title"] = page_id.replace("-", " ").replace("_", " ").title()

        # Extract wikilinks from content
        wikilinks = self.WIKILINK_PATTERN.findall(content)
        if wikilinks:
            metadata["wikilinks"] = wikilinks

        # Extract embedded files
        embedded = self.EMBEDDED_PATTERN.findall(content)
        if embedded:
            metadata["embedded"] = embedded

        # Extract hash tags from content
        hashtags = self.HASHTAG_PATTERN.findall(content)
        if hashtags:
            # Merge with existing tags if present
            existing_tags = metadata.get("tags", [])
            if isinstance(existing_tags, str):
                existing_tags = [existing_tags]
            elif not existing_tags:
                existing_tags = []
            # Add discovered hashtags
            all_tags = list(set(existing_tags + hashtags))
            metadata["tags"] = all_tags

        # Track if this is from a daily note
        daily_note_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}")
        if daily_note_pattern.match(page_id):
            metadata["is_daily_note"] = True

        # Track subdirectory as domain indicator
        # obsidian vaults often organize by folder
        if filepath.parent.name != ".":
            parent_folder = filepath.parent.name
            # Only use as domain if it's not the root vault folder
            if parent_folder != filepath.anchor.split("/")[-1]:
                metadata["vault_folder"] = parent_folder

        return metadata

    def normalize_to_markdown(self, filepath: Path, content: str) -> str:
        """Normalize Obsidian content to standard markdown.

        This converts Obsidian-specific syntax to the wiki's standard format:
        - Wikilinks are preserved (the wiki understands them)
        - Embedded files are converted to wikilinks
        - Hash tags in content are preserved

        Args:
            filepath: Path to the Obsidian file
            content: File content

        Returns:
            Normalized markdown (without frontmatter)
        """
        normalized = content

        # If file has frontmatter, strip it and process body
        if has_frontmatter(content):
            try:
                _, body = parse_frontmatter(content)
                normalized = body.strip()
            except Exception:
                # If parsing fails, proceed with original
                pass

        # Convert embedded files ![page-id]] to wikilinks [[page-id]]
        # Both embedded files and wikilinks work the same in the wiki
        normalized = self.EMBEDDED_PATTERN.sub(r"[[\1]]", normalized)

        # Note: We preserve hash tags in content as-is since they're valid markdown

        return normalized


def create_obsidian_adapter() -> ObsidianVaultAdapter:
    """Create an ObsidianVaultAdapter instance.

    Returns:
        A new ObsidianVaultAdapter instance
    """
    return ObsidianVaultAdapter()
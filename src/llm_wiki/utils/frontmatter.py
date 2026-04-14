"""Markdown frontmatter parsing and writing utilities."""

import re
from pathlib import Path
from typing import Any, cast

import frontmatter
from pydantic import ValidationError

from llm_wiki.models.page import PageFrontmatter, create_frontmatter


class FrontmatterError(Exception):
    """Raised when frontmatter operations fail."""

    pass


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from markdown content.

    Args:
        content: Markdown content with frontmatter

    Returns:
        Tuple of (frontmatter dict, body content)

    Raises:
        FrontmatterError: If frontmatter is invalid
    """
    try:
        post = frontmatter.loads(content)
        return dict(post.metadata), post.content
    except Exception as e:
        raise FrontmatterError(f"Failed to parse frontmatter: {e}") from e


def parse_and_validate(content: str) -> tuple[PageFrontmatter, str]:
    """Parse and validate frontmatter against page schemas.

    Args:
        content: Markdown content with frontmatter

    Returns:
        Tuple of (validated frontmatter object, body content)

    Raises:
        FrontmatterError: If frontmatter is invalid or missing required fields
    """
    metadata, body = parse_frontmatter(content)

    if not metadata:
        raise FrontmatterError("No frontmatter found in content")

    if "kind" not in metadata:
        raise FrontmatterError("Frontmatter missing required 'kind' field")

    try:
        frontmatter_obj = create_frontmatter(**metadata)
        return frontmatter_obj, body
    except ValidationError as e:
        raise FrontmatterError(f"Invalid frontmatter: {e}") from e
    except ValueError as e:
        raise FrontmatterError(f"Invalid frontmatter: {e}") from e


def write_frontmatter(frontmatter_dict: dict[str, Any], body: str) -> str:
    """Write frontmatter and body into markdown content.

    Args:
        frontmatter_dict: Frontmatter as dictionary
        body: Markdown body content

    Returns:
        Complete markdown content with frontmatter
    """
    post = frontmatter.Post(body, **frontmatter_dict)
    return cast(str, frontmatter.dumps(post))


def write_with_validation(frontmatter_obj: PageFrontmatter, body: str) -> str:
    """Write validated frontmatter object and body into markdown.

    Args:
        frontmatter_obj: Validated frontmatter object
        body: Markdown body content

    Returns:
        Complete markdown content with frontmatter
    """
    # Convert Pydantic model to dict, excluding None values for cleaner output
    frontmatter_dict = frontmatter_obj.model_dump(mode="json", exclude_none=True)
    return write_frontmatter(frontmatter_dict, body)


def read_page_file(filepath: Path | str) -> tuple[PageFrontmatter, str]:
    """Read and parse a wiki page file.

    Args:
        filepath: Path to markdown file

    Returns:
        Tuple of (validated frontmatter, body content)

    Raises:
        FrontmatterError: If file doesn't exist or frontmatter is invalid
        OSError: If file cannot be read
    """
    filepath = Path(filepath)

    if not filepath.exists():
        raise FrontmatterError(f"File does not exist: {filepath}")

    try:
        content = filepath.read_text(encoding="utf-8")
        return parse_and_validate(content)
    except OSError as e:
        raise OSError(f"Failed to read file {filepath}: {e}") from e


def write_page_file(filepath: Path | str, frontmatter_obj: PageFrontmatter, body: str) -> None:
    """Write a wiki page file with frontmatter.

    Args:
        filepath: Path to markdown file
        frontmatter_obj: Validated frontmatter object
        body: Markdown body content

    Raises:
        OSError: If file cannot be written
    """
    filepath = Path(filepath)

    # Ensure parent directory exists
    filepath.parent.mkdir(parents=True, exist_ok=True)

    content = write_with_validation(frontmatter_obj, body)

    try:
        filepath.write_text(content, encoding="utf-8")
    except OSError as e:
        raise OSError(f"Failed to write file {filepath}: {e}") from e


def has_frontmatter(content: str) -> bool:
    """Check if content has YAML frontmatter.

    Args:
        content: Markdown content

    Returns:
        True if frontmatter delimiters found
    """
    # Check for frontmatter delimiters at start
    return bool(re.match(r"^---\s*\n", content))


def extract_frontmatter_section(content: str) -> str | None:
    """Extract just the frontmatter section (without delimiters).

    Args:
        content: Markdown content

    Returns:
        Frontmatter YAML string, or None if no frontmatter
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if match:
        return match.group(1)
    return None

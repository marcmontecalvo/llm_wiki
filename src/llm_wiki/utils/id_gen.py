"""Page ID generation utilities."""

import re
import unicodedata
from collections.abc import Callable


def slugify(text: str, max_length: int = 100) -> str:
    """Convert text to URL-safe slug.

    Args:
        text: Input text to slugify
        max_length: Maximum length of slug (default 100)

    Returns:
        URL-safe slug (lowercase, hyphens only)

    Examples:
        >>> slugify("Hello World")
        'hello-world'
        >>> slugify("Python 3.11+")
        'python-3-11'
        >>> slugify("Über cool!")
        'uber-cool'
    """
    # Normalize unicode characters (e.g., ü -> u)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    # Convert to lowercase
    text = text.lower()

    # Replace non-alphanumeric characters with hyphens
    text = re.sub(r"[^a-z0-9]+", "-", text)

    # Remove leading/trailing hyphens
    text = text.strip("-")

    # Collapse multiple hyphens
    text = re.sub(r"-+", "-", text)

    # Truncate to max length
    if len(text) > max_length:
        text = text[:max_length].rstrip("-")

    return text


def generate_page_id(
    title: str,
    domain: str | None = None,
    collision_check: Callable[[str], bool] | None = None,
    max_length: int = 100,
) -> str:
    """Generate a unique page ID from title.

    Args:
        title: Page title
        domain: Optional domain prefix (e.g., 'general', 'homelab')
        collision_check: Optional function that returns True if ID exists
        max_length: Maximum length of ID (default 100)

    Returns:
        Unique page ID

    Examples:
        >>> generate_page_id("Machine Learning")
        'machine-learning'
        >>> generate_page_id("Python", domain="general")
        'general-python'
        >>> generate_page_id("Test", collision_check=lambda x: x == "test")
        'test-2'
    """
    # Generate base slug from title
    base_slug = slugify(title, max_length=max_length)

    if not base_slug:
        raise ValueError(f"Cannot generate ID from title: {title!r}")

    # Add domain prefix if provided
    if domain:
        domain_slug = slugify(domain)
        # Reserve space for domain prefix and hyphen
        remaining = max_length - len(domain_slug) - 1
        if remaining < 10:  # Ensure we have reasonable space
            # Use full slug without domain prefix
            page_id = base_slug
        else:
            base_slug = slugify(title, max_length=remaining)
            page_id = f"{domain_slug}-{base_slug}"
    else:
        page_id = base_slug

    # Handle collisions
    if collision_check:
        counter = 2
        original_id = page_id
        while collision_check(page_id):
            # Append counter: "my-page-2", "my-page-3", etc.
            suffix = f"-{counter}"
            # Ensure we don't exceed max_length
            truncated = original_id[: max_length - len(suffix)]
            page_id = f"{truncated}{suffix}"
            counter += 1

            # Safety check to prevent infinite loops
            if counter > 1000:
                raise ValueError(f"Too many ID collisions for title: {title!r}")

    return page_id


def generate_entity_id(
    name: str,
    entity_type: str | None = None,
    collision_check: Callable[[str], bool] | None = None,
    max_length: int = 100,
) -> str:
    """Generate a unique entity ID from name.

    Args:
        name: Entity name
        entity_type: Optional entity type prefix (e.g., 'person', 'company')
        collision_check: Optional function that returns True if ID exists
        max_length: Maximum length of ID (default 100)

    Returns:
        Unique entity ID

    Examples:
        >>> generate_entity_id("Apple Inc.")
        'apple-inc'
        >>> generate_entity_id("John Doe", entity_type="person")
        'person-john-doe'
    """
    return generate_page_id(
        title=name,
        domain=entity_type,
        collision_check=collision_check,
        max_length=max_length,
    )


def generate_concept_id(
    name: str,
    collision_check: Callable[[str], bool] | None = None,
    max_length: int = 100,
) -> str:
    """Generate a unique concept ID from name.

    Args:
        name: Concept name
        collision_check: Optional function that returns True if ID exists
        max_length: Maximum length of ID (default 100)

    Returns:
        Unique concept ID

    Examples:
        >>> generate_concept_id("Machine Learning")
        'machine-learning'
    """
    return generate_page_id(
        title=name,
        collision_check=collision_check,
        max_length=max_length,
    )

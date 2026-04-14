"""Content extraction service using LLM."""

import json
import logging
from pathlib import Path
from typing import Any

from llm_wiki.models.client import ModelClient, create_model_client
from llm_wiki.models.config import load_models_config
from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    """Raised when content extraction fails."""

    pass


class ContentExtractor:
    """Extracts structured information from content using LLM."""

    def __init__(self, client: ModelClient | None = None, config_dir: Path | None = None):
        """Initialize content extractor.

        Args:
            client: LLM client (if None, creates from config)
            config_dir: Path to config directory
        """
        if client is None:
            # Load model config and create client
            config_dir = config_dir or Path("config")
            models_config = load_models_config(config_dir / "models.yaml")
            # Get extraction model config
            provider_config = models_config.get_provider("extraction")
            client = create_model_client(provider_config)

        self.client = client

    def extract_page_kind(self, content: str, metadata: dict[str, Any]) -> str:
        """Determine page kind (entity, concept, or general).

        Args:
            content: Page content (markdown)
            metadata: Page metadata

        Returns:
            Page kind: "entity", "concept", or "page"

        Raises:
            ExtractionError: If extraction fails
        """
        # If kind is already set, use it
        if "kind" in metadata and metadata["kind"] != "source":
            return str(metadata["kind"])

        # Build prompt
        prompt = f"""Analyze this content and determine if it describes:
- An ENTITY (person, organization, tool, technology, product, service)
- A CONCEPT (idea, methodology, process, principle, topic)
- Neither (general content, notes, documentation)

Content title: {metadata.get("title", "Untitled")}

Content preview:
{content[:500]}

Respond with ONLY one word: entity, concept, or page"""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.client.chat_completion(messages).strip().lower()

            # Validate response
            if response in ("entity", "concept", "page"):
                return response

            logger.warning(f"Unexpected kind response: {response}, defaulting to 'page'")
            return "page"

        except Exception as e:
            raise ExtractionError(f"Failed to extract page kind: {e}") from e

    def extract_tags(self, content: str, metadata: dict[str, Any]) -> list[str]:
        """Extract relevant tags from content.

        Args:
            content: Page content (markdown)
            metadata: Page metadata

        Returns:
            List of tags

        Raises:
            ExtractionError: If extraction fails
        """
        # If tags already exist, return them
        if "tags" in metadata and metadata["tags"]:
            return list(metadata["tags"])

        title = metadata.get("title", "Untitled")
        prompt = f"""Extract 3-5 relevant tags for this content.
Tags should be:
- Single words or short phrases (2-3 words max)
- Lowercase
- Relevant to the main topics
- General enough to group with similar content

Title: {title}

Content:
{content[:1000]}

Respond with JSON array of strings: ["tag1", "tag2", "tag3"]"""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.client.chat_completion(
                messages, response_format={"type": "json_object"}
            )

            # Parse JSON response
            data = json.loads(response)

            # Handle different response formats
            if isinstance(data, list):
                tags = data
            elif isinstance(data, dict) and "tags" in data:
                tags = data["tags"]
            else:
                logger.warning(f"Unexpected tags response format: {data}")
                return []

            # Validate and clean tags
            tags = [str(tag).strip().lower() for tag in tags if tag]
            return tags[:5]  # Max 5 tags

        except Exception as e:
            logger.error(f"Failed to extract tags: {e}")
            return []  # Don't fail completely if tag extraction fails

    def extract_summary(self, content: str, metadata: dict[str, Any], max_length: int = 200) -> str:  # noqa: E501
        """Extract a concise summary of the content.

        Args:
            content: Page content (markdown)
            metadata: Page metadata
            max_length: Maximum summary length

        Returns:
            Summary text

        Raises:
            ExtractionError: If extraction fails
        """
        # If summary already exists, return it
        if "summary" in metadata and metadata["summary"]:
            return str(metadata["summary"])

        title = metadata.get("title", "Untitled")
        prompt = f"""Write a concise summary of this content in 1-2 sentences (max {max_length} characters).
Focus on the key information and purpose.

Title: {title}

Content:
{content[:1500]}

Respond with just the summary text, no JSON."""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.client.chat_completion(messages).strip()

            # Truncate if needed
            if len(response) > max_length:
                response = response[: max_length - 3] + "..."

            return response

        except Exception as e:
            logger.error(f"Failed to extract summary: {e}")
            # Return truncated content as fallback
            fallback = content.strip()[:max_length]
            if len(content) > max_length:
                fallback += "..."
            return fallback

    def extract_metadata(self, filepath: Path) -> dict[str, Any]:
        """Extract all metadata from a page file.

        Args:
            filepath: Path to page file

        Returns:
            Extracted metadata

        Raises:
            ExtractionError: If extraction fails
        """
        try:
            content_text = filepath.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(content_text)

            logger.info(f"Extracting metadata from {filepath.name}")

            # Extract page kind
            kind = self.extract_page_kind(body, metadata)
            metadata["kind"] = kind

            # Extract tags if not present
            if "tags" not in metadata or not metadata["tags"]:
                tags = self.extract_tags(body, metadata)
                if tags:
                    metadata["tags"] = tags

            # Extract summary if not present
            if "summary" not in metadata or not metadata["summary"]:
                summary = self.extract_summary(body, metadata)
                if summary:
                    metadata["summary"] = summary

            return metadata

        except Exception as e:
            raise ExtractionError(f"Failed to extract metadata: {e}") from e

"""Concept extraction from content."""

import json
import logging
from typing import Any

from llm_wiki.models.client import ModelClient

logger = logging.getLogger(__name__)


class ConceptExtractor:
    """Extracts concepts from content using LLM."""

    def __init__(self, client: ModelClient):
        """Initialize concept extractor.

        Args:
            client: LLM client for extraction
        """
        self.client = client

    def extract_concepts(self, content: str, metadata: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract concepts from content.

        Args:
            content: Page content (markdown)
            metadata: Page metadata

        Returns:
            List of concept dictionaries with name, description

        Raises:
            Exception: If extraction fails
        """
        title = metadata.get("title", "Untitled")

        prompt = f"""Extract key concepts from this content. A concept is an idea,
methodology, principle, or topic that's important to understanding the content.

For each concept, provide:
- name: Concept name (2-4 words)
- description: Clear definition (1-2 sentences)

Title: {title}

Content:
{content[:2000]}

Respond with JSON array of objects:
{{"concepts": [{{"name": "...", "description": "..."}}]}}"""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.client.chat_completion(
                messages, response_format={"type": "json_object"}
            )

            data = json.loads(response)

            # Handle different response formats
            if isinstance(data, dict) and "concepts" in data:
                concepts = data["concepts"]
            elif isinstance(data, list):
                concepts = data
            else:
                logger.warning(f"Unexpected concept response format: {data}")
                return []

            # Validate and clean concepts
            validated = []
            for concept in concepts:
                if isinstance(concept, dict) and "name" in concept:
                    validated.append(
                        {
                            "name": str(concept["name"]).strip(),
                            "description": str(concept.get("description", "")).strip(),
                        }
                    )

            return validated[:8]  # Max 8 concepts

        except Exception as e:
            logger.error(f"Failed to extract concepts: {e}")
            return []  # Don't fail completely

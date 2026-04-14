"""Entity extraction from content."""

import json
import logging
from typing import Any

from llm_wiki.models.client import ModelClient

logger = logging.getLogger(__name__)


class EntityExtractor:
    """Extracts entities from content using LLM."""

    def __init__(self, client: ModelClient):
        """Initialize entity extractor.

        Args:
            client: LLM client for extraction
        """
        self.client = client

    def extract_entities(self, content: str, metadata: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract entities from content.

        Args:
            content: Page content (markdown)
            metadata: Page metadata

        Returns:
            List of entity dictionaries with name, type, description

        Raises:
            Exception: If extraction fails
        """
        title = metadata.get("title", "Untitled")

        prompt = f"""Extract key entities from this content. An entity can be:
- PERSON: Individual people mentioned
- ORGANIZATION: Companies, teams, groups
- TECHNOLOGY: Technologies, programming languages, frameworks
- TOOL: Software tools, applications, services
- PRODUCT: Products or services

For each entity, provide:
- name: Entity name
- type: One of (person, organization, technology, tool, product)
- description: Brief description (1 sentence)

Title: {title}

Content:
{content[:2000]}

Respond with JSON array of objects:
{{"entities": [{{"name": "...", "type": "...", "description": "..."}}]}}"""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.client.chat_completion(
                messages, response_format={"type": "json_object"}
            )

            data = json.loads(response)

            # Handle different response formats
            if isinstance(data, dict) and "entities" in data:
                entities = data["entities"]
            elif isinstance(data, list):
                entities = data
            else:
                logger.warning(f"Unexpected entity response format: {data}")
                return []

            # Validate and clean entities
            validated = []
            for entity in entities:
                if isinstance(entity, dict) and "name" in entity and "type" in entity:
                    validated.append(
                        {
                            "name": str(entity["name"]).strip(),
                            "type": str(entity["type"]).lower().strip(),
                            "description": str(entity.get("description", "")).strip(),
                        }
                    )

            return validated[:10]  # Max 10 entities

        except Exception as e:
            logger.error(f"Failed to extract entities: {e}")
            return []  # Don't fail completely

"""Q&A pair extraction from content."""

import json
import logging
from typing import Any

from llm_wiki.models.client import ModelClient

logger = logging.getLogger(__name__)


class QAExtractor:
    """Extracts question/answer pairs from content using an LLM.

    Intended for assistant-session transcripts and any content that contains
    "how do I X?" → "do Y" patterns. Each extracted pair becomes a first-class
    ``qa`` wiki page.
    """

    def __init__(self, client: ModelClient):
        """Initialize the Q&A extractor.

        Args:
            client: LLM client for extraction.
        """
        self.client = client

    def extract_qa_pairs(
        self, content: str, metadata: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Extract Q&A pairs from content.

        Args:
            content: Page content (markdown or transcript).
            metadata: Page metadata.

        Returns:
            List of dicts with ``question``, ``answer``, ``tags``.
            Returns ``[]`` on extraction failure.
        """
        title = metadata.get("title", "Untitled")

        prompt = f"""Extract concrete question/answer pairs from this content.

A good Q&A pair is:
- A specific practical question a user might ask later
- A concrete, actionable answer (not vague generalities)
- Self-contained (readable without the surrounding context)

Skip: rhetorical questions, off-topic chatter, partial answers, conversational
filler. Prefer quality over quantity — return an empty list if no strong pairs.

Title: {title}

Content:
{content[:16000]}

Respond with JSON of this exact shape:
{{"pairs": [{{"question": "...", "answer": "...", "tags": ["tag1", "tag2"]}}]}}"""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.client.chat_completion(
                messages, response_format={"type": "json_object"}
            )

            data = json.loads(response)

            if isinstance(data, dict) and "pairs" in data:
                pairs = data["pairs"]
            elif isinstance(data, list):
                pairs = data
            else:
                logger.warning(f"Unexpected Q&A response format: {data}")
                return []

            validated: list[dict[str, Any]] = []
            for pair in pairs:
                if not isinstance(pair, dict):
                    continue
                question = str(pair.get("question", "")).strip()
                answer = str(pair.get("answer", "")).strip()
                if not question or not answer:
                    continue
                tags_raw = pair.get("tags", [])
                tags = [str(t).strip() for t in tags_raw if str(t).strip()] if isinstance(tags_raw, list) else []
                validated.append(
                    {
                        "question": question,
                        "answer": answer,
                        "tags": tags,
                    }
                )

            return validated[:20]  # Cap per-document Q&A output

        except Exception as e:
            logger.error(f"Failed to extract Q&A pairs: {e}")
            return []

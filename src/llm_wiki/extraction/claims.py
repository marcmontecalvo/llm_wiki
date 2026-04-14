"""Claims extraction from content."""

import json
import logging
from typing import Any

from llm_wiki.models.client import ModelClient
from llm_wiki.models.extraction import ClaimExtraction

logger = logging.getLogger(__name__)


class ClaimsExtractor:
    """Extracts factual claims from content using LLM."""

    def __init__(self, client: ModelClient):
        """Initialize claims extractor.

        Args:
            client: LLM client for extraction
        """
        self.client = client

    def extract_claims(
        self, content: str, metadata: dict[str, Any], page_id: str | None = None
    ) -> list[ClaimExtraction]:
        """Extract factual claims from content.

        Args:
            content: Page content (markdown)
            metadata: Page metadata
            page_id: Optional page identifier for claim tracking

        Returns:
            List of extracted claims with confidence scores and source references

        Raises:
            Exception: If extraction fails
        """
        title = metadata.get("title", "Untitled")
        page_id = page_id or metadata.get("id", "unknown")

        prompt = f"""Extract factual claims from this content. A claim should be:
- A declarative statement that can be verified as true or false
- Atomic (one core fact per claim)
- Not an opinion, question, or instruction
- Clear and unambiguous

For each claim, provide:
- claim: The factual statement (concise, complete)
- confidence: Your confidence this is a factual claim (0.0-1.0)
  - 1.0: Explicit, well-supported statement
  - 0.8-0.9: Clear statement with good context
  - 0.6-0.7: Statement is present but less explicit
  - 0.4-0.5: Ambiguous or requires interpretation
  - Below 0.4: Very uncertain or borderline opinion
- source_reference: Where this came from (e.g., "paragraph 2", "section title", "first sentence")
- temporal_context: When this is/was true (if applicable, e.g., "as of 2024", "during 2020-2023")
- qualifiers: Any conditions or limitations on the claim (e.g., "in the US", "for adults", "typically")

Title: {title}

Content:
{content[:3000]}

Respond with JSON object:
{{"claims": [{{"claim": "...", "confidence": 0.9, "source_reference": "...", "temporal_context": "...", "qualifiers": []}}]}}"""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.client.chat_completion(
                messages, response_format={"type": "json_object"}
            )

            data = json.loads(response)

            # Handle different response formats
            if isinstance(data, dict) and "claims" in data:
                claims_data = data["claims"]
            elif isinstance(data, list):
                claims_data = data
            else:
                logger.warning(f"Unexpected claims response format: {data}")
                return []

            # Validate and convert to ClaimExtraction objects
            validated = []
            for claim_data in claims_data:
                if isinstance(claim_data, dict) and "claim" in claim_data:
                    try:
                        claim_text = str(claim_data["claim"]).strip()
                        source_ref = str(claim_data.get("source_reference", "")).strip()

                        # Skip claims without text or source reference
                        if not claim_text or not source_ref:
                            logger.warning(f"Skipping claim without text or source: {claim_data}")
                            continue

                        claim_obj = ClaimExtraction(
                            claim=claim_text,
                            confidence=float(claim_data.get("confidence", 0.5)),
                            source_reference=source_ref,
                            subject=str(claim_data.get("subject", "")).strip() or None,
                            predicate=str(claim_data.get("predicate", "")).strip() or None,
                            object=str(claim_data.get("object", "")).strip() or None,
                            temporal_context=str(claim_data.get("temporal_context", "")).strip()
                            or None,
                            qualifiers=[
                                str(q).strip() for q in claim_data.get("qualifiers", []) if q
                            ],
                        )
                        validated.append(claim_obj)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Failed to create claim object: {e}")
                        continue

            return validated[:20]  # Max 20 claims per extraction

        except Exception as e:
            logger.error(f"Failed to extract claims: {e}")
            return []  # Don't fail completely

    def extract_claim_types(self, content: str, metadata: dict[str, Any]) -> dict[str, list[str]]:
        """Extract claims organized by type (fact, opinion, instruction).

        Args:
            content: Page content (markdown)
            metadata: Page metadata

        Returns:
            Dictionary with keys "facts", "opinions", "instructions" containing claim texts

        Raises:
            Exception: If extraction fails
        """
        title = metadata.get("title", "Untitled")

        prompt = f"""Categorize statements in this content into three types:

1. FACTS: Verifiable statements about reality (past, present, or future)
   - Examples: "Python was released in 1991", "Water boils at 100°C"

2. OPINIONS: Subjective judgments or beliefs
   - Examples: "This is the best library", "Python is easier than Java"

3. INSTRUCTIONS: Procedural steps or how-to statements
   - Examples: "First, install Python", "Mix the ingredients together"

Only include statements that are clearly one of these types. Skip ambiguous ones.

Title: {title}

Content:
{content[:2500]}

Respond with JSON:
{{"facts": ["fact1", "fact2"], "opinions": ["opinion1"], "instructions": ["step1", "step2"]}}"""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.client.chat_completion(
                messages, response_format={"type": "json_object"}
            )

            data = json.loads(response)

            # Ensure all keys exist
            result: dict[str, list[str]] = {
                "facts": [],
                "opinions": [],
                "instructions": [],
            }

            if isinstance(data, dict):
                for key in result.keys():
                    if key in data and isinstance(data[key], list):
                        # Only include string items, filter out non-strings
                        result[key] = [
                            str(item).strip()
                            for item in data[key]
                            if item and isinstance(item, str)
                        ]

            return result

        except Exception as e:
            logger.error(f"Failed to extract claim types: {e}")
            return {"facts": [], "opinions": [], "instructions": []}

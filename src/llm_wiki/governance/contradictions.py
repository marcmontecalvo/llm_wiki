"""Contradiction detector for detecting conflicting claims across wiki pages."""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llm_wiki.extraction.claims import ClaimsExtractor
from llm_wiki.models.client import ModelClient
from llm_wiki.models.extraction import ClaimExtraction
from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


@dataclass
class Contradiction:
    """Represents a detected contradiction between two claims."""

    claim_1: ClaimExtraction
    page_id_1: str
    claim_2: ClaimExtraction
    page_id_2: str
    contradiction_type: str  # semantic, negation, numerical, temporal, opposition
    confidence: float  # 0.0-1.0: How confident this is a real contradiction
    severity: str  # low, medium, high
    explanation: str  # Why these are contradictory
    suggested_resolution: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert contradiction to dictionary.

        Returns:
            Dictionary representation of the contradiction
        """
        return {
            "claim_1": self.claim_1.claim,
            "page_id_1": self.page_id_1,
            "claim_2": self.claim_2.claim,
            "page_id_2": self.page_id_2,
            "type": self.contradiction_type,
            "confidence": self.confidence,
            "severity": self.severity,
            "explanation": self.explanation,
            "suggested_resolution": self.suggested_resolution,
        }


@dataclass
class ContradictionReport:
    """Report on detected contradictions."""

    total_contradictions: int
    high_confidence: list[Contradiction] = field(default_factory=list)
    medium_confidence: list[Contradiction] = field(default_factory=list)
    low_confidence: list[Contradiction] = field(default_factory=list)
    by_type: dict[str, list[Contradiction]] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class ContradictionDetector:
    """Detects contradictory claims across wiki pages."""

    def __init__(
        self,
        client: ModelClient,
        min_similarity_threshold: float = 0.7,
        min_confidence: float = 0.6,
    ):
        """Initialize contradiction detector.

        Args:
            client: LLM client for semantic analysis
            min_similarity_threshold: Minimum similarity to compare claims (0.0-1.0)
            min_confidence: Minimum confidence to report a contradiction (0.0-1.0)
        """
        self.client = client
        self.claims_extractor = ClaimsExtractor(client)
        self.min_similarity_threshold = min_similarity_threshold
        self.min_confidence = min_confidence

    def detect_contradictions(
        self, all_claims: list[tuple[ClaimExtraction, str]]
    ) -> list[Contradiction]:
        """Detect contradictions in a collection of claims.

        Args:
            all_claims: List of (ClaimExtraction, page_id) tuples

        Returns:
            List of detected contradictions
        """
        contradictions: list[Contradiction] = []

        # Compare each claim pair
        for i in range(len(all_claims)):
            for j in range(i + 1, len(all_claims)):
                claim_1, page_id_1 = all_claims[i]
                claim_2, page_id_2 = all_claims[j]

                # Skip if from same page
                if page_id_1 == page_id_2:
                    continue

                # Check for contradictions using multiple methods
                contradiction = self._check_contradiction_pair(
                    claim_1, page_id_1, claim_2, page_id_2
                )

                if contradiction:
                    contradictions.append(contradiction)

        return contradictions

    def _check_contradiction_pair(
        self, claim_1: ClaimExtraction, page_id_1: str, claim_2: ClaimExtraction, page_id_2: str
    ) -> Contradiction | None:
        """Check if two claims contradict each other.

        Args:
            claim_1: First claim
            page_id_1: Page ID for claim 1
            claim_2: Second claim
            page_id_2: Page ID for claim 2

        Returns:
            Contradiction if detected, None otherwise
        """
        # Try negation detection first (high precision)
        negation_result = self._detect_negation_contradiction(claim_1, claim_2)
        if negation_result:
            return negation_result

        # Try numerical contradictions
        numerical_result = self._detect_numerical_contradiction(claim_1, claim_2)
        if numerical_result:
            return numerical_result

        # Try semantic contradiction (requires similarity check)
        semantic_result = self._detect_semantic_contradiction(claim_1, claim_2)
        if semantic_result:
            return semantic_result

        return None

    def _detect_negation_contradiction(
        self, claim_1: ClaimExtraction, claim_2: ClaimExtraction
    ) -> Contradiction | None:
        """Detect explicit negation contradictions.

        Patterns like:
        - "X is Y" vs "X is not Y"
        - "X has Z" vs "X does not have Z"

        Args:
            claim_1: First claim
            claim_2: Second claim

        Returns:
            Contradiction if detected
        """
        text_1 = claim_1.claim.lower().strip()
        text_2 = claim_2.claim.lower().strip()

        # Check if one is a negation of the other
        negation_patterns = [
            r"\bno(t|w)?\b",
            r"\bdon't\b",
            r"\bdoesn't\b",
            r"\bdidnt'\b",
            r"\bwill not\b",
            r"\bcannot\b",
            r"\bcan't\b",
            r"\bwillnot\b",
        ]

        # Check if texts are similar but one has negation
        has_negation_1 = any(re.search(pattern, text_1) for pattern in negation_patterns)
        has_negation_2 = any(re.search(pattern, text_2) for pattern in negation_patterns)

        if has_negation_1 != has_negation_2:
            # One has negation, other doesn't
            # Remove negation words for comparison
            text_1_without_neg = re.sub(
                "|".join(negation_patterns), "", text_1, flags=re.IGNORECASE
            ).strip()
            text_2_without_neg = re.sub(
                "|".join(negation_patterns), "", text_2, flags=re.IGNORECASE
            ).strip()

            # Check similarity of non-negation parts
            similarity = self._simple_similarity(text_1_without_neg, text_2_without_neg)

            if similarity > 0.75:
                confidence = min(0.95, 0.7 + similarity * 0.25)
                return Contradiction(
                    claim_1=claim_1,
                    page_id_1="",
                    claim_2=claim_2,
                    page_id_2="",
                    contradiction_type="negation",
                    confidence=confidence,
                    severity=self._calculate_severity(confidence),
                    explanation="Direct negation contradiction: One claim affirms while the other denies.",
                    suggested_resolution="Review source credibility and temporal context",
                )

        return None

    def _detect_numerical_contradiction(
        self, claim_1: ClaimExtraction, claim_2: ClaimExtraction
    ) -> Contradiction | None:
        """Detect numerical contradictions.

        Examples:
        - "Released in 2020" vs "Released in 2019"
        - "Has 5 features" vs "Has 10 features"

        Args:
            claim_1: First claim
            claim_2: Second claim

        Returns:
            Contradiction if detected
        """
        text_1 = claim_1.claim
        text_2 = claim_2.claim

        # Extract numbers from both claims
        numbers_1 = self._extract_numbers(text_1)
        numbers_2 = self._extract_numbers(text_2)

        if not numbers_1 or not numbers_2:
            return None

        # Find common number positions (same subject talking about different values)
        # For simplicity, check if claims are similar and have different numbers
        text_1_normalized = re.sub(r"\d+", "NUM", text_1)
        text_2_normalized = re.sub(r"\d+", "NUM", text_2)

        if text_1_normalized == text_2_normalized:
            # Same structure, different numbers
            diffs = [abs(n1 - n2) for n1 in numbers_1 for n2 in numbers_2]
            if diffs and min(diffs) > 0:
                # Extract context around numbers
                confidence = min(0.85, 0.6 + 0.25)  # Numerical contradictions are clear
                return Contradiction(
                    claim_1=claim_1,
                    page_id_1="",
                    claim_2=claim_2,
                    page_id_2="",
                    contradiction_type="numerical",
                    confidence=confidence,
                    severity="high" if min(diffs) > 10 else "medium",
                    explanation=f"Numerical contradiction: Different values for similar statements ({numbers_1[0]} vs {numbers_2[0]})",
                    suggested_resolution="Verify source data and dates of claims",
                )

        return None

    def _detect_semantic_contradiction(
        self, claim_1: ClaimExtraction, claim_2: ClaimExtraction
    ) -> Contradiction | None:
        """Detect semantic contradictions using LLM analysis.

        Args:
            claim_1: First claim
            claim_2: Second claim

        Returns:
            Contradiction if detected
        """
        # Use LLM to analyze semantic contradiction
        prompt = f"""Analyze if these two claims contradict each other:

Claim 1: "{claim_1.claim}"
Claim 2: "{claim_2.claim}"

Consider:
1. Do they directly contradict (opposite statements)?
2. Are they about the same subject/entity?
3. Could both be true in different contexts?
4. Is there temporal context that resolves any apparent contradiction?

Respond with JSON:
{{
  "contradicts": true/false,
  "contradiction_type": "opposition" or "none",
  "confidence": 0.0-1.0,
  "explanation": "brief explanation"
}}"""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.client.chat_completion(
                messages, response_format={"type": "json_object"}
            )

            data = json.loads(response)

            if data.get("contradicts", False) and data.get("confidence", 0) >= self.min_confidence:
                confidence = float(data.get("confidence", 0.5))
                explanation = str(data.get("explanation", "Semantic contradiction detected"))

                return Contradiction(
                    claim_1=claim_1,
                    page_id_1="",
                    claim_2=claim_2,
                    page_id_2="",
                    contradiction_type=data.get("contradiction_type", "opposition"),
                    confidence=confidence,
                    severity=self._calculate_severity(confidence),
                    explanation=explanation,
                    suggested_resolution="Review both sources and determine which is more credible",
                )

        except Exception as e:
            logger.debug(f"LLM semantic analysis failed: {e}")

        return None

    def _extract_numbers(self, text: str) -> list[float]:
        """Extract numbers from text.

        Args:
            text: Text to extract numbers from

        Returns:
            List of numbers found
        """
        pattern = r"\b\d+(?:\.\d+)?\b"
        matches = re.findall(pattern, text)
        return [float(m) for m in matches]

    def _simple_similarity(self, text_1: str, text_2: str) -> float:
        """Calculate simple similarity between two texts (0.0-1.0).

        Uses word overlap metric.

        Args:
            text_1: First text
            text_2: Second text

        Returns:
            Similarity score (0.0-1.0)
        """
        words_1 = set(text_1.lower().split())
        words_2 = set(text_2.lower().split())

        if not words_1 or not words_2:
            return 0.0

        intersection = len(words_1 & words_2)
        union = len(words_1 | words_2)

        return intersection / union if union > 0 else 0.0

    def _calculate_severity(self, confidence: float) -> str:
        """Calculate severity level based on confidence.

        Args:
            confidence: Confidence score (0.0-1.0)

        Returns:
            Severity level: low, medium, or high
        """
        if confidence >= 0.85:
            return "high"
        elif confidence >= 0.7:
            return "medium"
        else:
            return "low"

    def analyze_all_pages(self, wiki_base: Path) -> ContradictionReport:
        """Analyze all pages for contradictions.

        Args:
            wiki_base: Base wiki directory

        Returns:
            ContradictionReport with all detected contradictions
        """
        all_claims: list[tuple[ClaimExtraction, str]] = []

        # Collect all claims from all pages
        domains_dir = wiki_base / "domains"
        if not domains_dir.exists():
            logger.warning(f"Domains directory not found: {domains_dir}")
            return ContradictionReport(total_contradictions=0)

        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            pages_dir = domain_dir / "pages"
            if not pages_dir.exists():
                continue

            for page_file in pages_dir.glob("*.md"):
                try:
                    content = page_file.read_text(encoding="utf-8")
                    metadata, body = parse_frontmatter(content)
                    page_id = metadata.get("id", page_file.stem)

                    # Extract claims from page
                    claims = self.claims_extractor.extract_claims(body, metadata, page_id)
                    for claim in claims:
                        all_claims.append((claim, page_id))

                except Exception as e:
                    logger.error(f"Failed to process {page_file}: {e}")
                    continue

        logger.info(f"Extracted {len(all_claims)} claims from all pages")

        # Detect contradictions
        contradictions = self.detect_contradictions(all_claims)

        # Organize results
        report = ContradictionReport(total_contradictions=len(contradictions))

        for contradiction in contradictions:
            # Set page IDs
            for i, (claim, page_id) in enumerate(all_claims):
                if i == 0 or claim == contradiction.claim_1:
                    contradiction.page_id_1 = page_id
                if i == len(all_claims) - 1 or claim == contradiction.claim_2:
                    contradiction.page_id_2 = page_id

            # Organize by confidence
            if contradiction.confidence >= 0.8:
                report.high_confidence.append(contradiction)
            elif contradiction.confidence >= 0.65:
                report.medium_confidence.append(contradiction)
            else:
                report.low_confidence.append(contradiction)

            # Organize by type
            if contradiction.contradiction_type not in report.by_type:
                report.by_type[contradiction.contradiction_type] = []
            report.by_type[contradiction.contradiction_type].append(contradiction)

        return report

    def generate_report(self, report: ContradictionReport, output_path: Path) -> Path:
        """Generate markdown report of contradictions.

        Args:
            report: ContradictionReport with detected contradictions
            output_path: Path to write report to

        Returns:
            Path to generated report
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            "# Contradiction Detection Report",
            f"Generated: {report.timestamp}",
            "",
            "## Summary",
            f"- Total contradictions detected: {report.total_contradictions}",
            f"- High confidence: {len(report.high_confidence)}",
            f"- Medium confidence: {len(report.medium_confidence)}",
            f"- Low confidence: {len(report.low_confidence)}",
            "",
        ]

        # High confidence section
        if report.high_confidence:
            lines.append("## High Confidence Contradictions")
            lines.append("")
            for contradiction in report.high_confidence:
                lines.extend(self._format_contradiction(contradiction))
                lines.append("")

        # Medium confidence section
        if report.medium_confidence:
            lines.append("## Medium Confidence Contradictions")
            lines.append("")
            for contradiction in report.medium_confidence:
                lines.extend(self._format_contradiction(contradiction))
                lines.append("")

        # By type section
        if report.by_type:
            lines.append("## Contradictions by Type")
            lines.append("")
            for contradiction_type, contradictions in sorted(report.by_type.items()):
                lines.append(f"### {contradiction_type.title()} ({len(contradictions)})")
                lines.append("")
                for contradiction in contradictions[:10]:  # Limit to 10 per type
                    lines.extend(self._format_contradiction(contradiction))
                    lines.append("")

        # Write report
        report_text = "\n".join(lines)
        output_path.write_text(report_text, encoding="utf-8")
        logger.info(f"Generated contradiction report: {output_path}")

        return output_path

    def _format_contradiction(self, contradiction: Contradiction) -> list[str]:
        """Format a contradiction for markdown output.

        Args:
            contradiction: Contradiction to format

        Returns:
            List of markdown lines
        """
        return [
            f"**Claim 1** ({contradiction.page_id_1}): {contradiction.claim_1.claim}",
            "",
            f"**Claim 2** ({contradiction.page_id_2}): {contradiction.claim_2.claim}",
            "",
            f"**Type**: {contradiction.contradiction_type}",
            f"**Confidence**: {contradiction.confidence:.2f}",
            f"**Severity**: {contradiction.severity}",
            f"**Explanation**: {contradiction.explanation}",
            (
                f"**Suggested Resolution**: {contradiction.suggested_resolution}"
                if contradiction.suggested_resolution
                else ""
            ),
        ]

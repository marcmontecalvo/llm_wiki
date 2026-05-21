"""Confidence gating — block low-confidence pages from promotion.

Epic 2.2: Pages with quality scores below a configurable threshold are
flagged and cannot pass wildfire promotion.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from llm_wiki.governance.quality import QualityScorer


@dataclass(frozen=True)
class GateResult:
    """Result of a confidence gate check.

    Attributes:
        page_id: The page that was checked.
        score: Computed quality score.
        passed: ``True`` when score >= threshold.
        reason: Human-readable reason for failure (``None`` when passed).
    """

    page_id: str
    score: float
    passed: bool
    reason: str | None = None


def check_confidence_gate(
    filepath: Path,
    *,
    threshold: float = 0.3,
    backlink_count: int = 0,
    llm_extraction: bool = False,
) -> GateResult:
    """Evaluate a page against the confidence threshold.

    Args:
        filepath: Path to the markdown page to gate.
        threshold: Minimum acceptable quality score (default 0.3).
        backlink_count: Number of backlinking pages (for scoring accuracy).
        llm_extraction: Whether LLM extraction is enabled.

    Returns:
        GateResult with ``passed`` set based on threshold.
    """
    scorer = QualityScorer()
    report = scorer.score_with_backlinks(
        filepath, backlink_count, llm_extraction_enabled=llm_extraction
    )

    if report.score >= threshold:
        return GateResult(
            page_id=report.page_id,
            score=report.score,
            passed=True,
        )

    return GateResult(
        page_id=report.page_id,
        score=report.score,
        passed=False,
        reason=f"confidence {report.score:.2f} below threshold {threshold:.2f}",
    )

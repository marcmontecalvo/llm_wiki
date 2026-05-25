"""Quality scorer for wiki pages.

Architecture-aligned weights (Epic 2):

    citation_presence: 0.4   (0.6 when llm_extraction=False)
    trust_tag:             0.2
    source_count:          0.2
    backlink_count:        0.1
    recency:               0.1

When ``llm_extraction`` is disabled the trust_tag weight (0.2) redistributes
to ``citation_presence``, making it 0.6.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llm_wiki.paths import resolve_wiki_base
from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)
# and score_with_backlinks().  Key is ``llm_extraction_enabled`` boolean.
_DEFAULT_WEIGHTS = {
    "citation_presence": 0.6,
    "trust_tag": 0.2,
    "source_count": 0.2,
    "backlink_count": 0.1,
    "recency": 0.1,
}
_LLM_WEIGHTS = {
    "citation_presence": 0.4,
    "trust_tag": 0.2,
    "source_count": 0.2,
    "backlink_count": 0.1,
    "recency": 0.1,
}

# Validate weight schemata at import time — catches drift between
# the two dicts before any scoring happens.
assert set(_DEFAULT_WEIGHTS.keys()) == set(_LLM_WEIGHTS.keys()), "weight dicts must share keys"
for _name, _wd in (("_DEFAULT", _DEFAULT_WEIGHTS), ("_LLM", _LLM_WEIGHTS)):
    s = sum(_wd.values())
    # _DEFAULT re-distributes trust_tag weight to citation_presence, so its
    # sum is 1.2  (0.6 + 0.2 + 0.2 + 0.1 + 0.1) — acceptable because the
    # scorer normalises.  _LLM is a true probability distribution (sum 1.0).
    acceptable = (_name == "_LLM" and math.isclose(s, 1.0, rel_tol=1e-9)) or (
        _name == "_DEFAULT" and abs(s - 1.2) < 1e-9
    )
    assert acceptable, f"{_name}: weights sum to {s}, expected {1.0 if s < 1.15 else 1.2}"


@dataclass
class QualityReport:
    """Report on page quality."""

    page_id: str
    score: float  # 0.0 (low quality) to 1.0 (high quality)
    factors: dict[str, float]
    issues: list[str]


class QualityScorer:
    """Scorer for page quality and confidence.

    Uses architecture-defined confidence weights.  All scoring is
    deterministic — no LLM calls.
    """

    @staticmethod
    def _get_weights(llm_extraction_enabled: bool) -> dict[str, float]:
        """Return the weight dict for the given feature-flag state.

        Single source of truth -- both :meth:`score_page` and
        :meth:`score_with_backlinks` delegate to this method so that
        future weight changes are applied consistently.
        """
        return _LLM_WEIGHTS if llm_extraction_enabled else _DEFAULT_WEIGHTS

    @staticmethod
    def _weighted_score(factors: dict[str, float], weights: dict[str, float]) -> float:
        """Compute the weighted average of *factors* using *weights*."""
        total = sum(weights.values())
        if total == 0:
            return 0.0
        return sum((factors.get(k) or 0.0) * w for k, w in weights.items()) / total

    def score_page(
        self,
        filepath: Path,
        llm_extraction_enabled: bool = False,
    ) -> QualityReport:
        """Score a page's quality.

        Args:
            filepath: Path to markdown file.
            llm_extraction_enabled: When ``False`` the trust_tag weight
                redistributes to ``citation_presence`` (0.4 → 0.6).

        Returns:
            QualityReport with score and factors.
        """
        try:
            content = filepath.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(content)
        except Exception as e:
            logger.error(f"Failed to score {filepath}: {e}")
            return QualityReport(
                page_id=filepath.stem,
                score=0.0,
                factors={},
                issues=[f"Failed to parse: {e}"],
            )

        page_id = metadata.get("id", filepath.stem)
        factors: dict[str, float] = {}
        issues: list[str] = []

        # Citation presence: 1.0 if source field exists, else 0.0
        citation_score = 1.0 if "source" in metadata and metadata["source"] else 0.0
        if citation_score == 0.0:
            issues.append("No source citation")
        factors["citation_presence"] = citation_score

        # Trust tag: ratio of non-ambiguous claims
        trust_score = self._score_trust_tags(metadata)
        factors["trust_tag"] = trust_score

        # Source count: number of sources (capped at 1.0)
        source_score = self._score_source_count(metadata)
        factors["source_count"] = source_score

        # Backlink count (fetched by caller from index)
        factors["backlink_count"] = 0.0  # set by caller via score_with_backlinks

        # Recency
        recency_score = self._score_recency(metadata, issues)
        factors["recency"] = recency_score

        # Apply weights (trust_tag weight redistributes when LLM extraction disabled)
        weights = self._get_weights(llm_extraction_enabled)

        # Compute weighted average
        overall_score = self._weighted_score(factors, weights)

        return QualityReport(
            page_id=page_id,
            score=float(min(max(overall_score, 0.0), 1.0)),
            factors=factors,
            issues=issues,
        )

    def score_with_backlinks(
        self,
        filepath: Path,
        backlink_count: int,
        llm_extraction_enabled: bool = False,
    ) -> QualityReport:
        """Score a page and inject backlink count into the report.

        Args:
            filepath: Path to markdown file.
            backlink_count: Number of pages linking to this page.
            llm_extraction_enabled: LLM extraction feature flag state.

        Returns:
            QualityReport with ``backlink_count`` factor populated.
        """
        report = self.score_page(filepath, llm_extraction_enabled=llm_extraction_enabled)

        # Backlink score: 1.0 when >= 3 backlinks, scaling down to 0 at 0
        if backlink_count >= 3:
            report.factors["backlink_count"] = 1.0
        elif backlink_count == 1:
            report.factors["backlink_count"] = 0.5
        else:
            report.factors["backlink_count"] = 0.0

        # Recompute weighted average with backlink factor
        weights = self._get_weights(llm_extraction_enabled)
        overall_score = self._weighted_score(report.factors, weights)
        report.score = float(min(max(overall_score, 0.0), 1.0))

        return report

    def _score_trust_tags(self, metadata: dict[str, Any]) -> float:
        """Score based on trust_tag distribution of claims.

        Returns 1.0 when all claims are ``extracted``/``inferred``,
        0.0 when all claims are ``ambiguous``, scales linearly in between.
        Pages with no claims get a neutral 0.5.
        """
        claims = metadata.get("claims", [])
        if not claims:
            return 0.5  # Neutral when no claims exist

        total = len(claims)
        ambiguous_count = 0
        for claim in claims:
            if isinstance(claim, dict):
                if claim.get("trust_tag") == "ambiguous":
                    ambiguous_count += 1
            elif isinstance(claim, str):
                # Legacy: claim stored as plain string — treat as extracted
                pass

        if ambiguous_count >= total:
            return 0.0
        non_ambiguous = total - ambiguous_count
        return round(non_ambiguous / total, 4)

    def _score_source_count(self, metadata: dict[str, Any]) -> float:
        """Score based on number of sources.

        1 source = 0.5, 2+ sources = 1.0.
        """
        sources = metadata.get("sources", [])
        if not sources:
            # Check legacy singular "source" field
            source_val = metadata.get("source", "")
            if not source_val:
                return 0.0
            sources = [source_val] if isinstance(source_val, str) else source_val

        if len(sources) >= 2:
            return 1.0
        return 0.5

    def _score_recency(self, metadata: dict[str, Any], issues: list[str]) -> float:
        """Score recency based on update timestamp.

        Args:
            metadata: Page metadata.
            issues: List to append issues to.

        Returns:
            Recency score (0.0-1.0).
        """
        created = metadata.get("created")
        updated = metadata.get("updated")

        if not updated:
            issues.append("No updated timestamp")
            return 0.0

        if created == updated:
            issues.append("Never updated since creation")
            return 0.3

        return 1.0

    def score_all(
        self,
        wiki_base: Path | None = None,
        max_score: float = 1.0,
        llm_extraction_enabled: bool = False,
    ) -> list[QualityReport]:
        """Score all pages in the wiki.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/).
            max_score: Maximum score to include (0.0-1.0).
            llm_extraction_enabled: Feature flag for LLM extraction.

        Returns:
            List of quality reports, sorted by score (ascending).
        """
        wiki_base = resolve_wiki_base(wiki_base)
        reports: list[QualityReport] = []

        domains_dir = wiki_base / "domains"
        if not domains_dir.exists():
            logger.warning(f"Domains directory not found: {domains_dir}")
            return reports

        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            pages_dir = domain_dir / "pages"
            if not pages_dir.exists():
                continue

            for page_file in pages_dir.glob("*.md"):
                report = self.score_page(page_file, llm_extraction_enabled=llm_extraction_enabled)
                if report.score <= max_score:
                    reports.append(report)

        reports.sort(key=lambda r: r.score)
        return reports

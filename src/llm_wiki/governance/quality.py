"""Quality scorer for wiki pages."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


@dataclass
class QualityReport:
    """Report on page quality."""

    page_id: str
    score: float  # 0.0 (low quality) to 1.0 (high quality)
    factors: dict[str, float]
    issues: list[str]


class QualityScorer:
    """Scorer for page quality and confidence."""

    # Content length thresholds
    MIN_CONTENT_LENGTH = 100
    GOOD_CONTENT_LENGTH = 500

    # Metadata completeness weights
    METADATA_WEIGHTS = {
        "summary": 0.15,
        "tags": 0.1,
        "kind": 0.1,
        "source": 0.15,
    }

    def score_page(self, filepath: Path) -> QualityReport:
        """Score a page's quality.

        Args:
            filepath: Path to markdown file

        Returns:
            QualityReport with score and factors
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
        factors = {}
        issues: list[str] = []

        # Metadata completeness
        metadata_score = self._score_metadata(metadata, issues)
        factors["metadata"] = metadata_score

        # Content length and structure
        content_score = self._score_content(body, issues)
        factors["content"] = content_score

        # Citations present
        citation_score = 1.0 if "source" in metadata else 0.0
        if citation_score == 0.0:
            issues.append("No source citation")
        factors["citations"] = citation_score

        # Recency (has updated timestamp different from created)
        recency_score = self._score_recency(metadata, issues)
        factors["recency"] = recency_score

        # Calculate weighted overall score
        overall_score = (
            factors["metadata"] * 0.3
            + factors["content"] * 0.4
            + factors["citations"] * 0.2
            + factors["recency"] * 0.1
        )

        return QualityReport(
            page_id=page_id,
            score=min(max(overall_score, 0.0), 1.0),
            factors=factors,
            issues=issues,
        )

    def _score_metadata(self, metadata: dict[str, Any], issues: list[str]) -> float:
        """Score metadata completeness.

        Args:
            metadata: Page metadata
            issues: List to append issues to

        Returns:
            Metadata score (0.0-1.0)
        """
        score = 0.5  # Base score for having basic required fields

        for field, weight in self.METADATA_WEIGHTS.items():
            if field in metadata and metadata[field]:
                # Check if it's not empty
                value = metadata[field]
                if isinstance(value, str) and value.strip():
                    score += weight
                elif isinstance(value, list) and value:
                    score += weight
                else:
                    issues.append(f"Empty {field}")
            else:
                issues.append(f"Missing {field}")

        return min(score, 1.0)

    def _score_content(self, content: str, issues: list[str]) -> float:
        """Score content length and structure.

        Args:
            content: Page content (body)
            issues: List to append issues to

        Returns:
            Content score (0.0-1.0)
        """
        length = len(content.strip())

        # Length scoring
        if length < self.MIN_CONTENT_LENGTH:
            issues.append(f"Very short content ({length} chars)")
            length_score = 0.2
        elif length < self.GOOD_CONTENT_LENGTH:
            length_score = 0.5 + (length / self.GOOD_CONTENT_LENGTH) * 0.3
        else:
            length_score = 0.8

        # Structure scoring
        has_headings = "#" in content
        has_lists = "-" in content or "*" in content or "1." in content

        structure_score = 0.0
        if has_headings:
            structure_score += 0.1
        else:
            issues.append("No headings")

        if has_lists:
            structure_score += 0.1
        else:
            issues.append("No lists or bullet points")

        return min(length_score + structure_score, 1.0)

    def _score_recency(self, metadata: dict[str, Any], issues: list[str]) -> float:
        """Score recency based on update timestamp.

        Args:
            metadata: Page metadata
            issues: List to append issues to

        Returns:
            Recency score (0.0-1.0)
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
        self, wiki_base: Path | None = None, max_score: float = 1.0
    ) -> list[QualityReport]:
        """Score all pages in the wiki.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)
            max_score: Maximum score to include (0.0-1.0)

        Returns:
            List of quality reports, sorted by score (ascending - lowest quality first)
        """
        wiki_base = wiki_base or Path("wiki_system")
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
                report = self.score_page(page_file)
                if report.score <= max_score:
                    reports.append(report)

        # Sort by quality score (ascending - lowest first)
        reports.sort(key=lambda r: r.score)

        return reports

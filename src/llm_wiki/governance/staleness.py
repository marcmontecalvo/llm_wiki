"""Staleness detector for wiki pages."""

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


@dataclass
class StalenessReport:
    """Report on page staleness."""

    page_id: str
    score: float  # 0.0 (fresh) to 1.0 (very stale)
    reasons: list[str]
    age_days: int | None = None
    never_updated: bool = False
    has_time_sensitive_content: bool = False


class StalenessDetector:
    """Detector for stale or outdated wiki pages."""

    # Age thresholds (in days)
    FRESH_THRESHOLD = 30
    STALE_THRESHOLD = 90
    VERY_STALE_THRESHOLD = 180

    # Time-sensitive keywords that suggest content may become outdated
    TIME_SENSITIVE_KEYWORDS = [
        r"\b20\d{2}\b",  # Years (2020, 2024, etc.)
        r"\bcurrent\b",
        r"\blatest\b",
        r"\bupcoming\b",
        r"\brecent\b",
        r"\bnew\b",
        r"\btoday\b",
        r"\bnow\b",
        r"\bversion\s+\d+",  # Version numbers
        r"\bv\d+\.\d+",  # Version numbers (v1.0, etc.)
    ]

    def analyze_page(self, filepath: Path) -> StalenessReport:
        """Analyze a page for staleness.

        Args:
            filepath: Path to markdown file

        Returns:
            StalenessReport with staleness score and reasons
        """
        try:
            content = filepath.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(content)
        except Exception as e:
            logger.error(f"Failed to analyze {filepath}: {e}")
            return StalenessReport(
                page_id=filepath.stem,
                score=0.0,
                reasons=[f"Failed to parse: {e}"],
            )

        page_id = metadata.get("id", filepath.stem)
        reasons = []
        score_components = []

        # Check age
        age_days = None
        created = metadata.get("created")
        updated = metadata.get("updated")

        if created:
            age_days = self._calculate_age(created)
            if age_days is not None:
                if age_days > self.VERY_STALE_THRESHOLD:
                    reasons.append(f"Very old ({age_days} days)")
                    score_components.append(0.6)
                elif age_days > self.STALE_THRESHOLD:
                    reasons.append(f"Old ({age_days} days)")
                    score_components.append(0.4)
                elif age_days > self.FRESH_THRESHOLD:
                    reasons.append(f"Moderately old ({age_days} days)")
                    score_components.append(0.2)

        # Check if never updated
        never_updated = False
        if created and updated and created == updated:
            never_updated = True
            reasons.append("Never updated since creation")
            score_components.append(0.3)

        # Check for time-sensitive content
        has_time_sensitive = self._has_time_sensitive_content(body)
        if has_time_sensitive:
            reasons.append("Contains time-sensitive content")
            score_components.append(0.3)

        # Check for URLs (external references that may become outdated)
        url_count = len(re.findall(r"https?://", body))
        if url_count > 5:
            reasons.append(f"Many external references ({url_count} URLs)")
            score_components.append(0.2)

        # Calculate final score
        if score_components:
            score = min(sum(score_components), 1.0)
        else:
            score = 0.0
            reasons.append("Fresh (recently created/updated)")

        return StalenessReport(
            page_id=page_id,
            score=score,
            reasons=reasons,
            age_days=age_days,
            never_updated=never_updated,
            has_time_sensitive_content=has_time_sensitive,
        )

    def _calculate_age(self, timestamp: str | datetime) -> int | None:
        """Calculate age in days from timestamp.

        Args:
            timestamp: ISO timestamp string or datetime

        Returns:
            Age in days, or None if invalid
        """
        try:
            if isinstance(timestamp, str):
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            else:
                dt = timestamp

            now = datetime.now(UTC)
            age = (now - dt.replace(tzinfo=UTC)).days
            return max(age, 0)
        except Exception as e:
            logger.warning(f"Failed to parse timestamp {timestamp}: {e}")
            return None

    def _has_time_sensitive_content(self, content: str) -> bool:
        """Check if content has time-sensitive keywords.

        Args:
            content: Page content

        Returns:
            True if time-sensitive content found
        """
        content_lower = content.lower()

        for pattern in self.TIME_SENSITIVE_KEYWORDS:
            if re.search(pattern, content_lower, re.IGNORECASE):
                return True

        return False

    def analyze_all(
        self, wiki_base: Path | None = None, min_score: float = 0.0
    ) -> list[StalenessReport]:
        """Analyze all pages in the wiki.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)
            min_score: Minimum staleness score to include (0.0-1.0)

        Returns:
            List of staleness reports, sorted by score (descending)
        """
        wiki_base = wiki_base or Path("wiki_system")
        reports: list[StalenessReport] = []

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
                report = self.analyze_page(page_file)
                if report.score >= min_score:
                    reports.append(report)

        # Sort by staleness score (descending)
        reports.sort(key=lambda r: r.score, reverse=True)

        return reports

"""Duplicate entity detection for wiki pages."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


# Common abbreviation mappings for alias matching
KNOWN_ABBREVIATIONS = {
    "aws": "amazon web services",
    "gcp": "google cloud platform",
    "npm": "node package manager",
    "api": "application programming interface",
    "sdk": "software development kit",
    "llm": "large language model",
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "ci/cd": "continuous integration continuous deployment",
    "orm": "object relational mapping",
}


@dataclass
class DuplicateCandidate:
    """Represents a potential duplicate page pair."""

    page_1: str  # First page ID
    page_2: str  # Second page ID
    duplicate_score: float  # Overall duplicate score (0.0-1.0)
    reasons: list[str] = field(default_factory=list)  # Why flagged as duplicate
    suggested_action: str = "keep_both"  # "merge", "keep_both", or "redirect"
    primary_page: str | None = None  # Which to keep if merging

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "page_1": self.page_1,
            "page_2": self.page_2,
            "duplicate_score": self.duplicate_score,
            "reasons": self.reasons,
            "suggested_action": self.suggested_action,
            "primary_page": self.primary_page,
        }


@dataclass
class DuplicateReport:
    """Report of detected duplicate entities."""

    total_candidates: int
    high_confidence: list[DuplicateCandidate] = field(default_factory=list)
    medium_confidence: list[DuplicateCandidate] = field(default_factory=list)
    low_confidence: list[DuplicateCandidate] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class DuplicateDetector:
    """Detects duplicate entity pages in the wiki."""

    def __init__(self, min_score: float = 0.3, wiki_base: Path | None = None):
        """Initialize duplicate detector.

        Args:
            min_score: Minimum duplicate score to include in report (0.0-1.0)
            wiki_base: Base wiki directory (optional, used by analyze_all_pages)
        """
        self.min_score = min_score
        self.wiki_base = wiki_base

    def analyze_all_pages(self, wiki_base: Path | None = None) -> DuplicateReport:
        """Analyze all pages for duplicates.

        Args:
            wiki_base: Base wiki directory. Uses instance wiki_base if not provided.

        Returns:
            DuplicateReport with detected duplicates organized by confidence
        """
        if wiki_base is None:
            wiki_base = self.wiki_base
        if wiki_base is None:
            raise ValueError("wiki_base must be provided")

        # Collect all pages
        pages_metadata: dict[str, tuple[dict, str]] = {}  # page_id -> (metadata, body)

        domains_dir = wiki_base / "domains"
        if not domains_dir.exists():
            logger.warning(f"Domains directory not found: {domains_dir}")
            return DuplicateReport(total_candidates=0)

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

                    # Skip source pages (don't detect source doc duplicates)
                    if metadata.get("kind") == "source":
                        continue

                    pages_metadata[page_id] = (metadata, body)

                except Exception as e:
                    logger.error(f"Failed to process {page_file}: {e}")
                    continue

        logger.info(f"Loaded {len(pages_metadata)} pages for duplicate detection")

        # Compare all pairs (once per pair)
        all_candidates: list[DuplicateCandidate] = []
        page_ids = sorted(pages_metadata.keys())

        for i in range(len(page_ids)):
            for j in range(i + 1, len(page_ids)):
                page_id_1 = page_ids[i]
                page_id_2 = page_ids[j]

                metadata_1, body_1 = pages_metadata[page_id_1]
                metadata_2, body_2 = pages_metadata[page_id_2]

                score, reasons = self._score_pair(metadata_1, metadata_2, body_1, body_2)

                if score >= self.min_score:
                    # Determine suggested action and primary page
                    if score > 0.8:
                        suggested_action = "merge"
                    elif score >= 0.5:
                        suggested_action = "redirect"
                    else:
                        suggested_action = "keep_both"

                    # Determine primary page (more backlinks, longer content, or alphabetically first)
                    backlinks_1 = len(metadata_1.get("backlinks", []))
                    backlinks_2 = len(metadata_2.get("backlinks", []))

                    if backlinks_1 > backlinks_2:
                        primary_page = page_id_1
                    elif backlinks_2 > backlinks_1:
                        primary_page = page_id_2
                    else:
                        # If equal, use longer content
                        if len(body_1) >= len(body_2):
                            primary_page = page_id_1
                        else:
                            primary_page = page_id_2

                    candidate = DuplicateCandidate(
                        page_1=page_id_1,
                        page_2=page_id_2,
                        duplicate_score=score,
                        reasons=reasons,
                        suggested_action=suggested_action,
                        primary_page=primary_page,
                    )
                    all_candidates.append(candidate)

        # Organize by confidence
        report = DuplicateReport(total_candidates=len(all_candidates))

        for candidate in all_candidates:
            if candidate.duplicate_score > 0.8:
                report.high_confidence.append(candidate)
            elif candidate.duplicate_score >= 0.5:
                report.medium_confidence.append(candidate)
            else:
                report.low_confidence.append(candidate)

        return report

    def _score_pair(
        self,
        meta1: dict,
        meta2: dict,
        content1: str,
        content2: str,
    ) -> tuple[float, list[str]]:
        """Score a pair of pages for duplicate likelihood.

        Args:
            meta1: Metadata dict for page 1
            meta2: Metadata dict for page 2
            content1: Body content for page 1
            content2: Body content for page 2

        Returns:
            Tuple of (duplicate_score, list of reasons)
        """
        reasons: list[str] = []

        # A. Exact name match (normalized)
        name_similarity = 0.0
        norm_name_1 = self._normalize_name(meta1.get("title") or meta1.get("name", ""))
        norm_name_2 = self._normalize_name(meta2.get("title") or meta2.get("name", ""))

        if norm_name_1 and norm_name_2 and norm_name_1 == norm_name_2:
            name_similarity = 1.0
            reasons.append(f"Exact name match: '{norm_name_1}'")

        # B. Alias/synonym matching
        alias_match = 0.0
        name_1 = meta1.get("title") or meta1.get("name", "")
        name_2 = meta2.get("title") or meta2.get("name", "")
        aliases_1 = meta1.get("aliases", []) or []
        aliases_2 = meta2.get("aliases", []) or []

        # Check if name_2 is in aliases_1 or vice versa
        if self._check_alias_match(name_2, aliases_1):
            alias_match = 1.0
            reasons.append(f"'{name_2}' is in aliases of page 1")
        elif self._check_alias_match(name_1, aliases_2):
            alias_match = 1.0
            reasons.append(f"'{name_1}' is in aliases of page 2")

        # C. Metadata overlap (same source URL or GitHub repo)
        metadata_overlap = 0.0
        source_url_1 = meta1.get("source_url", "")
        source_url_2 = meta2.get("source_url", "")
        github_url_1 = meta1.get("github_url", "")
        github_url_2 = meta2.get("github_url", "")

        if source_url_1 and source_url_1 == source_url_2:
            metadata_overlap = 1.0
            reasons.append(f"Same source URL: {source_url_1}")
        elif github_url_1 and github_url_1 == github_url_2:
            metadata_overlap = 1.0
            reasons.append(f"Same GitHub URL: {github_url_1}")

        # D. Tag overlap (>= 3 common tags)
        tag_overlap = 0.0
        tags_1 = set(meta1.get("tags", []) or [])
        tags_2 = set(meta2.get("tags", []) or [])

        if tags_1 and tags_2:
            common_tags = tags_1 & tags_2
            if len(common_tags) >= 3:
                tag_overlap = 1.0
                reasons.append(
                    f"{len(common_tags)} common tags: {', '.join(sorted(common_tags)[:5])}"
                )

        # Calculate final score using formula:
        # duplicate_score = name_similarity * 0.4 + alias_match * 0.3 + metadata_overlap * 0.2 + tag_overlap * 0.1
        score = (
            name_similarity * 0.4 + alias_match * 0.3 + metadata_overlap * 0.2 + tag_overlap * 0.1
        )

        return score, reasons

    def _normalize_name(self, name: str) -> str:
        """Normalize a name for comparison.

        Converts to lowercase, strips whitespace, removes common stop words.

        Args:
            name: Name to normalize

        Returns:
            Normalized name
        """
        if not name:
            return ""

        # Lowercase and strip whitespace
        normalized = name.lower().strip()

        # Remove common stop words
        stop_words = {"the", "a", "an"}
        words = normalized.split()
        words = [w for w in words if w not in stop_words]

        normalized = " ".join(words)

        return normalized

    def _check_alias_match(self, name: str, aliases: list[str]) -> bool:
        """Check if a name matches any alias.

        Args:
            name: Name to check
            aliases: List of aliases

        Returns:
            True if name matches an alias (case-insensitive)
        """
        if not name or not aliases:
            return False

        norm_name = self._normalize_name(name)
        for alias in aliases:
            norm_alias = self._normalize_name(alias)
            if norm_name == norm_alias:
                return True

        return False

    def generate_report(self, report: DuplicateReport, output_path: Path) -> Path:
        """Generate markdown report of duplicates.

        Args:
            report: DuplicateReport with detected duplicates
            output_path: Path to write report to

        Returns:
            Path to generated report
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            "# Duplicate Entity Detection Report",
            f"Generated: {report.timestamp}",
            "",
            "## Summary",
            f"- Total duplicate candidates: {report.total_candidates}",
            f"- High confidence: {len(report.high_confidence)}",
            f"- Medium confidence: {len(report.medium_confidence)}",
            f"- Low confidence: {len(report.low_confidence)}",
            "",
        ]

        # High confidence section
        if report.high_confidence:
            lines.append("## High Confidence Duplicates (score > 0.8)")
            lines.append("")
            for candidate in sorted(
                report.high_confidence, key=lambda c: c.duplicate_score, reverse=True
            ):
                lines.extend(self._format_candidate(candidate))
                lines.append("")

        # Medium confidence section
        if report.medium_confidence:
            lines.append("## Medium Confidence Duplicates (score 0.5-0.8)")
            lines.append("")
            for candidate in sorted(
                report.medium_confidence, key=lambda c: c.duplicate_score, reverse=True
            ):
                lines.extend(self._format_candidate(candidate))
                lines.append("")

        # Low confidence section
        if report.low_confidence:
            lines.append("## Low Confidence Duplicates (score 0.3-0.5)")
            lines.append("")
            for candidate in sorted(
                report.low_confidence, key=lambda c: c.duplicate_score, reverse=True
            ):
                lines.extend(self._format_candidate(candidate))
                lines.append("")

        # Write report
        report_text = "\n".join(lines)
        output_path.write_text(report_text, encoding="utf-8")
        logger.info(f"Generated duplicate report: {output_path}")

        return output_path

    def _format_candidate(self, candidate: DuplicateCandidate) -> list[str]:
        """Format a duplicate candidate for markdown output.

        Args:
            candidate: Candidate to format

        Returns:
            List of markdown lines
        """
        return [
            f"### {candidate.page_1} ↔ {candidate.page_2}",
            "",
            f"**Score**: {candidate.duplicate_score:.3f}",
            f"**Suggested Action**: {candidate.suggested_action}",
            f"**Primary Page**: {candidate.primary_page}",
            "",
            "**Reasons**:",
            *[f"- {reason}" for reason in candidate.reasons],
        ]

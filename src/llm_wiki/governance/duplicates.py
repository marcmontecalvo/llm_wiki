"""Duplicate entity detection for wiki pages."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llm_wiki.utils.frontmatter import parse_frontmatter
from llm_wiki.review.queue import ReviewQueue
from llm_wiki.review.models import ReviewItem, ReviewType, ReviewPriority, ReviewStatus

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

    def __init__(
        self,
        min_score: float = 0.3,
        wiki_base: Path | None = None,
        check_domains: list[str] | None = None,
        exclude_kinds: list[str] | None = None,
    ):
        """Initialize duplicate detector.

        Args:
            min_score: Minimum duplicate score to include in report (0.0-1.0)
            wiki_base: Base wiki directory (optional, used by analyze_all_pages)
            check_domains: List of domain names to check (None = all domains)
            exclude_kinds: List of page kinds to exclude (e.g., ["source"])
        """
        self.min_score = min_score
        self.wiki_base = wiki_base
        self.check_domains = check_domains
        self.exclude_kinds = exclude_kinds or ["source"]

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
            wiki_base = Path("wiki_system")

        # Collect all pages
        pages_metadata: dict[str, tuple[dict, str]] = {}  # page_id -> (metadata, body)

        domains_dir = wiki_base / "domains"
        if not domains_dir.exists():
            logger.warning(f"Domains directory not found: {domains_dir}")
            return DuplicateReport(total_candidates=0)

        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            # Filter by domain name if check_domains is specified
            if self.check_domains and domain_dir.name not in self.check_domains:
                logger.debug(f"Skipping domain {domain_dir.name} (not in check_domains)")
                continue

            pages_dir = domain_dir / "pages"
            if not pages_dir.exists():
                continue

            for page_file in pages_dir.glob("*.md"):
                try:
                    content = page_file.read_text(encoding="utf-8")
                    metadata, body = parse_frontmatter(content)
                    page_id = metadata.get("id", page_file.stem)

                    # Skip pages with excluded kinds
                    page_kind = metadata.get("kind")
                    if page_kind in self.exclude_kinds:
                        logger.debug(f"Skipping {page_id} (kind={page_kind} in exclude_kinds)")
                        continue

                    if page_id in pages_metadata:
                        logger.warning(f"Duplicate page ID '{page_id}' in {page_file}; skipping")
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
                    raw_backlinks_1 = metadata_1.get("backlinks", [])
                    raw_backlinks_2 = metadata_2.get("backlinks", [])
                    backlinks_1 = len(raw_backlinks_1) if isinstance(raw_backlinks_1, list) else 0
                    backlinks_2 = len(raw_backlinks_2) if isinstance(raw_backlinks_2, list) else 0

                    if backlinks_1 > backlinks_2:
                        primary_page = page_id_1
                    elif backlinks_2 > backlinks_1:
                        primary_page = page_id_2
                    elif len(body_1) > len(body_2):
                        primary_page = page_id_1
                    elif len(body_2) > len(body_1):
                        primary_page = page_id_2
                    else:
                        # Deterministic alphabetical fallback
                        primary_page = page_id_1 if page_id_1 <= page_id_2 else page_id_2

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

        # Check if name_2 is in aliases_1 or vice versa (including KNOWN_ABBREVIATIONS)
        if self._check_alias_match(name_2, aliases_1):
            alias_match = 1.0
            # Check page aliases first, then known abbreviations
            if self._check_alias_match(name_2, aliases_1):
                reasons.append(f"'{name_2}' is in aliases of page 1")
            elif self._is_known_abbreviation(name_2):
                reasons.append(f"Known abbreviation: '{name_2}'")
        elif self._check_alias_match(name_1, aliases_2):
            alias_match = 1.0
            if self._check_alias_match(name_1, aliases_2):
                reasons.append(f"'{name_1}' is in aliases of page 2")
            elif self._is_known_abbreviation(name_1):
                reasons.append(f"Known abbreviation: '{name_1}'")

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

        # E. Content similarity (word-based Jaccard similarity)
        content_similarity = 0.0
        if content1 and content2:
            words1 = set(content1.lower().split())
            words2 = set(content2.lower().split())
            # Remove very short words (likely stop words or noise)
            words1 = {w for w in words1 if len(w) > 2}
            words2 = {w for w in words2 if len(w) > 2}
            if words1 and words2:
                intersection = words1 & words2
                union = words1 | words2
                if union:
                    jaccard = len(intersection) / len(union)
                    # Only count as significant if at least 30% similar
                    if jaccard >= 0.3:
                        content_similarity = jaccard
                        reasons.append(f"Content similarity: {jaccard:.2f}")

        # Calculate final score using formula:
        # duplicate_score = name_similarity * 0.4 + alias_match * 0.3 + metadata_overlap * 0.2 + tag_overlap * 0.1 + content_similarity * 0.1
        score = (
            name_similarity * 0.4
            + alias_match * 0.3
            + metadata_overlap * 0.2
            + tag_overlap * 0.1
            + content_similarity * 0.1
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
        """Check if a name matches any alias or known abbreviation.

        Args:
            name: Name to check
            aliases: List of aliases

        Returns:
            True if name matches an alias (case-insensitive) or known abbreviation
        """
        if not name:
            return False

        norm_name = self._normalize_name(name)

        # Check against page aliases
        if aliases:
            for alias in aliases:
                norm_alias = self._normalize_name(alias)
                if norm_name == norm_alias:
                    return True

        # Check against known abbreviations
        # Check if name is a known abbreviation key (e.g., "aws")
        if norm_name in KNOWN_ABBREVIATIONS:
            return True

        # Check if name is an expansion of a known abbreviation
        for abbrev, expansion in KNOWN_ABBREVIATIONS.items():
            if norm_name == self._normalize_name(expansion):
                return True

        return False

    def _is_known_abbreviation(self, name: str) -> bool:
        """Check if a name is a known abbreviation or expansion.

        Args:
            name: Name to check

        Returns:
            True if name is a known abbreviation or its expansion
        """
        if not name:
            return False

        norm_name = self._normalize_name(name)
        # Check if it's an abbreviation key (e.g., "aws")
        if norm_name in KNOWN_ABBREVIATIONS:
            return True
        # Check if it's an expansion of a known abbreviation
        for abbrev, expansion in KNOWN_ABBREVIATIONS.items():
            if norm_name == self._normalize_name(expansion):
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

    def add_to_review_queue(
        self,
        report: DuplicateReport,
        queue_dir: Path | None = None,
        min_score: float = 0.5,
    ) -> list[ReviewItem]:
        """Add high-confidence duplicate candidates to the review queue.

        Args:
            report: DuplicateReport with detected duplicates
            queue_dir: Optional queue directory (defaults to wiki_system/review_queue)
            min_score: Minimum score to add to queue (default 0.5)

        Returns:
            List of created ReviewItems
        """
        if queue_dir is None:
            # Use wiki_base if available, otherwise default
            if self.wiki_base:
                queue_dir = self.wiki_base / "review_queue"
            else:
                queue_dir = Path("wiki_system") / "review_queue"

        queue = ReviewQueue(queue_dir=queue_dir)
        created_items: list[ReviewItem] = []

        # Get candidates above threshold
        all_candidates = (
            report.high_confidence
            + report.medium_confidence
            + report.low_confidence
        )
        candidates_to_add = [c for c in all_candidates if c.duplicate_score >= min_score]

        for candidate in candidates_to_add:
            # Check if this duplicate pair is already in the queue
            existing_items = queue.list_pending(item_type=ReviewType.DUPLICATE)
            existing_pair_ids = {
                (item.metadata.get("page_1"), item.metadata.get("page_2"))
                for item in existing_items
            }

            pair_key = (candidate.page_1, candidate.page_2)
            reverse_pair = (candidate.page_2, candidate.page_1)

            if pair_key in existing_pair_ids or reverse_pair in existing_pair_ids:
                logger.debug(f"Skipping duplicate {pair_key} - already in queue")
                continue

            # Determine priority based on score
            if candidate.duplicate_score > 0.8:
                priority = ReviewPriority.HIGH
            elif candidate.duplicate_score >= 0.6:
                priority = ReviewPriority.MEDIUM
            else:
                priority = ReviewPriority.LOW

            # Create review item
            item_id = f"dup_{candidate.page_1}_{candidate.page_2}"
            review_item = ReviewItem(
                id=item_id,
                type=ReviewType.DUPLICATE,
                target_id=candidate.primary_page or candidate.page_1,
                reason=f"Duplicate detected: '{candidate.page_1}' ↔ '{candidate.page_2}' (score: {candidate.duplicate_score:.2f})",
                priority=priority,
                metadata={
                    "page_1": candidate.page_1,
                    "page_2": candidate.page_2,
                    "duplicate_score": candidate.duplicate_score,
                    "suggested_action": candidate.suggested_action,
                    "reasons": candidate.reasons,
                },
            )

            try:
                queue.create(review_item)
                created_items.append(review_item)
                logger.info(f"Added duplicate to review queue: {item_id}")
            except ValueError as e:
                # Item might already exist
                logger.debug(f"Could not add review item: {e}")
                continue

        logger.info(f"Added {len(created_items)} duplicates to review queue")
        return created_items

    def merge_duplicate(
        self,
        page_1: str,
        page_2: str,
        primary_page: str,
        wiki_base: Path | None = None,
    ) -> dict[str, Any]:
        """Merge a duplicate page into the primary page.

        The merge workflow:
        1. Load primary and secondary page content
        2. Merge content (secondary content appended as section)
        3. Update all backlinks that point to secondary page
        4. Create redirect from secondary to primary
        5. Update or delete secondary page

        Args:
            page_1: First page ID
            page_2: Second page ID
            primary_page: The page to keep (must be one of page_1 or page_2)
            wiki_base: Base wiki directory (defaults to self.wiki_base)

        Returns:
            Dictionary with merge results
        """
        if wiki_base is None:
            wiki_base = self.wiki_base or Path("wiki_system")

        if primary_page not in (page_1, page_2):
            raise ValueError(f"Primary page must be one of {page_1} or {page_2}")

        secondary_page = page_2 if primary_page == page_1 else page_1

        logger.info(f"Merging {secondary_page} into {primary_page}")

        # Find the pages
        primary_path, secondary_path = self._find_page_files(
            primary_page, secondary_page, wiki_base
        )

        if not primary_path:
            raise FileNotFoundError(f"Primary page not found: {primary_page}")
        if not secondary_path:
            raise FileNotFoundError(f"Secondary page not found: {secondary_page}")

        # Read page contents
        primary_content = primary_path.read_text(encoding="utf-8")
        secondary_content = secondary_path.read_text(encoding="utf-8")

        primary_meta, primary_body = parse_frontmatter(primary_content)
        secondary_meta, secondary_body = parse_frontmatter(secondary_content)

        # Get secondary page title for the merged section
        secondary_title = secondary_meta.get("title", secondary_page)

        # Create merged content - append secondary content as a section
        merged_body = self._merge_content(
            primary_body, secondary_body, secondary_title
        )

        # Update primary page metadata - merge tags, aliases
        merged_meta = self._merge_metadata(primary_meta, secondary_meta)

        # Write updated primary page
        merged_frontmatter = self._create_frontmatter(merged_meta, merged_body)
        primary_path.write_text(merged_frontmatter, encoding="utf-8")

        # Update backlinks from other pages
        updated_backlinks = self._update_backlinks(
            secondary_page, primary_page, wiki_base
        )

        # Create redirect file for secondary page
        redirect_path = secondary_path.with_suffix(".md.redirect")
        redirect_content = f"""---
redirect_to: {primary_page}
redirect_from: {secondary_page}
---

# Redirect

This page has been merged into [[{primary_page}]].
"""
        redirect_path.write_text(redirect_content, encoding="utf-8")

        # Delete or archive secondary page
        archived_path = secondary_path.with_suffix(".md.archived")
        secondary_path.rename(archived_path)

        logger.info(f"Merge complete: {secondary_page} -> {primary_page}")

        return {
            "status": "success",
            "primary_page": primary_page,
            "secondary_page": secondary_page,
            "backlinks_updated": updated_backlinks,
            "redirect_created": str(redirect_path),
            "archived_path": str(archived_path),
        }

    def auto_merge_duplicates(
        self,
        report: DuplicateReport,
        wiki_base: Path | None = None,
        threshold: float = 0.9,
    ) -> list[dict[str, Any]]:
        """Automatically merge duplicates above the threshold.

        This method iterates through high-confidence duplicate candidates
        and merges them automatically if they exceed the threshold.
        For safety, this only auto-merges when score > threshold.

        Args:
            report: DuplicateReport with detected duplicates
            wiki_base: Base wiki directory (defaults to self.wiki_base)
            threshold: Minimum score for automatic merging (default 0.9)

        Returns:
            List of merge results for each successful merge
        """
        if wiki_base is None:
            wiki_base = self.wiki_base or Path("wiki_system")

        results = []

        # Only auto-merge high-confidence duplicates
        for candidate in report.high_confidence:
            if candidate.duplicate_score >= threshold:
                primary = candidate.primary_page or candidate.page_1

                try:
                    result = self.merge_duplicate(
                        candidate.page_1,
                        candidate.page_2,
                        primary,
                        wiki_base,
                    )
                    result["candidate_score"] = candidate.duplicate_score
                    results.append(result)
                    logger.info(
                        f"Auto-merged {candidate.page_2} -> {primary} "
                        f"(score: {candidate.duplicate_score:.3f})"
                    )
                except Exception as e:
                    logger.error(
                        f"Auto-merge failed for {candidate.page_1} ↔ {candidate.page_2}: {e}"
                    )

        return results

    def _find_page_files(
        self, page_1: str, page_2: str, wiki_base: Path
    ) -> tuple[Path | None, Path | None]:
        """Find the file paths for two page IDs.

        Args:
            page_1: First page ID
            page_2: Second page ID
            wiki_base: Base wiki directory

        Returns:
            Tuple of (path_for_page_1, path_for_page_2)
        """
        path_1 = None
        path_2 = None

        domains_dir = wiki_base / "domains"
        if not domains_dir.exists():
            return None, None

        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            pages_dir = domain_dir / "pages"
            if not pages_dir.exists():
                continue

            for page_file in pages_dir.glob("*.md"):
                try:
                    content = page_file.read_text(encoding="utf-8")
                    metadata, _ = parse_frontmatter(content)
                    page_id = metadata.get("id", page_file.stem)

                    if page_id == page_1 and path_1 is None:
                        path_1 = page_file
                    elif page_id == page_2 and path_2 is None:
                        path_2 = page_file

                    if path_1 and path_2:
                        break
                except Exception:
                    continue

        return path_1, path_2

    def _merge_content(
        self, primary_body: str, secondary_body: str, secondary_title: str
    ) -> str:
        """Merge secondary content into primary.

        Args:
            primary_body: Content of primary page
            secondary_body: Content of secondary page
            secondary_title: Title of secondary page for section header

        Returns:
            Merged content
        """
        merged = primary_body.strip()

        # Add a section with the secondary content
        if secondary_body.strip():
            merged += f"\n\n## Content from {secondary_title}\n\n"
            merged += secondary_body.strip()

        return merged

    def _merge_metadata(
        self, primary_meta: dict, secondary_meta: dict
    ) -> dict:
        """Merge metadata from secondary into primary.

        Args:
            primary_meta: Metadata of primary page
            secondary_meta: Metadata of secondary page

        Returns:
            Merged metadata
        """
        merged = primary_meta.copy()

        # Merge tags (unique, preserve primary order then add new secondary tags)
        primary_tags = set(primary_meta.get("tags", []) or [])
        secondary_tags = set(secondary_meta.get("tags", []) or [])
        merged_tags = list(primary_tags | secondary_tags)
        if merged_tags:
            merged["tags"] = merged_tags

        # Merge aliases (unique)
        primary_aliases = set(primary_meta.get("aliases", []) or [])
        secondary_aliases = set(secondary_meta.get("aliases", []) or [])
        merged_aliases = list(primary_aliases | secondary_aliases)
        if merged_aliases:
            merged["aliases"] = merged_aliases

        # Merge external IDs (prefer primary, add any new secondary IDs)
        if "external_ids" in secondary_meta:
            if "external_ids" not in merged:
                merged["external_ids"] = {}
            merged["external_ids"].update(secondary_meta.get("external_ids", {}))

        # Track merge in metadata
        merged["merged_from"] = secondary_meta.get("id", "unknown")
        merged["merged_at"] = datetime.now(UTC).isoformat()

        return merged

    def _create_frontmatter(self, metadata: dict, body: str) -> str:
        """Create frontmatter and body for a page.

        Args:
            metadata: Page metadata dict
            body: Page body content

        Returns:
            Complete markdown with frontmatter
        """
        import yaml

        # Build frontmatter - put id first
        fm_parts = []
        if "id" in metadata:
            fm_parts.append(f"id: {yaml.safe_dump(metadata['id']).strip()}")

        for key, value in metadata.items():
            if key == "id":
                continue
            if value is None:
                continue
            if isinstance(value, list):
                if value:
                    fm_parts.append(f"{key}:")
                    for item in value:
                        fm_parts.append(f"  - {item}")
                else:
                    fm_parts.append(f"{key}: []")
            elif isinstance(value, dict):
                fm_parts.append(f"{key}:")
                for k, v in value.items():
                    fm_parts.append(f"  {k}: {v}")
            else:
                fm_parts.append(f"{key}: {yaml.safe_dump(value).strip()}")

        frontmatter = "---\n" + "\n".join(fm_parts) + "\n---\n"
        return frontmatter + body

    def _update_backlinks(
        self, from_page: str, to_page: str, wiki_base: Path
    ) -> int:
        """Update all backlinks that point to from_page to instead point to to_page.

        Args:
            from_page: Page ID to redirect from
            to_page: Page ID to redirect to
            wiki_base: Base wiki directory

        Returns:
            Number of backlinks updated
        """
        updated_count = 0

        domains_dir = wiki_base / "domains"
        if not domains_dir.exists():
            return 0

        # Find all pages that link to from_page
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

                    # Check if body contains a link to from_page
                    link_patterns = [
                        f"[[{from_page}]]",
                        f"[[{from_page}|",
                        f"({from_page})",
                    ]

                    has_link = any(pattern in body for pattern in link_patterns)

                    if has_link:
                        # Replace links
                        updated_body = body
                        updated_body = updated_body.replace(
                            f"[[{from_page}]]", f"[[{to_page}]]"
                        )
                        # Handle wiki links with alias: [[page|display]]
                        import re

                        updated_body = re.sub(
                            rf"\[\[{re.escape(from_page)}\|",
                            f"[[{to_page}|",
                            updated_body,
                        )

                        if updated_body != body:
                            # Update backlinks in metadata
                            backlinks = metadata.get("backlinks", []) or []
                            if from_page in backlinks:
                                backlinks.remove(from_page)
                                if to_page not in backlinks:
                                    backlinks.append(to_page)
                                metadata["backlinks"] = backlinks

                            # Write updated content
                            updated_content = self._create_frontmatter(
                                metadata, updated_body
                            )
                            page_file.write_text(updated_content, encoding="utf-8")
                            updated_count += 1

                except Exception as e:
                    logger.debug(f"Could not update {page_file}: {e}")
                    continue

        return updated_count

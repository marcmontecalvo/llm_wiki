"""Governance daemon job."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llm_wiki.governance.contradictions import ContradictionDetector
from llm_wiki.governance.duplicates import DuplicateDetector
from llm_wiki.governance.linter import LintSeverity, MetadataLinter
from llm_wiki.governance.quality import QualityScorer
from llm_wiki.governance.staleness import StalenessDetector
from llm_wiki.index.backlinks import BacklinkIndex
from llm_wiki.index.metadata import MetadataIndex
from llm_wiki.models.client import ModelClient
from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


class GovernanceJob:
    """Daemon job for running governance checks."""

    def __init__(self, wiki_base: Path | None = None, client: ModelClient | None = None):
        """Initialize governance job.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)
            client: Optional LLM client for contradiction detection
        """
        self.wiki_base = wiki_base or Path("wiki_system")
        self.client = client

        # Initialize checkers
        index_dir = self.wiki_base / "index"
        metadata_index = MetadataIndex(index_dir=index_dir)
        metadata_index.load()

        self.linter = MetadataLinter(metadata_index=metadata_index)
        self.staleness_detector = StalenessDetector()
        self.quality_scorer = QualityScorer()
        self.duplicate_detector = DuplicateDetector(min_score=0.3, wiki_base=wiki_base)
        self.contradiction_detector = ContradictionDetector(client) if client else None
        self.backlink_index = BacklinkIndex(index_dir=index_dir)

    def execute(self) -> dict[str, Any]:
        """Execute governance checks.

        Returns:
            Dictionary with governance statistics
        """
        logger.info("Starting governance check")

        try:
            # Run all checkers
            lint_issues = self.linter.lint_all(self.wiki_base)
            staleness_reports = self.staleness_detector.analyze_all(self.wiki_base, min_score=0.3)
            quality_reports = self.quality_scorer.score_all(self.wiki_base, max_score=0.6)

            # Count issues by severity
            lint_errors = sum(1 for i in lint_issues if i.severity == LintSeverity.ERROR)
            lint_warnings = sum(1 for i in lint_issues if i.severity == LintSeverity.WARNING)

            # Count pages scanned and collect all page IDs
            domains_dir = self.wiki_base / "domains"
            pages_scanned = 0
            all_page_ids: set[str] = set()
            if domains_dir.exists():
                for domain_dir in domains_dir.iterdir():
                    if domain_dir.is_dir():
                        pages_dir = domain_dir / "pages"
                        if pages_dir.exists():
                            for pf in pages_dir.glob("*.md"):
                                try:
                                    content = pf.read_text(encoding="utf-8")
                                    metadata, _ = parse_frontmatter(content)
                                    page_id = metadata.get("id", pf.stem)
                                    all_page_ids.add(page_id)
                                    pages_scanned += 1
                                except Exception as e:
                                    logger.error(f"Failed to read {pf}: {e}")

            # Run link health checks
            logger.info("Running link health checks")
            self.backlink_index.load()
            broken_link_stats = self.backlink_index.update_broken_links(all_page_ids)
            orphan_pages = self.backlink_index.get_orphan_pages(all_page_ids)

            # Persist updated broken links to disk
            self.backlink_index.save()

            # Collect pages with broken links for the report
            pages_with_broken: dict[str, list[str]] = {}
            for pid, pdata in self.backlink_index.index.items():
                if pdata["broken_links"]:
                    pages_with_broken[pid] = sorted(pdata["broken_links"])

            # Run duplicate detection
            logger.info("Running duplicate detection")
            duplicate_report = self.duplicate_detector.analyze_all_pages(self.wiki_base)
            logger.info(f"Found {duplicate_report.total_candidates} potential duplicate pairs")

            # Run contradiction detection if client is available
            contradiction_report = None
            if self.contradiction_detector:
                logger.info("Running contradiction detection")
                contradiction_report = self.contradiction_detector.analyze_all_pages(self.wiki_base)
                logger.info(
                    f"Found {contradiction_report.total_contradictions} potential contradictions"
                )

            # Generate report
            report_path = self._generate_report(
                lint_issues,
                staleness_reports,
                quality_reports,
                duplicate_report,
                contradiction_report,
                pages_scanned=pages_scanned,
                pages_with_broken=pages_with_broken,
                orphan_pages=orphan_pages,
            )

            stats = {
                "status": "success",
                "total_pages": pages_scanned,
                "lint_issues": len(lint_issues),
                "lint_errors": lint_errors,
                "lint_warnings": lint_warnings,
                "stale_pages": len(staleness_reports),
                "low_quality_pages": len(quality_reports),
                "duplicates": duplicate_report.total_candidates,
                "contradictions": contradiction_report.total_contradictions
                if contradiction_report
                else 0,
                "broken_links": broken_link_stats["total_broken_links"],
                "orphan_pages": len(orphan_pages),
                "report_path": str(report_path),
            }

            logger.info(f"Governance check complete: {stats}")

            return stats

        except Exception as e:
            logger.error(f"Governance check failed: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "lint_issues": 0,
                "stale_pages": 0,
                "low_quality_pages": 0,
                "duplicates": 0,
                "contradictions": 0,
            }

    def _generate_report(
        self,
        lint_issues: list,
        staleness_reports: list,
        quality_reports: list,
        duplicate_report: Any,
        contradiction_report: Any = None,
        pages_scanned: int = 0,
        pages_with_broken: dict[str, list[str]] | None = None,
        orphan_pages: list[str] | None = None,
    ) -> Path:
        """Generate governance report markdown.

        Args:
            lint_issues: List of lint issues
            staleness_reports: List of staleness reports
            quality_reports: List of quality reports
            duplicate_report: Duplicate detection report
            contradiction_report: Optional contradiction report

        Returns:
            Path to generated report
        """
        reports_dir = self.wiki_base / "reports"
        reports_dir.mkdir(exist_ok=True)

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        report_path = reports_dir / f"governance_{timestamp}.md"

        pages_with_broken = pages_with_broken or {}
        orphan_pages = orphan_pages or []
        total_broken = sum(len(v) for v in pages_with_broken.values())

        # Generate report content
        lines = [
            "# Wiki Governance Report",
            f"Generated: {datetime.now(UTC).isoformat()}",
            "",
            "## Summary",
            f"- Pages scanned: {pages_scanned}",
            f"- Lint issues: {len(lint_issues)}",
            f"- Stale pages: {len(staleness_reports)}",
            f"- Low-quality pages: {len(quality_reports)}",
            f"- Duplicate candidates: {duplicate_report.total_candidates}",
            f"- Broken links: {total_broken} across {len(pages_with_broken)} pages",
            f"- Orphan pages (no backlinks): {len(orphan_pages)}",
        ]

        if contradiction_report:
            lines.append(f"- Contradictions detected: {contradiction_report.total_contradictions}")

        lines.extend(["", ""])

        # Lint issues section
        if lint_issues:
            lines.append("## Lint Issues")
            lines.append("")

            # Group by page
            by_page: dict[str, list] = {}
            for issue in lint_issues:
                if issue.page_id not in by_page:
                    by_page[issue.page_id] = []
                by_page[issue.page_id].append(issue)

            for page_id in sorted(by_page.keys()):
                lines.append(f"### {page_id}")
                for issue in by_page[page_id]:
                    severity = issue.severity.value.upper()
                    field_info = f" ({issue.field})" if issue.field else ""
                    lines.append(f"- **{severity}**: {issue.message}{field_info}")
                lines.append("")

        # Stale pages section
        if staleness_reports:
            lines.append("## Stale Pages")
            lines.append("")
            lines.append("Pages sorted by staleness score (highest first):")
            lines.append("")

            for report in staleness_reports[:20]:  # Top 20
                age_info = f" ({report.age_days} days old)" if report.age_days else ""
                lines.append(f"### {report.page_id} (score: {report.score:.2f}{age_info})")
                for reason in report.reasons:
                    lines.append(f"- {reason}")
                lines.append("")

        # Low-quality pages section
        if quality_reports:
            lines.append("## Low-Quality Pages")
            lines.append("")
            lines.append("Pages sorted by quality score (lowest first):")
            lines.append("")

            for report in quality_reports[:20]:  # Bottom 20
                lines.append(f"### {report.page_id} (score: {report.score:.2f})")
                for issue in report.issues:
                    lines.append(f"- {issue}")
                lines.append("")

        # Broken links section
        if pages_with_broken:
            lines.append("## Broken Links")
            lines.append("")
            lines.append("Pages with links to non-existent targets:")
            lines.append("")
            for pid in sorted(pages_with_broken.keys()):
                lines.append(f"### {pid}")
                for broken in pages_with_broken[pid]:
                    lines.append(f"- !! [[{broken}]] (target not found)")
                lines.append("")

        # Orphan pages section
        if orphan_pages:
            lines.append("## Orphan Pages")
            lines.append("")
            lines.append("Pages with no backlinks (nothing links here):")
            lines.append("")
            # Configurable limit with default of 50
            limit = 50
            for pid in orphan_pages[:limit]:
                lines.append(f"- {pid}")
            if len(orphan_pages) > limit:
                lines.append(f"- ... and {len(orphan_pages) - limit} more (use --limit flag to see more)")
            lines.append("")

        # Duplicates section
        if duplicate_report.total_candidates > 0:
            lines.append("## Detected Duplicates")
            lines.append("")

            if duplicate_report.high_confidence:
                lines.append("### High Confidence Duplicates (score > 0.8)")
                lines.append("")
                for candidate in duplicate_report.high_confidence[:10]:
                    lines.append(
                        f"- **{candidate.page_1}** ↔ **{candidate.page_2}** "
                        f"(score: {candidate.duplicate_score:.3f})"
                    )
                    lines.append(f"  - Action: {candidate.suggested_action}")
                    lines.append(f"  - Primary: {candidate.primary_page}")
                    for reason in candidate.reasons[:2]:
                        lines.append(f"  - {reason}")
                lines.append("")

            if duplicate_report.medium_confidence:
                lines.append("### Medium Confidence Duplicates (score 0.5-0.8)")
                lines.append("")
                for candidate in duplicate_report.medium_confidence[:5]:
                    lines.append(
                        f"- **{candidate.page_1}** ↔ **{candidate.page_2}** "
                        f"(score: {candidate.duplicate_score:.3f})"
                    )
                lines.append("")

        # Contradictions section
        if contradiction_report and contradiction_report.total_contradictions > 0:
            lines.append("## Detected Contradictions")
            lines.append("")

            if contradiction_report.high_confidence:
                lines.append("### High Confidence Contradictions")
                lines.append("")
                for contradiction in contradiction_report.high_confidence[:10]:
                    lines.append(
                        f"- **{contradiction.page_id_1}** vs **{contradiction.page_id_2}** "
                        f"(confidence: {contradiction.confidence:.2f})"
                    )
                    lines.append(f"  - Type: {contradiction.contradiction_type}")
                    lines.append(f"  - Claim 1: {contradiction.claim_1.claim[:80]}...")
                    lines.append(f"  - Claim 2: {contradiction.claim_2.claim[:80]}...")
                lines.append("")

            if contradiction_report.medium_confidence:
                lines.append("### Medium Confidence Contradictions")
                lines.append("")
                for contradiction in contradiction_report.medium_confidence[:5]:
                    lines.append(
                        f"- **{contradiction.page_id_1}** vs **{contradiction.page_id_2}** "
                        f"(confidence: {contradiction.confidence:.2f})"
                    )
                lines.append("")

        # Write report
        report_path.write_text("\n".join(lines), encoding="utf-8")

        logger.info(f"Generated governance report: {report_path}")

        return report_path


def run_governance_check(
    wiki_base: Path | None = None, client: ModelClient | None = None
) -> dict[str, Any]:
    """Run governance check job.

    This function is called by the daemon scheduler.

    Args:
        wiki_base: Base wiki directory (defaults to wiki_system/)
        client: Optional LLM client for contradiction detection

    Returns:
        Dictionary with governance statistics
    """
    job = GovernanceJob(wiki_base=wiki_base, client=client)
    return job.execute()

"""Governance daemon job."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llm_wiki.governance.contradictions import ContradictionDetector
from llm_wiki.governance.linter import LintSeverity, MetadataLinter
from llm_wiki.governance.quality import QualityScorer
from llm_wiki.governance.staleness import StalenessDetector
from llm_wiki.index.metadata import MetadataIndex
from llm_wiki.models.client import ModelClient

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
        self.contradiction_detector = ContradictionDetector(client) if client else None

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
                lint_issues, staleness_reports, quality_reports, contradiction_report
            )

            stats = {
                "status": "success",
                "lint_issues": len(lint_issues),
                "lint_errors": lint_errors,
                "lint_warnings": lint_warnings,
                "stale_pages": len(staleness_reports),
                "low_quality_pages": len(quality_reports),
                "contradictions": contradiction_report.total_contradictions
                if contradiction_report
                else 0,
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
                "contradictions": 0,
            }

    def _generate_report(
        self,
        lint_issues: list,
        staleness_reports: list,
        quality_reports: list,
        contradiction_report: Any = None,
    ) -> Path:
        """Generate governance report markdown.

        Args:
            lint_issues: List of lint issues
            staleness_reports: List of staleness reports
            quality_reports: List of quality reports
            contradiction_report: Optional contradiction report

        Returns:
            Path to generated report
        """
        reports_dir = self.wiki_base / "reports"
        reports_dir.mkdir(exist_ok=True)

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        report_path = reports_dir / f"governance_{timestamp}.md"

        # Count pages scanned
        domains_dir = self.wiki_base / "domains"
        pages_scanned = 0
        if domains_dir.exists():
            for domain_dir in domains_dir.iterdir():
                if domain_dir.is_dir():
                    pages_dir = domain_dir / "pages"
                    if pages_dir.exists():
                        pages_scanned += len(list(pages_dir.glob("*.md")))

        # Generate report content
        lines = [
            "# Governance Report",
            f"Generated: {datetime.now(UTC).isoformat()}",
            "",
            "## Summary",
            f"- Pages scanned: {pages_scanned}",
            f"- Lint issues: {len(lint_issues)}",
            f"- Stale pages: {len(staleness_reports)}",
            f"- Low-quality pages: {len(quality_reports)}",
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

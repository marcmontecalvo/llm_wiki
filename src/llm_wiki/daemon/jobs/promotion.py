"""Promotion daemon job."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llm_wiki.promotion.config import PromotionConfig
from llm_wiki.promotion.engine import PromotionEngine

logger = logging.getLogger(__name__)


class PromotionJob:
    """Daemon job for running page promotion checks."""

    def __init__(
        self,
        wiki_base: Path | None = None,
        config: PromotionConfig | None = None,
    ):
        """Initialize promotion job.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)
            config: Promotion configuration
        """
        self.wiki_base = wiki_base or Path("wiki_system")
        self.config = config or PromotionConfig()

        # Initialize promotion engine
        self.engine = PromotionEngine(config=self.config, wiki_base=self.wiki_base)

    def execute(self) -> dict[str, Any]:
        """Execute promotion check job.

        Returns:
            Dictionary with promotion statistics
        """
        logger.info("Starting promotion check")

        try:
            # Process all candidates
            report = self.engine.process_candidates()

            # Generate report file
            report_path = self._save_report(report)

            stats = {
                "status": "success",
                "total_candidates": report.total_candidates,
                "auto_promoted": report.auto_promoted,
                "suggested_for_review": report.suggested_for_review,
                "report_path": str(report_path),
            }

            logger.info(f"Promotion check complete: {stats}")

            return stats

        except Exception as e:
            logger.error(f"Promotion check failed: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "total_candidates": 0,
                "auto_promoted": 0,
                "suggested_for_review": 0,
            }

    def _save_report(self, report) -> Path:
        """Save promotion report to disk.

        Args:
            report: PromotionReport instance

        Returns:
            Path to saved report
        """
        reports_dir = self.wiki_base / "reports"
        reports_dir.mkdir(exist_ok=True)

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        report_path = reports_dir / f"promotion_{timestamp}.json"

        # Save as JSON
        with report_path.open("w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)

        logger.info(f"Saved promotion report: {report_path}")

        return report_path


def run_promotion_check(
    wiki_base: Path | None = None,
    config: PromotionConfig | None = None,
) -> dict[str, Any]:
    """Run promotion check job.

    This function is called by the daemon scheduler.

    Args:
        wiki_base: Base wiki directory (defaults to wiki_system/)
        config: Promotion configuration

    Returns:
        Dictionary with promotion statistics
    """
    job = PromotionJob(wiki_base=wiki_base, config=config)
    return job.execute()

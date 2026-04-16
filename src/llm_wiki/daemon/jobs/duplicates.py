"""Duplicate detection daemon job."""

import logging
from pathlib import Path
from typing import Any

from llm_wiki.governance.duplicates import DuplicateDetector
from llm_wiki.models.config import DuplicatesConfig

logger = logging.getLogger(__name__)


class DuplicateDetectionJob:
    """Daemon job for running duplicate entity detection."""

    def __init__(
        self,
        wiki_base: Path | None = None,
        config: DuplicatesConfig | None = None,
    ):
        """Initialize duplicate detection job.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)
            config: Duplicate detection configuration
        """
        self.wiki_base = wiki_base or Path("wiki_system")
        self.config = config or DuplicatesConfig()

    def execute(self) -> dict[str, Any]:
        """Execute duplicate detection.

        Returns:
            Dictionary with duplicate detection statistics
        """
        logger.info("Starting duplicate detection job")

        try:
            # Initialize detector with config
            detector = DuplicateDetector(
                min_score=self.config.min_score_to_flag,
                wiki_base=self.wiki_base,
                check_domains=self.config.check_domains,
                exclude_kinds=self.config.exclude_kinds,
            )

            # Run detection
            report = detector.analyze_all_pages(self.wiki_base)

            logger.info(
                f"Duplicate detection complete: {report.total_candidates} candidates found"
            )

            # Optionally add to review queue if enabled
            added_to_queue = 0
            if self.config.require_review:
                added_to_queue = len(
                    detector.add_to_review_queue(report, min_score=0.5)
                )
                logger.info(f"Added {added_to_queue} duplicates to review queue")

            # Optionally auto-merge if enabled
            auto_merged = 0
            if self.config.auto_merge_threshold and self.config.auto_merge_threshold > 0:
                results = detector.auto_merge_duplicates(
                    report,
                    wiki_base=self.wiki_base,
                    threshold=self.config.auto_merge_threshold,
                )
                auto_merged = len(results)
                logger.info(f"Auto-merged {auto_merged} duplicate pairs")

            stats = {
                "status": "success",
                "total_candidates": report.total_candidates,
                "high_confidence": len(report.high_confidence),
                "medium_confidence": len(report.medium_confidence),
                "low_confidence": len(report.low_confidence),
                "added_to_queue": added_to_queue,
                "auto_merged": auto_merged,
            }

            logger.info(f"Duplicate detection job complete: {stats}")
            return stats

        except Exception as e:
            logger.error(f"Duplicate detection job failed: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "total_candidates": 0,
                "high_confidence": 0,
                "medium_confidence": 0,
                "low_confidence": 0,
                "added_to_queue": 0,
                "auto_merged": 0,
            }


def run_duplicate_detection(
    wiki_base: Path | None = None,
    config: DuplicatesConfig | None = None,
) -> dict[str, Any]:
    """Run duplicate detection job.

    This function is called by the daemon scheduler.

    Args:
        wiki_base: Base wiki directory (defaults to wiki_system/)
        config: Duplicate detection configuration

    Returns:
        Dictionary with duplicate detection statistics
    """
    job = DuplicateDetectionJob(wiki_base=wiki_base, config=config)
    return job.execute()
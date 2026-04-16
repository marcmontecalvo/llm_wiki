"""Review queue population daemon job."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llm_wiki.review.models import ReviewItem, ReviewPriority, ReviewStatus, ReviewType
from llm_wiki.review.queue import ReviewQueue

logger = logging.getLogger(__name__)


class ReviewQueueJob:
    """Daemon job for populating the review queue."""

    def __init__(self, wiki_base: Path | None = None):
        """Initialize review queue job.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)
        """
        self.wiki_base = wiki_base or Path("wiki_system")
        self.review_queue = ReviewQueue(queue_dir=self.wiki_base / "review_queue")

        # Configuration thresholds
        self.min_page_quality = 0.4
        self.min_claim_confidence = 0.5

    def execute(self) -> dict[str, Any]:
        """Execute review queue population job.

        Returns:
            Dictionary with population statistics
        """
        logger.info("Starting review queue population")

        added_count = 0

        try:
            # Scan for pages with low quality
            pages_added = self._scan_low_quality_pages()
            added_count += pages_added

            # Scan for claims with low confidence
            claims_added = self._scan_low_confidence_claims()
            added_count += claims_added

            # Scan for sourceless claims
            sourceless_added = self._scan_sourceless_claims()
            added_count += sourceless_added

            # Scan for duplicates (placeholder - requires entity resolution)
            duplicates_added = self._scan_duplicates()
            added_count += duplicates_added

            # Clean up old items
            cleanup_count = self.review_queue.cleanup_old_items(30)

            stats = {
                "status": "success",
                "items_added": added_count,
                "pages_scanned": pages_added,
                "claims_scanned": claims_added,
                "sourceless_scanned": sourceless_added,
                "duplicates_scanned": duplicates_added,
                "cleanup_count": cleanup_count,
            }

            logger.info(f"Review queue population complete: {stats}")
            return stats

        except Exception as e:
            logger.error(f"Review queue population failed: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "items_added": 0,
            }

    def _scan_low_quality_pages(self) -> int:
        """Scan for pages with quality below threshold.

        Returns:
            Number of items added to queue
        """
        added = 0
        domains_dir = self.wiki_base / "domains"

        if not domains_dir.exists():
            return 0

        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            pages_dir = domain_dir / "pages"
            if not pages_dir.exists():
                continue

            for page_file in pages_dir.glob("*.md"):
                try:
                    content = json.loads(page_file.read_text())
                    quality = content.get("quality_score", 1.0)

                    if quality < self.min_page_quality:
                        page_id = page_file.stem
                        existing = self.review_queue.get(f"page-{page_id}")
                        if existing is None:
                            item = ReviewItem(
                                id=f"page-{page_id}",
                                type=ReviewType.PAGE,
                                target_id=page_id,
                                reason=f"Page quality score {quality:.2f} below threshold {self.min_page_quality}",
                                priority=ReviewPriority.MEDIUM
                                if quality >= 0.2
                                else ReviewPriority.HIGH,
                                created_at=datetime.now(UTC),
                                metadata={
                                    "domain": domain_dir.name,
                                    "quality_score": quality,
                                    "title": content.get("title", page_id),
                                },
                            )
                            self.review_queue.create(item)
                            added += 1
                            logger.info(f"Added review item for low quality page: {page_id}")

                except (json.JSONDecodeError, KeyError):
                    continue

        return added

    def _scan_low_confidence_claims(self) -> int:
        """Scan for claims with confidence below threshold.

        Returns:
            Number of items added to queue
        """
        # This would require loading the claims graph
        # For now, return 0 as this needs claims storage implementation
        return 0

    def _scan_sourceless_claims(self) -> int:
        """Scan for claims without sources.

        Returns:
            Number of items added to queue
        """
        # This would require loading the claims graph
        # For now, return 0 as this needs claims storage implementation
        return 0

    def _scan_duplicates(self) -> int:
        """Scan for duplicate entities.

        Returns:
            Number of items added to queue
        """
        # This would require entity resolution service
        # For now, return 0 as this needs entity resolution implementation
        return 0

    def add_manual_review_item(
        self,
        target_id: str,
        item_type: ReviewType,
        reason: str,
        priority: ReviewPriority = ReviewPriority.MEDIUM,
        metadata: dict | None = None,
    ) -> ReviewItem:
        """Manually add a review item to the queue.

        Args:
            target_id: ID of the thing to review
            item_type: Type of review item
            reason: Reason for review
            priority: Priority level
            metadata: Additional metadata

        Returns:
            Created ReviewItem
        """
        item_id = f"{item_type.value}-{target_id}"
        item = ReviewItem(
            id=item_id,
            type=item_type,
            target_id=target_id,
            reason=reason,
            priority=priority,
            created_at=datetime.now(UTC),
            metadata=metadata or {},
        )
        return self.review_queue.create(item)

    def add_for_review(
        self,
        target_id: str,
        item_type: str,
        reason: str,
        priority: str = "medium",
    ) -> ReviewItem:
        """Add an item to the review queue.

        Args:
            target_id: ID of thing being reviewed
            item_type: Type of item as string
            reason: Reason for review
            priority: Priority as string

        Returns:
            Created ReviewItem
        """
        return self.add_manual_review_item(
            target_id=target_id,
            item_type=ReviewType(item_type),
            reason=reason,
            priority=ReviewPriority(priority),
        )


def run_review_queue_job(wiki_base: Path | None = None) -> dict[str, Any]:
    """Run the review queue population job.

    Args:
        wiki_base: Base wiki directory

    Returns:
        Job execution statistics
    """
    job = ReviewQueueJob(wiki_base=wiki_base)
    return job.execute()
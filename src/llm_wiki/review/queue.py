"""Review queue storage and management."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from llm_wiki.review.models import ReviewItem, ReviewPriority, ReviewStatus, ReviewType


class ReviewQueue:
    """Manages the review queue storage and operations."""

    def __init__(self, queue_dir: Path | None = None):
        """Initialize the review queue.

        Args:
            queue_dir: Base directory for queue storage
                      (default: wiki_system/review_queue)
        """
        if queue_dir is None:
            queue_dir = Path("wiki_system") / "review_queue"

        self.queue_dir = Path(queue_dir)
        self.pending_dir = self.queue_dir / "pending"
        self.approved_dir = self.queue_dir / "approved"
        self.rejected_dir = self.queue_dir / "rejected"
        self.deferred_dir = self.queue_dir / "deferred"

        # Create directories if they don't exist
        for directory in [
            self.pending_dir,
            self.approved_dir,
            self.rejected_dir,
            self.deferred_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

    def _get_status_dir(self, status: ReviewStatus) -> Path:
        """Get directory for a given status.

        Args:
            status: Review status

        Returns:
            Path to status directory
        """
        status_dirs = {
            ReviewStatus.PENDING: self.pending_dir,
            ReviewStatus.APPROVED: self.approved_dir,
            ReviewStatus.REJECTED: self.rejected_dir,
            ReviewStatus.DEFERRED: self.deferred_dir,
        }
        return status_dirs[status]

    def _item_path(self, item_id: str, status: ReviewStatus) -> Path:
        """Get file path for a review item.

        Args:
            item_id: Review item ID
            status: Review status

        Returns:
            Path to item file
        """
        return self._get_status_dir(status) / f"{item_id}.json"

    def create(self, item: ReviewItem) -> ReviewItem:
        """Create a new review item.

        Args:
            item: ReviewItem to create

        Returns:
            Created ReviewItem

        Raises:
            ValueError: If item already exists
        """
        path = self._item_path(item.id, item.status)
        if path.exists():
            raise ValueError(f"Review item already exists: {item.id}")

        path.write_text(json.dumps(item.to_dict(), indent=2, default=str))
        return item

    def get(self, item_id: str, status: ReviewStatus | None = None) -> ReviewItem | None:
        """Get a review item by ID.

        Args:
            item_id: Review item ID
            status: Optional status to search in (searches all if not provided)

        Returns:
            ReviewItem if found, None otherwise
        """
        if status is not None:
            path = self._item_path(item_id, status)
            if path.exists():
                data = json.loads(path.read_text())
                return ReviewItem.from_dict(data)
            return None

        # Search all status directories
        for search_status in ReviewStatus:
            path = self._item_path(item_id, search_status)
            if path.exists():
                data = json.loads(path.read_text())
                return ReviewItem.from_dict(data)
        return None

    def update(self, item: ReviewItem) -> ReviewItem:
        """Update a review item.

        Args:
            item: ReviewItem with updated values

        Returns:
            Updated ReviewItem

        Raises:
            ValueError: If item doesn't exist
        """
        # First try to find the old item in any status
        old_item = self.get(item.id)
        if old_item is None:
            raise ValueError(f"Review item not found: {item.id}")

        # If status changed, move the file
        old_path = self._item_path(item.id, old_item.status)
        new_path = self._item_path(item.id, item.status)

        # Delete old file
        if old_path.exists():
            old_path.unlink()

        # Write new file
        new_path.write_text(json.dumps(item.to_dict(), indent=2, default=str))
        return item

    def delete(self, item_id: str) -> bool:
        """Delete a review item.

        Args:
            item_id: Review item ID

        Returns:
            True if deleted, False if not found
        """
        item = self.get(item_id)
        if item is None:
            return False

        path = self._item_path(item_id, item.status)
        if path.exists():
            path.unlink()
        return True

    def list_by_status(
        self,
        status: ReviewStatus,
        item_type: ReviewType | None = None,
        priority: ReviewPriority | None = None,
    ) -> list[ReviewItem]:
        """List items by status with optional filters.

        Args:
            status: Status to filter by
            item_type: Optional type filter
            priority: Optional priority filter

        Returns:
            List of matching ReviewItems
        """
        items: list[ReviewItem] = []
        status_dir = self._get_status_dir(status)

        if not status_dir.exists():
            return items

        for item_file in status_dir.glob("*.json"):
            data = json.loads(item_file.read_text())
            item = ReviewItem.from_dict(data)

            # Apply filters
            if item_type and item.type != item_type:
                continue
            if priority and item.priority != priority:
                continue

            items.append(item)

        # Sort by priority (urgent, high, medium, low) and then by created_at
        priority_order = {
            ReviewPriority.URGENT: 0,
            ReviewPriority.HIGH: 1,
            ReviewPriority.MEDIUM: 2,
            ReviewPriority.LOW: 3,
        }
        items.sort(key=lambda x: (priority_order[x.priority], x.created_at), reverse=True)
        return items

    def list_pending(
        self,
        item_type: ReviewType | None = None,
        priority: ReviewPriority | None = None,
    ) -> list[ReviewItem]:
        """List pending review items.

        Args:
            item_type: Optional type filter
            priority: Optional priority filter

        Returns:
            List of pending ReviewItems
        """
        return self.list_by_status(ReviewStatus.PENDING, item_type, priority)

    def list_all(
        self,
        status: ReviewStatus | None = None,
        item_type: ReviewType | None = None,
        priority: ReviewPriority | None = None,
    ) -> list[ReviewItem]:
        """List all items with optional filters.

        Args:
            status: Optional status filter
            item_type: Optional type filter
            priority: Optional priority filter

        Returns:
            List of matching ReviewItems
        """
        if status is not None:
            return self.list_by_status(status, item_type, priority)

        all_items = []
        for review_status in ReviewStatus:
            all_items.extend(self.list_by_status(review_status, item_type, priority))
        return all_items

    def approve(self, item_id: str, reviewed_by: str, notes: str | None = None) -> ReviewItem:
        """Approve a pending review item.

        Args:
            item_id: Review item ID
            reviewed_by: Who is approving
            notes: Optional approval notes

        Returns:
            Approved ReviewItem

        Raises:
            ValueError: If item not found or already resolved
        """
        item = self.get(item_id)
        if item is None:
            raise ValueError(f"Review item not found: {item_id}")

        item.approve(reviewed_by, notes)
        return self.update(item)

    def reject(self, item_id: str, reviewed_by: str, notes: str | None = None) -> ReviewItem:
        """Reject a pending review item.

        Args:
            item_id: Review item ID
            reviewed_by: Who is rejecting
            notes: Optional rejection reason

        Returns:
            Rejected ReviewItem

        Raises:
            ValueError: If item not found or already resolved
        """
        item = self.get(item_id)
        if item is None:
            raise ValueError(f"Review item not found: {item_id}")

        item.reject(reviewed_by, notes)
        return self.update(item)

    def defer(self, item_id: str, notes: str | None = None) -> ReviewItem:
        """Defer a pending review item.

        Args:
            item_id: Review item ID
            notes: Optional deferral reason

        Returns:
            Deferred ReviewItem

        Raises:
            ValueError: If item not found or already resolved
        """
        item = self.get(item_id)
        if item is None:
            raise ValueError(f"Review item not found: {item_id}")

        item.defer(notes)
        return self.update(item)

    def count_by_status(self, status: ReviewStatus) -> int:
        """Count items in a given status.

        Args:
            status: Status to count

        Returns:
            Number of items with that status
        """
        status_dir = self._get_status_dir(status)
        if not status_dir.exists():
            return 0
        return len(list(status_dir.glob("*.json")))

    def count_all(self) -> dict[str, int]:
        """Count items by status.

        Returns:
            Dictionary of status -> count
        """
        return {status.value: self.count_by_status(status) for status in ReviewStatus}

    def cleanup_old_items(self, days: int = 30) -> int:
        """Delete items older than specified days from approved/rejected/deferred.

        Args:
            days: Age in days (default 30)

        Returns:
            Number of items deleted
        """
        cutoff_date = datetime.now(UTC) - timedelta(days=days)
        deleted_count = 0

        # Only clean up non-pending statuses
        for status in [
            ReviewStatus.APPROVED,
            ReviewStatus.REJECTED,
            ReviewStatus.DEFERRED,
        ]:
            status_dir = self._get_status_dir(status)
            if not status_dir.exists():
                continue

            for item_file in status_dir.glob("*.json"):
                data = json.loads(item_file.read_text())
                item = ReviewItem.from_dict(data)

                if item.reviewed_at and item.reviewed_at < cutoff_date:
                    item_file.unlink()
                    deleted_count += 1

        return deleted_count

    def export_stats(self) -> dict[str, Any]:
        """Export queue statistics.

        Returns:
            Dictionary with queue statistics
        """
        counts = self.count_all()
        pending = self.list_pending()

        # Group pending by priority
        priority_counts = {}
        for priority in ReviewPriority:
            priority_counts[priority.value] = len(
                [item for item in pending if item.priority == priority]
            )

        # Group pending by type
        type_counts = {}
        for item_type in ReviewType:
            type_counts[item_type.value] = len([item for item in pending if item.type == item_type])

        return {
            "counts_by_status": counts,
            "pending_by_priority": priority_counts,
            "pending_by_type": type_counts,
            "total_pending": counts["pending"],
            "total_all": sum(counts.values()),
        }

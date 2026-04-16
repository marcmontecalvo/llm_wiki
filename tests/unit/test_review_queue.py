"""Tests for the review queue."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from llm_wiki.review.models import ReviewItem, ReviewPriority, ReviewStatus, ReviewType
from llm_wiki.review.queue import ReviewQueue


class TestReviewItem:
    """Tests for ReviewItem model."""

    def test_create_review_item(self):
        """Test creating a review item."""
        now = datetime.now(UTC)
        item = ReviewItem(
            id="test-001",
            type=ReviewType.PAGE,
            target_id="page-123",
            reason="Low quality page",
            priority=ReviewPriority.MEDIUM,
            status=ReviewStatus.PENDING,
            created_at=now,
        )

        assert item.id == "test-001"
        assert item.type == ReviewType.PAGE
        assert item.target_id == "page-123"
        assert item.reason == "Low quality page"
        assert item.priority == ReviewPriority.MEDIUM
        assert item.status == ReviewStatus.PENDING

    def test_is_pending(self):
        """Test is_pending method."""
        item = ReviewItem(
            id="test-001",
            type=ReviewType.PAGE,
            target_id="page-123",
            reason="Test",
            created_at=datetime.now(UTC),
            status=ReviewStatus.PENDING,
        )
        assert item.is_pending() is True

    def test_is_resolved(self):
        """Test is_resolved method."""
        pending_item = ReviewItem(
            id="test-001",
            type=ReviewType.PAGE,
            target_id="page-123",
            reason="Test",
            created_at=datetime.now(UTC),
            status=ReviewStatus.PENDING,
        )
        assert pending_item.is_resolved() is False

        approved_item = ReviewItem(
            id="test-002",
            type=ReviewType.PAGE,
            target_id="page-123",
            reason="Test",
            created_at=datetime.now(UTC),
            status=ReviewStatus.APPROVED,
            reviewed_at=datetime.now(UTC),
            reviewed_by="tester",
        )
        assert approved_item.is_resolved() is True

    def test_approve(self):
        """Test approving a review item."""
        item = ReviewItem(
            id="test-001",
            type=ReviewType.PAGE,
            target_id="page-123",
            reason="Test",
            created_at=datetime.now(UTC),
        )

        item.approve("reviewer", "Looks good")

        assert item.status == ReviewStatus.APPROVED
        assert item.reviewed_by == "reviewer"
        assert item.notes == "Looks good"
        assert item.reviewed_at is not None

    def test_reject(self):
        """Test rejecting a review item."""
        item = ReviewItem(
            id="test-001",
            type=ReviewType.PAGE,
            target_id="page-123",
            reason="Test",
            created_at=datetime.now(UTC),
        )

        item.reject("reviewer", "Needs more work")

        assert item.status == ReviewStatus.REJECTED
        assert item.reviewed_by == "reviewer"
        assert item.notes == "Needs more work"

    def test_defer(self):
        """Test deferring a review item."""
        item = ReviewItem(
            id="test-001",
            type=ReviewType.PAGE,
            target_id="page-123",
            reason="Test",
            created_at=datetime.now(UTC),
        )

        item.defer("Waiting for more info")

        assert item.status == ReviewStatus.DEFERRED
        assert item.notes == "Waiting for more info"

    def test_cannot_approve_resolved(self):
        """Test that approving an already resolved item raises error."""
        item = ReviewItem(
            id="test-001",
            type=ReviewType.PAGE,
            target_id="page-123",
            reason="Test",
            created_at=datetime.now(UTC),
            status=ReviewStatus.APPROVED,
            reviewed_at=datetime.now(UTC),
            reviewed_by="tester",
        )

        with pytest.raises(ValueError, match="already"):
            item.approve("another", "Should fail")


class TestReviewQueue:
    """Tests for ReviewQueue."""

    @pytest.fixture
    def queue_dir(self, temp_dir: Path) -> Path:
        """Create temporary queue directory."""
        qd = temp_dir / "review_queue"
        qd.mkdir(parents=True)
        return qd

    @pytest.fixture
    def queue(self, queue_dir: Path) -> ReviewQueue:
        """Create review queue instance."""
        return ReviewQueue(queue_dir=queue_dir)

    def test_create_review_item(self, queue: ReviewQueue, queue_dir: Path):
        """Test creating a review item."""
        now = datetime.now(UTC)
        item = ReviewItem(
            id="test-001",
            type=ReviewType.PAGE,
            target_id="page-123",
            reason="Low quality page",
            created_at=now,
        )

        result = queue.create(item)

        assert result.id == "test-001"
        assert (queue_dir / "pending" / "test-001.json").exists()

    def test_create_duplicate_raises(self, queue: ReviewQueue):
        """Test creating duplicate item raises error."""
        item = ReviewItem(
            id="test-001",
            type=ReviewType.PAGE,
            target_id="page-123",
            reason="Test",
            created_at=datetime.now(UTC),
        )
        queue.create(item)

        with pytest.raises(ValueError, match="already exists"):
            queue.create(item)

    def test_get_item(self, queue: ReviewQueue):
        """Test getting an item."""
        item = ReviewItem(
            id="test-001",
            type=ReviewType.PAGE,
            target_id="page-123",
            reason="Test",
            created_at=datetime.now(UTC),
        )
        queue.create(item)

        retrieved = queue.get("test-001")

        assert retrieved is not None
        assert retrieved.id == "test-001"
        assert retrieved.type == ReviewType.PAGE

    def test_get_nonexistent(self, queue: ReviewQueue):
        """Test getting non-existent item returns None."""
        result = queue.get("nonexistent")
        assert result is None

    def test_update_item_status(self, queue: ReviewQueue, queue_dir: Path):
        """Test updating item status."""
        item = ReviewItem(
            id="test-001",
            type=ReviewType.PAGE,
            target_id="page-123",
            reason="Test",
            created_at=datetime.now(UTC),
        )
        queue.create(item)

        # Approve the item
        updated = queue.approve("test-001", "tester", "Approved")

        assert updated.status == ReviewStatus.APPROVED
        assert (queue_dir / "approved" / "test-001.json").exists()

    def test_delete_item(self, queue: ReviewQueue):
        """Test deleting an item."""
        item = ReviewItem(
            id="test-001",
            type=ReviewType.PAGE,
            target_id="page-123",
            reason="Test",
            created_at=datetime.now(UTC),
        )
        queue.create(item)

        result = queue.delete("test-001")

        assert result is True
        assert queue.get("test-001") is None

    def test_list_pending(self, queue: ReviewQueue):
        """Test listing pending items."""
        now = datetime.now(UTC)
        
        # Create some items
        for i in range(3):
            item = ReviewItem(
                id=f"test-{i:03d}",
                type=ReviewType.PAGE,
                target_id=f"page-{i}",
                reason="Test",
                priority=ReviewPriority.MEDIUM if i % 2 else ReviewPriority.HIGH,
                created_at=now,
            )
            queue.create(item)

        pending = queue.list_pending()

        assert len(pending) == 3

    def test_list_with_filters(self, queue: ReviewQueue):
        """Test listing with filters."""
        now = datetime.now(UTC)

        # Create items of different types
        page_item = ReviewItem(
            id="page-001",
            type=ReviewType.PAGE,
            target_id="page-123",
            reason="Test",
            created_at=now,
        )
        queue.create(page_item)

        claim_item = ReviewItem(
            id="claim-001",
            type=ReviewType.CLAIM,
            target_id="claim-456",
            reason="Test",
            created_at=now,
        )
        queue.create(claim_item)

        # Filter by type
        pages = queue.list_by_status(ReviewStatus.PENDING, item_type=ReviewType.PAGE)
        assert len(pages) == 1

    def test_count_by_status(self, queue: ReviewQueue):
        """Test counting items by status."""
        now = datetime.now(UTC)

        item1 = ReviewItem(
            id="test-001",
            type=ReviewType.PAGE,
            target_id="page-123",
            reason="Test",
            created_at=now,
        )
        queue.create(item1)

        pending_count = queue.count_by_status(ReviewStatus.PENDING)
        assert pending_count == 1

    def test_cleanup_old_items(self, queue: ReviewQueue):
        """Test cleanup of old items."""
        now = datetime.now(UTC)

        # Create old approved item
        old_approved = ReviewItem(
            id="old-001",
            type=ReviewType.PAGE,
            target_id="page-old",
            reason="Test",
            created_at=now - timedelta(days=35),
            status=ReviewStatus.APPROVED,
            reviewed_at=now - timedelta(days=35),
            reviewed_by="tester",
        )
        queue.create(old_approved)

        # Create recent pending item
        recent = ReviewItem(
            id="recent-001",
            type=ReviewType.PAGE,
            target_id="page-recent",
            reason="Test",
            created_at=now - timedelta(days=5),
        )
        queue.create(recent)

        deleted = queue.cleanup_old_items(30)

        # Old item should be deleted
        assert deleted >= 1
        # Recent item should still exist
        assert queue.get("recent-001") is not None

    def test_export_stats(self, queue: ReviewQueue):
        """Test exporting queue statistics."""
        now = datetime.now(UTC)

        item = ReviewItem(
            id="test-001",
            type=ReviewType.PAGE,
            target_id="page-123",
            reason="Test",
            priority=ReviewPriority.HIGH,
            created_at=now,
        )
        queue.create(item)

        stats = queue.export_stats()

        assert "counts_by_status" in stats
        assert stats["total_pending"] == 1
        assert stats["pending_by_priority"]["high"] == 1
        assert stats["pending_by_type"]["page"] == 1
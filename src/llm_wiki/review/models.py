"""Models for the review queue system."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ReviewType(StrEnum):
    """Type of item being reviewed."""

    PAGE = "page"
    CLAIM = "claim"
    CONTRADICTION = "contradiction"
    PROMOTION = "promotion"
    DUPLICATE = "duplicate"
    ROUTING_MISTAKE = "routing_mistake"
    SOURCELESS_CLAIM = "sourceless_claim"
    MANUAL = "manual"


class ReviewStatus(StrEnum):
    """Status of a review item."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class ReviewPriority(StrEnum):
    """Priority level for review items."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class ReviewItem(BaseModel):
    """A single item in the review queue."""

    id: str = Field(..., description="Unique review item ID")
    type: ReviewType = Field(..., description="Type of review item")
    target_id: str = Field(..., description="ID of the thing being reviewed")
    reason: str = Field(..., description="Why it needs review")
    priority: ReviewPriority = Field(default=ReviewPriority.MEDIUM, description="Priority level")
    status: ReviewStatus = Field(default=ReviewStatus.PENDING, description="Current status")
    created_at: datetime = Field(..., description="When the review item was created")
    reviewed_at: datetime | None = Field(default=None, description="When the review was completed")
    reviewed_by: str | None = Field(default=None, description="Who performed the review")
    notes: str | None = Field(default=None, description="Reviewer notes or reason for decision")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Type-specific metadata")

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Validate review item ID is not empty."""
        if not v or not v.strip():
            raise ValueError("Review item ID cannot be empty")
        return v

    @field_validator("target_id")
    @classmethod
    def validate_target_id(cls, v: str) -> str:
        """Validate target ID is not empty."""
        if not v or not v.strip():
            raise ValueError("Target ID cannot be empty")
        return v

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        """Validate reason is not empty."""
        if not v or not v.strip():
            raise ValueError("Reason cannot be empty")
        return v

    def is_pending(self) -> bool:
        """Check if item is pending review."""
        return self.status == ReviewStatus.PENDING

    def is_resolved(self) -> bool:
        """Check if item has been resolved (approved, rejected, or deferred)."""
        return self.status in (
            ReviewStatus.APPROVED,
            ReviewStatus.REJECTED,
            ReviewStatus.DEFERRED,
        )

    def approve(self, reviewed_by: str, notes: str | None = None) -> None:
        """Approve the review item.

        Args:
            reviewed_by: Who is approving
            notes: Optional approval notes

        Raises:
            ValueError: If item is already resolved
        """
        if self.is_resolved():
            raise ValueError(f"Cannot approve: item is already {self.status.value}")
        self.status = ReviewStatus.APPROVED
        self.reviewed_by = reviewed_by
        self.reviewed_at = datetime.now(UTC)
        if notes:
            self.notes = notes

    def reject(self, reviewed_by: str, notes: str | None = None) -> None:
        """Reject the review item.

        Args:
            reviewed_by: Who is rejecting
            notes: Optional rejection reason

        Raises:
            ValueError: If item is already resolved
        """
        if self.is_resolved():
            raise ValueError(f"Cannot reject: item is already {self.status.value}")
        self.status = ReviewStatus.REJECTED
        self.reviewed_by = reviewed_by
        self.reviewed_at = datetime.now(UTC)
        if notes:
            self.notes = notes

    def defer(self, notes: str | None = None) -> None:
        """Defer the review item for later.

        Args:
            notes: Optional deferral reason

        Raises:
            ValueError: If item is already resolved
        """
        if self.is_resolved():
            raise ValueError(f"Cannot defer: item is already {self.status.value}")
        self.status = ReviewStatus.DEFERRED
        if notes:
            self.notes = notes

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage.

        Returns:
            Dictionary representation of the review item
        """
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewItem":
        """Create ReviewItem from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            ReviewItem instance
        """
        return cls.model_validate(data)

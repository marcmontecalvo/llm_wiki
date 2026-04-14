"""Integration and merge models for deterministic content merging."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, Field

# Type aliases for merge strategies
MergeStrategy: TypeAlias = Literal[
    "keep_existing",
    "use_extracted",
    "union",
    "deduplicate_merge",
    "prefer_newer",
    "set_to_now",
]

ChangeType: TypeAlias = Literal["added", "removed", "updated", "merged", "deduped"]
ConflictResolution: TypeAlias = Literal["keep_existing", "use_extracted", "manual_review"]


class MergeStrategies(BaseModel):
    """Configuration for merge strategies per field."""

    title: MergeStrategy = Field(default="keep_existing", description="Title merge strategy")
    domain: MergeStrategy = Field(default="keep_existing", description="Domain merge strategy")
    tags: MergeStrategy = Field(default="union", description="Tags merge strategy")
    entities: MergeStrategy = Field(default="union", description="Entities merge strategy")
    concepts: MergeStrategy = Field(default="union", description="Concepts merge strategy")
    summary: MergeStrategy = Field(default="prefer_newer", description="Summary merge strategy")
    claims: MergeStrategy = Field(default="deduplicate_merge", description="Claims merge strategy")
    relationships: MergeStrategy = Field(
        default="union", description="Relationships merge strategy"
    )
    source: MergeStrategy = Field(default="keep_existing", description="Source merge strategy")
    created: MergeStrategy = Field(default="keep_existing", description="Created date merge")
    updated: MergeStrategy = Field(default="set_to_now", description="Updated date merge")
    status: MergeStrategy = Field(default="keep_existing", description="Status merge strategy")
    confidence: MergeStrategy = Field(default="prefer_newer", description="Confidence merge")
    links: MergeStrategy = Field(default="union", description="Links merge strategy")
    sources: MergeStrategy = Field(default="union", description="Sources merge strategy")


@dataclass
class Change:
    """Represents a single change during integration."""

    field: str
    old_value: Any
    new_value: Any
    change_type: ChangeType
    timestamp: datetime
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "field": self.field,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "change_type": self.change_type,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
        }


@dataclass
class IntegrationConflict:
    """Represents a conflict detected during integration."""

    field: str
    existing_value: Any
    extracted_value: Any
    resolution: ConflictResolution
    reason: str
    confidence_diff: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "field": self.field,
            "existing_value": self.existing_value,
            "extracted_value": self.extracted_value,
            "resolution": self.resolution,
            "reason": self.reason,
            "confidence_diff": self.confidence_diff,
        }


@dataclass
class IntegrationResult:
    """Result of an integration operation."""

    page_id: str
    changes: list[Change] = field(default_factory=list)
    conflicts: list[IntegrationConflict] = field(default_factory=list)
    success: bool = True
    error: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    # Statistics
    total_fields_checked: int = 0
    fields_changed: int = 0
    fields_merged: int = 0
    conflicts_detected: int = 0

    def has_conflicts(self) -> bool:
        """Check if integration resulted in conflicts."""
        return len(self.conflicts) > 0

    def has_changes(self) -> bool:
        """Check if integration resulted in changes."""
        return len(self.changes) > 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "page_id": self.page_id,
            "success": self.success,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
            "changes": [change.to_dict() for change in self.changes],
            "conflicts": [conflict.to_dict() for conflict in self.conflicts],
            "statistics": {
                "total_fields_checked": self.total_fields_checked,
                "fields_changed": self.fields_changed,
                "fields_merged": self.fields_merged,
                "conflicts_detected": self.conflicts_detected,
            },
        }


@dataclass
class IntegrationState:
    """Represents the state of a page before integration (for rollback support)."""

    page_id: str
    snapshot: dict[str, Any]
    timestamp: datetime
    result: IntegrationResult | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "page_id": self.page_id,
            "snapshot": self.snapshot,
            "timestamp": self.timestamp.isoformat(),
            "result": self.result.to_dict() if self.result else None,
        }

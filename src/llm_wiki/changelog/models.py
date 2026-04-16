"""Data models for the wiki change log."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class FieldChange:
    """Records a change to a single field."""

    field: str
    old_value: Any
    new_value: Any
    change_type: str  # added, modified, removed

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dict."""
        return {
            "field": self.field,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "change_type": self.change_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FieldChange:
        """Deserialise from a dict."""
        return cls(
            field=data["field"],
            old_value=data.get("old_value"),
            new_value=data.get("new_value"),
            change_type=data["change_type"],
        )


def _generate_change_id(page_id: str, timestamp: str) -> str:
    """Produce a unique, short change ID (includes random UUID to avoid collisions)."""
    raw = f"{page_id}::{timestamp}::{uuid.uuid4()}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


@dataclass
class ChangeLogEntry:
    """A single change event for a wiki page."""

    id: str
    page_id: str
    timestamp: str  # ISO-8601 string
    change_type: str  # created, updated, deleted, merged, promoted, reverted
    actor: str  # user, system, content-extractor, governance, …
    changes: list[FieldChange] = field(default_factory=list)
    reason: str | None = None
    parent_change_id: str | None = None

    @classmethod
    def create(
        cls,
        page_id: str,
        change_type: str,
        actor: str,
        changes: list[FieldChange] | None = None,
        reason: str | None = None,
        parent_change_id: str | None = None,
    ) -> ChangeLogEntry:
        """Factory that auto-generates an ID and timestamp.

        Args:
            page_id: The page being changed.
            change_type: One of ``created``, ``updated``, ``deleted``,
                         ``merged``, ``promoted``, ``reverted``.
            actor: Who/what made the change.
            changes: List of field-level changes.
            reason: Human-readable explanation.
            parent_change_id: ID of the preceding entry for this page.

        Returns:
            New :class:`ChangeLogEntry`.
        """
        ts = datetime.now(UTC).isoformat()
        entry_id = _generate_change_id(page_id, ts)
        return cls(
            id=entry_id,
            page_id=page_id,
            timestamp=ts,
            change_type=change_type,
            actor=actor,
            changes=changes or [],
            reason=reason,
            parent_change_id=parent_change_id,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dict."""
        return {
            "id": self.id,
            "page_id": self.page_id,
            "timestamp": self.timestamp,
            "change_type": self.change_type,
            "actor": self.actor,
            "changes": [c.to_dict() for c in self.changes],
            "reason": self.reason,
            "parent_change_id": self.parent_change_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChangeLogEntry:
        """Deserialise from a dict."""
        return cls(
            id=data["id"],
            page_id=data["page_id"],
            timestamp=data["timestamp"],
            change_type=data["change_type"],
            actor=data["actor"],
            changes=[FieldChange.from_dict(c) for c in data.get("changes", [])],
            reason=data.get("reason"),
            parent_change_id=data.get("parent_change_id"),
        )


def diff_metadata(
    old: dict[str, Any],
    new: dict[str, Any],
    tracked_fields: list[str] | None = None,
) -> list[FieldChange]:
    """Compare two metadata dicts and return a list of field changes.

    Args:
        old: Previous metadata (may be empty for newly created pages).
        new: Updated metadata.
        tracked_fields: Whitelist of field names to inspect.  When ``None``
                        all keys in either dict are considered.

    Returns:
        List of :class:`FieldChange` objects describing what changed.
    """
    all_keys = set(old) | set(new)
    if tracked_fields is not None:
        all_keys = all_keys & set(tracked_fields)

    field_changes: list[FieldChange] = []
    for key in sorted(all_keys):
        old_val = old.get(key)
        new_val = new.get(key)

        if old_val is None and new_val is not None:
            field_changes.append(FieldChange(key, old_val, new_val, "added"))
        elif old_val is not None and new_val is None:
            field_changes.append(FieldChange(key, old_val, new_val, "removed"))
        elif old_val != new_val:
            field_changes.append(FieldChange(key, old_val, new_val, "modified"))

    return field_changes

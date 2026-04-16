"""ChangeLog — persistent store for wiki page change history."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llm_wiki.changelog.models import ChangeLogEntry, FieldChange

logger = logging.getLogger(__name__)

# Fields that are tracked by default during metadata diff comparisons.
DEFAULT_TRACKED_FIELDS = [
    "title",
    "summary",
    "tags",
    "kind",
    "domain",
    "source",
    "aliases",
    "entities",
    "concepts",
    "relationships",
    "claims",
    "quality_score",
]


class ChangeLog:
    """Persistent log of all changes made to wiki pages.

    Storage layout::

        <changelog_dir>/
        ├── index.json          # change_id -> {page_id, timestamp, change_type, actor}
        └── pages/
            └── <page_id>.json  # ordered list of full ChangeLogEntry dicts

    Args:
        changelog_dir: Directory for the change log files.
                       Defaults to ``wiki_system/changelog``.
        max_entries_per_page: Soft cap on stored entries per page.  Older
                              entries are pruned when the cap is exceeded.
                              ``0`` means unlimited.
    """

    def __init__(
        self,
        changelog_dir: Path | None = None,
        max_entries_per_page: int = 1000,
    ):
        self.changelog_dir = changelog_dir or Path("wiki_system/changelog")
        self.max_entries_per_page = max_entries_per_page
        self._pages_dir = self.changelog_dir / "pages"
        self._index_file = self.changelog_dir / "index.json"

        # In-memory index: change_id -> lightweight summary
        self._index: dict[str, dict[str, str]] = {}

        # In-memory per-page history cache: page_id -> list[ChangeLogEntry]
        self._cache: dict[str, list[ChangeLogEntry]] = {}

    # ------------------------------------------------------------------
    # Initialisation / persistence
    # ------------------------------------------------------------------

    def ensure_dirs(self) -> None:
        """Create changelog directories if they don't exist."""
        self.changelog_dir.mkdir(parents=True, exist_ok=True)
        self._pages_dir.mkdir(parents=True, exist_ok=True)

    def load_index(self) -> None:
        """Load the lightweight index from disk."""
        if self._index_file.exists():
            try:
                data = json.loads(self._index_file.read_text(encoding="utf-8"))
                self._index = data
                logger.debug(f"Loaded changelog index ({len(self._index)} entries)")
            except Exception as e:
                logger.error(f"Failed to load changelog index: {e}")
                self._index = {}

    def save_index(self) -> None:
        """Persist the lightweight index to disk."""
        self.ensure_dirs()
        self._index_file.write_text(
            json.dumps(self._index, indent=2, sort_keys=True), encoding="utf-8"
        )

    def _page_file(self, page_id: str) -> Path:
        return self._pages_dir / f"{page_id}.json"

    def _load_page_entries(self, page_id: str) -> list[ChangeLogEntry]:
        """Load all entries for a page from disk (cached)."""
        if page_id in self._cache:
            return self._cache[page_id]

        pf = self._page_file(page_id)
        if not pf.exists():
            return []

        try:
            raw = json.loads(pf.read_text(encoding="utf-8"))
            entries = [ChangeLogEntry.from_dict(d) for d in raw]
            self._cache[page_id] = entries
            return entries
        except Exception as e:
            logger.error(f"Failed to load changelog for {page_id}: {e}")
            return []

    def _save_page_entries(self, page_id: str, entries: list[ChangeLogEntry]) -> None:
        """Write all entries for a page to disk."""
        self.ensure_dirs()
        pf = self._page_file(page_id)
        pf.write_text(
            json.dumps([e.to_dict() for e in entries], indent=2),
            encoding="utf-8",
        )
        self._cache[page_id] = entries

    # ------------------------------------------------------------------
    # Recording changes
    # ------------------------------------------------------------------

    def record(
        self,
        page_id: str,
        change_type: str,
        actor: str,
        changes: list[FieldChange] | None = None,
        reason: str | None = None,
    ) -> ChangeLogEntry:
        """Record a change event for *page_id*.

        Automatically sets the ``parent_change_id`` to the most recent
        existing entry for the page.

        Args:
            page_id: The page being changed.
            change_type: One of ``created``, ``updated``, ``deleted``,
                         ``merged``, ``promoted``, ``reverted``.
            actor: Who/what triggered the change.
            changes: Detailed field-level changes (optional).
            reason: Human-readable explanation (optional).

        Returns:
            The newly created :class:`ChangeLogEntry`.
        """
        existing = self._load_page_entries(page_id)
        parent_id = existing[-1].id if existing else None

        entry = ChangeLogEntry.create(
            page_id=page_id,
            change_type=change_type,
            actor=actor,
            changes=changes or [],
            reason=reason,
            parent_change_id=parent_id,
        )

        # Append to per-page history
        updated = existing + [entry]

        # Prune if over limit
        if self.max_entries_per_page and len(updated) > self.max_entries_per_page:
            updated = updated[-self.max_entries_per_page :]

        self._save_page_entries(page_id, updated)

        # Update index
        self._index[entry.id] = {
            "page_id": page_id,
            "timestamp": entry.timestamp,
            "change_type": change_type,
            "actor": actor,
        }
        self.save_index()

        logger.debug(f"Recorded {change_type} change for {page_id} by {actor} [{entry.id}]")
        return entry

    # ------------------------------------------------------------------
    # Query interface
    # ------------------------------------------------------------------

    def get_page_history(self, page_id: str, limit: int = 50) -> list[ChangeLogEntry]:
        """Return the most recent *limit* change entries for *page_id*.

        Args:
            page_id: Page identifier.
            limit: Maximum number of entries to return (0 = all).

        Returns:
            List of entries, newest first.
        """
        entries = self._load_page_entries(page_id)
        # Newest first
        entries = list(reversed(entries))
        if limit:
            entries = entries[:limit]
        return entries

    def get_recent_changes(
        self,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[ChangeLogEntry]:
        """Return recent changes across all pages.

        Args:
            since: Only return changes at or after this time.  Must be
                   timezone-aware.  ``None`` means no lower bound.
            limit: Maximum number of entries to return.

        Returns:
            List of entries, newest first.
        """
        self.load_index()

        # Filter index by timestamp
        candidates: list[dict[str, str]] = []
        for change_id, summary in self._index.items():
            if since:
                entry_ts = datetime.fromisoformat(summary["timestamp"])
                if entry_ts < since:
                    continue
            candidates.append({"id": change_id, **summary})

        # Sort newest first
        candidates.sort(key=lambda x: x["timestamp"], reverse=True)
        candidates = candidates[:limit]

        # Load full entries
        results: list[ChangeLogEntry] = []
        for candidate in candidates:
            page_id = candidate["page_id"]
            entries = self._load_page_entries(page_id)
            for entry in entries:
                if entry.id == candidate["id"]:
                    results.append(entry)
                    break

        return results

    def get_changes_by_actor(self, actor: str, limit: int = 0) -> list[ChangeLogEntry]:
        """Return all changes made by *actor*.

        Args:
            actor: Actor name to filter on.
            limit: Maximum entries to return (0 = all).

        Returns:
            List of entries, newest first.
        """
        self.load_index()

        matching_ids = [cid for cid, summary in self._index.items() if summary["actor"] == actor]

        # Collect full entries
        results: list[ChangeLogEntry] = []
        seen_pages: set[str] = set()
        for change_id in matching_ids:
            page_id = self._index[change_id]["page_id"]
            if page_id not in seen_pages:
                seen_pages.add(page_id)
                entries = self._load_page_entries(page_id)
                results.extend(e for e in entries if e.actor == actor)

        # Sort newest first
        results.sort(key=lambda e: e.timestamp, reverse=True)
        if limit:
            results = results[:limit]
        return results

    def get_entry(self, change_id: str) -> ChangeLogEntry | None:
        """Look up a single change by its ID.

        Args:
            change_id: Change identifier.

        Returns:
            :class:`ChangeLogEntry` or ``None`` if not found.
        """
        self.load_index()
        summary = self._index.get(change_id)
        if not summary:
            return None

        entries = self._load_page_entries(summary["page_id"])
        for entry in entries:
            if entry.id == change_id:
                return entry
        return None

    def get_change_stats(self) -> dict[str, Any]:
        """Return aggregate statistics about the change log.

        Returns:
            Dict with ``total_changes``, ``total_pages``,
            ``changes_by_type``, ``changes_by_actor``, ``most_changed``.
        """
        self.load_index()

        changes_by_type: dict[str, int] = {}
        changes_by_actor: dict[str, int] = {}
        changes_per_page: dict[str, int] = {}

        for summary in self._index.values():
            ct = summary["change_type"]
            actor = summary["actor"]
            page_id = summary["page_id"]

            changes_by_type[ct] = changes_by_type.get(ct, 0) + 1
            changes_by_actor[actor] = changes_by_actor.get(actor, 0) + 1
            changes_per_page[page_id] = changes_per_page.get(page_id, 0) + 1

        most_changed = sorted(changes_per_page.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total_changes": len(self._index),
            "total_pages": len(changes_per_page),
            "changes_by_type": changes_by_type,
            "changes_by_actor": changes_by_actor,
            "most_changed": [{"page_id": p, "count": c} for p, c in most_changed],
        }

    # ------------------------------------------------------------------
    # Human-readable diff formatting
    # ------------------------------------------------------------------

    def format_diff(self, entry: ChangeLogEntry) -> str:
        """Format a change entry as a human-readable diff.

        Args:
            entry: The change to format.

        Returns:
            Multi-line string suitable for terminal output.
        """
        ts = entry.timestamp[:19].replace("T", " ")
        lines = [
            f"Change: {entry.id}",
            f"Page:   {entry.page_id}",
            f"Date:   {ts}",
            f"Type:   {entry.change_type}",
            f"Actor:  {entry.actor}",
        ]
        if entry.reason:
            lines.append(f"Reason: {entry.reason}")
        if entry.parent_change_id:
            lines.append(f"Parent: {entry.parent_change_id}")

        if entry.changes:
            lines.append("")
            lines.append("Changes:")
            for fc in entry.changes:
                lines.extend(_format_field_change(fc))
        else:
            lines.append("Changes: (none recorded)")

        return "\n".join(lines)

    def format_page_diff(
        self,
        page_id: str,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> str:
        """Format a summary of all changes to *page_id* in a time window.

        Args:
            page_id: Page to inspect.
            from_dt: Start of the window (inclusive, timezone-aware).
            to_dt: End of the window (inclusive, timezone-aware).  Defaults
                   to now.

        Returns:
            Multi-line string suitable for terminal output.
        """
        entries = self._load_page_entries(page_id)
        if not entries:
            return f"No change history found for {page_id!r}."

        from_iso = from_dt.isoformat() if from_dt else None
        to_iso = (to_dt or datetime.now(UTC)).isoformat()

        filtered = [
            e
            for e in entries
            if (from_iso is None or e.timestamp >= from_iso) and e.timestamp <= to_iso
        ]

        if not filtered:
            return f"No changes found for {page_id!r} in the specified range."

        lines = [f"Change history for: {page_id}", "=" * 50]
        for entry in reversed(filtered):
            lines.append("")
            lines.append(self.format_diff(entry))
            lines.append("-" * 40)

        return "\n".join(lines)


# ------------------------------------------------------------------
# Formatting helpers
# ------------------------------------------------------------------


def _format_field_change(fc: FieldChange) -> list[str]:
    """Return a list of diff-style lines for a single field change."""
    lines: list[str] = []
    if fc.change_type == "added":
        lines.append(f"  + {fc.field}: {_fmt_val(fc.new_value)}")
    elif fc.change_type == "removed":
        lines.append(f"  - {fc.field}: {_fmt_val(fc.old_value)}")
    else:  # modified
        lines.append(f"  ~ {fc.field}:")
        lines.append(f"      - {_fmt_val(fc.old_value)}")
        lines.append(f"      + {_fmt_val(fc.new_value)}")
    return lines


def _fmt_val(val: Any, max_len: int = 120) -> str:
    """Compact representation of a field value."""
    if val is None:
        return "(none)"
    text = repr(val) if not isinstance(val, str) else val
    if len(text) > max_len:
        text = text[:max_len] + "…"
    return text

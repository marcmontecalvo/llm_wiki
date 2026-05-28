"""Conflict review queue for workspace fact stores.

Stores conflict entries as JSONL under
``workspaces/{workspace_id}/facts/conflicts.jsonl``.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from llm_wiki.knowledge.models import KnowledgeConflict

logger = logging.getLogger(__name__)


class ReviewQueue:
    """File-backed conflict review queue."""

    def __init__(self, queue_dir: str | Path) -> None:
        self._queue_dir = Path(queue_dir)
        self._lock = threading.Lock()

    # ── Path helpers ───────────────────────────────────────────────────────

    def _conflicts_path(self, workspace_id: str) -> Path:
        """Return the path to the conflicts JSONL file for a workspace."""
        return self._queue_dir / workspace_id / "facts" / "conflicts.jsonl"

    def _ensure_conflicts_dir(self, workspace_id: str) -> None:
        """Create directories for the workspace conflict file."""
        p = self._conflicts_path(workspace_id)
        p.parent.mkdir(parents=True, exist_ok=True)

    # ── Conflict persistence ──────────────────────────────────────────────

    def add_conflict(
        self,
        workspace_id: str,
        fact_key: str,
        conflict: KnowledgeConflict,
    ) -> None:
        """Append a conflict entry to conflicts.jsonl.

        Protected by ``self._lock`` to prevent torn writes when
        ``add_conflict`` and ``resolve_conflict`` race against each
        other (e.g. parallel callers reading–modifying–writing the
        same JSONL file).
        """
        with self._lock:
            self._add_conflict_unlocked(workspace_id, fact_key, conflict)

    def _add_conflict_unlocked(
        self,
        workspace_id: str,
        fact_key: str,
        conflict: KnowledgeConflict,
    ) -> None:
        """Internal: append a conflict entry (caller must hold _lock)."""
        self._ensure_conflicts_dir(workspace_id)
        path = self._conflicts_path(workspace_id)

        entry: dict[str, Any] = {
            "key": fact_key,
            "workspace_id": workspace_id,
            "candidates": conflict.candidates,
            "requires_review": conflict.requires_review,
            "resolved": False,
            "resolved_at": None,
            "resolution_choice": None,
            "created_at": datetime.now(tz=UTC).isoformat(),
        }

        line = json.dumps(entry, default=str) + "\n"

        # Atomic append: read existing + new line, write as one file
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            existing = b""
            if path.exists():
                try:
                    existing = path.read_bytes()
                except OSError:
                    pass
            with os.fdopen(fd, "wb") as f:
                f.write(existing)
                f.write(line.encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ── Conflict listing ───────────────────────────────────────────────────

    def list_conflicts(
        self,
        workspace_id: str | None = None,
        *,
        unresolved_only: bool = True,
    ) -> list[dict[str, Any]]:
        """List conflict entries, optionally scoped to a workspace.

        Returns unresolved conflicts sorted by ``created_at`` descending.
        """
        results: list[dict[str, Any]] = []

        if workspace_id is not None:
            paths = [self._conflicts_path(workspace_id)]
        else:
            # Scan all workspaces
            base = self._queue_dir
            if not base.exists():
                return []
            paths = []
            for ws_dir in sorted(base.iterdir()):
                if not ws_dir.is_dir():
                    continue
                cp = self._conflicts_path(ws_dir.name)
                if cp.exists():
                    paths.append(cp)

        for path in paths:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if unresolved_only and entry.get("resolved", False):
                    continue
                results.append(entry)

        # Sort by timestamp descending
        results.sort(key=lambda e: e.get("created_at", ""), reverse=True)
        return results

    # ── Conflict resolution ────────────────────────────────────────────────

    def resolve_conflict(
        self,
        workspace_id: str,
        fact_key: str,
        choice: Literal["canonical", "reject", "stale"],
        candidate_index: int | None = None,
    ) -> dict[str, Any]:
        """Mark a conflict as resolved.

        Protected by ``self._lock`` to prevent races with ``add_conflict``.
        """
        with self._lock:
            return self._resolve_conflict_unlocked(workspace_id, fact_key, choice, candidate_index)

    def _resolve_conflict_unlocked(
        self,
        workspace_id: str,
        fact_key: str,
        choice: Literal["canonical", "reject", "stale"],
        candidate_index: int | None = None,
    ) -> dict[str, Any]:
        """Internal: resolve a conflict (caller must hold _lock)."""
        self._ensure_conflicts_dir(workspace_id)
        path = self._conflicts_path(workspace_id)

        if not path.exists():
            return {
                "key": fact_key,
                "workspace_id": workspace_id,
                "resolved": False,
                "error": "conflict_not_found",
            }

        lines = path.read_text(encoding="utf-8").splitlines()
        updated_lines: list[str] = []
        found = False
        resolved_at = datetime.now(tz=UTC).isoformat()
        result_entry: dict[str, Any] = {}

        for line in lines:
            line = line.strip()
            if not line:
                updated_lines.append(line)
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                updated_lines.append(line)
                continue

            if entry.get("key") == fact_key and not entry.get("resolved", False):
                found = True
                entry["resolved"] = True
                entry["resolved_at"] = resolved_at
                entry["resolution_choice"] = choice
                if candidate_index is not None:
                    entry["candidate_index"] = candidate_index
                result_entry = dict(entry)
                updated_lines.append(json.dumps(entry, default=str))
            else:
                updated_lines.append(line)

        # Write atomically
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "wb") as f:
                f.write(("\n".join(updated_lines) + "\n").encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        if not found:
            return {
                "key": fact_key,
                "workspace_id": workspace_id,
                "resolved": False,
                "error": "conflict_not_found",
            }

        return {**result_entry, "resolved": True}

"""File-backed, thread-safe fact store scoped by workspace_id.

Each workspace gets:
  - A directory: wiki_system/workspaces/{workspace_id}/facts/
  - An index:   facts/index.json (mapping key -> metadata)
  - A history:  facts/history/{hash}.jsonl (append-only version log)

Concurrency:
  - Per-fact locks for write operations on specific (workspace_id, fact_key) tuples.
  - Per-workspace lock for coarse index writes.
  - Read operations are lock-free (JSONL is append-only).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from llm_wiki.knowledge.categories import normalize_category
from llm_wiki.knowledge.models import (
    KnowledgeConflict,
    KnowledgeFact,
    KnowledgeFactWriteRequest,
    KnowledgeFactWriteResponse,
    KnowledgeListResponse,
    KnowledgeSource,
)
from llm_wiki.knowledge.review import ReviewQueue

logger = logging.getLogger(__name__)

# Re-export from canonical exceptions module for cross-module compatibility.
# The canonical exceptions live in llm_wiki.exceptions as WikiError subclasses;
# importing them here ensures raises in this module match what routes catch.
from llm_wiki.exceptions import (  # noqa: E402 F401
    FactConflictError,
    UnknownFactCategoryError,
    UnknownFactKeyError,
)


class WorkspaceFactStore:
    """Thread-safe, file-backed fact store scoped by workspace_id."""

    def __init__(self, wiki_base: str | None = None) -> None:
        self._wiki_base = wiki_base or os.environ.get("WIKI_ROOT", "wiki_system")
        # Per-fact lock: lazy, keyed by (workspace_id, fact_key)
        self._fact_locks: dict[tuple[str, str], threading.Lock] = {}
        # Per-workspace lock for coarse index operations
        self._workspace_locks: dict[str, threading.Lock] = {}
        # Protects dict insertions themselves (thread-safe lazy init)
        self._lock_lock = threading.Lock()
        # Lazy-initialized review queue
        self._review_queue: ReviewQueue | None = None

    # ── Lock helpers ───────────────────────────────────────────────────────

    def _get_fact_lock(self, workspace_id: str, fact_key: str) -> threading.Lock:
        key = (workspace_id, fact_key)
        if key not in self._fact_locks:
            with self._lock_lock:
                if key not in self._fact_locks:  # double-check
                    self._fact_locks[key] = threading.Lock()
        return self._fact_locks[key]

    def _get_workspace_lock(self, workspace_id: str) -> threading.Lock:
        if workspace_id not in self._workspace_locks:
            with self._lock_lock:
                if workspace_id not in self._workspace_locks:
                    self._workspace_locks[workspace_id] = threading.Lock()
        return self._workspace_locks[workspace_id]

    # ── Path helpers ───────────────────────────────────────────────────────

    def _workspace_facts_path(self, workspace_id: str) -> Path:
        return Path(self._wiki_base) / "workspaces" / workspace_id / "facts"

    def _index_path(self, workspace_id: str) -> Path:
        return self._workspace_facts_path(workspace_id) / "index.json"

    def _history_path(self, workspace_id: str, fact_key: str) -> Path:
        base = self._workspace_facts_path(workspace_id)
        hash_key = hashlib.sha256(fact_key.encode()).hexdigest()[:16]
        return base / "history" / f"{hash_key}.jsonl"

    def _ensure_workspace(self, workspace_id: str) -> Path:
        """Create directory structure atomically. Idempotent.

        Uses a single mkdir call for the full tree so concurrent callers
        never see a partially created workspace directory.
        """
        facts_dir = self._workspace_facts_path(workspace_id)
        facts_dir.mkdir(parents=True, exist_ok=True)
        (facts_dir / "categories").mkdir(parents=True, exist_ok=True)
        (facts_dir / "history").mkdir(parents=True, exist_ok=True)
        return facts_dir

    # ── Index operations ───────────────────────────────────────────────────

    def _read_index(self, workspace_id: str) -> dict[str, Any]:
        """Read index.json. Returns empty dict if missing or corrupt."""
        idx_path = self._index_path(workspace_id)
        if not idx_path.exists():
            return {}
        try:
            text = idx_path.read_text(encoding="utf-8")
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Corrupt index.json for workspace %s: %s", workspace_id, e)
        return {}

    def _write_index(self, workspace_id: str, index: dict[str, Any]) -> None:
        """Atomically write index.json."""
        idx_path = self._index_path(workspace_id)
        self._atomic_json(idx_path, index)

    def _atomic_json(self, path: Path, data: Any) -> None:
        """Write JSON atomically via temp file + os.replace."""
        dir_path = path.parent or Path(".")
        fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ── History operations ─────────────────────────────────────────────────

    def _parse_jsonl(self, path: Path) -> list[KnowledgeFact]:
        """Parse KnowledgeFacts from a JSONL file, skipping corrupt lines."""
        results: list[KnowledgeFact] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    results.append(KnowledgeFact(**json.loads(line)))
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning("Skipping corrupt line in %s: %s", path, e)
        except OSError as e:
            logger.warning("Failed to read %s: %s", path, e)
        return results

    def _read_history(self, workspace_id: str, fact_key: str) -> list[KnowledgeFact]:
        """Read all history entries from the JSONL file."""
        hist_path = self._history_path(workspace_id, fact_key)
        if not hist_path.exists():
            return []
        return self._parse_jsonl(hist_path)

    def _append_history(self, workspace_id: str, fact: KnowledgeFact) -> None:
        """Append a single JSON line to the history file atomically."""
        hist_path = self._history_path(workspace_id, fact.key)
        line = json.dumps(fact.model_dump(), default=str) + "\n"

        dir_path = hist_path.parent
        dir_path.mkdir(parents=True, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix=".tmp")
        try:
            # Read existing content if any. Safe because callers hold the
            # per-fact lock, so no concurrent writer targets this path.
            existing = b""
            if hist_path.exists():
                try:
                    existing = hist_path.read_bytes()
                except OSError:
                    pass

            with os.fdopen(fd, "wb") as f:
                f.write(existing)
                f.write(line.encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, hist_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ── Category validation ────────────────────────────────────────────────

    def _normalize_category(self, category: str) -> str:
        """Normalize category alias to canonical form."""
        return normalize_category(category)

    # ── Review queue access ────────────────────────────────────────────────

    @property
    def review_queue(self) -> ReviewQueue:
        """Return the lazy-initialized review-queue helper."""
        if self._review_queue is None:
            self._review_queue = ReviewQueue(queue_dir=Path(self._wiki_base) / "workspaces")
        return self._review_queue

    # ── Core CRUD ──────────────────────────────────────────────────────────

    def put_fact(
        self, workspace_id: str, write_req: KnowledgeFactWriteRequest
    ) -> KnowledgeFactWriteResponse:
        """Create or update a fact. Thread-safe via per-fact lock.

        Optimistic concurrency: if expected_previous_version or
        expected_previous_updated_at is provided and doesn't match, returns
        stale_rejected.
        """
        category = self._normalize_category(write_req.category)
        return self._put_fact_internal(
            workspace_id=workspace_id,
            fact_key=write_req.key,
            request=write_req,
            category=category,
        )

    def get_fact(self, workspace_id: str, fact_key: str) -> KnowledgeFact | None:
        """Read the most recent version of a fact.

        Returns the fact unless the latest history entry is a tombstone
        (status="deleted"), in which case None is returned. If the latest
        entry is a tombstone but there are older non-deleted entries, those
        are NOT returned — a deletion means "this fact no longer exists."
        """
        history = self._read_history(workspace_id, fact_key)
        if not history:
            return None
        latest = history[-1]
        if latest.status == "deleted":
            return None
        return latest

    def delete_fact(self, workspace_id: str, fact_key: str) -> KnowledgeFact | None:
        """Write a tombstone with status=deleted. Returns the tombstone."""
        latest = self.get_fact(workspace_id, fact_key)
        if latest is None:
            return None
        tombstone = KnowledgeFact(
            id=latest.id,
            workspace_id=workspace_id,
            category=latest.category,
            key=latest.key,
            value=latest.value,
            source=latest.source,
            provenance=latest.provenance,
            confidence=latest.confidence,
            authority_score=latest.authority_score,
            status="deleted",
            visibility=latest.visibility,
            valid_from=latest.valid_from,
            valid_until=latest.valid_until,
            created_at=latest.created_at,
            updated_at=datetime.now(tz=UTC),
            version=latest.version + 1,
        )
        self._append_history(workspace_id, fact=tombstone)
        return tombstone

    def list_facts(
        self,
        workspace_id: str,
        *,
        category: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> KnowledgeListResponse:
        """Paginated list of facts from index.json."""
        index = self._read_index(workspace_id)
        if not index:
            return KnowledgeListResponse()

        # Build fact list: resolve each index entry from history
        facts: list[KnowledgeFact] = []
        for key, meta in index.items():
            if category and meta.get("category") != category:
                continue
            fact = self.get_fact(workspace_id, key)
            if fact is not None:
                facts.append(fact)

        # Cursor pagination (simple offset-based via base64-like token)
        offset = 0
        if cursor:
            try:
                offset = int(cursor)
            except ValueError:
                offset = 0

        limited = facts[offset : offset + limit]
        total_hint = len(facts)
        next_cursor = str(offset + limit) if (offset + limit) < total_hint else None

        return KnowledgeListResponse(
            facts=limited,
            next_cursor=next_cursor,
            total_hint=total_hint,
        )

    def batch_put(
        self,
        workspace_id: str,
        requests: list[KnowledgeFactWriteRequest],
        *,
        category_map: dict[str, str] | None = None,
    ) -> list[KnowledgeFactWriteResponse]:
        """Process writes sequentially, each under its own per-fact lock.

        Deduplicates conflicts per fact_key within the batch — if a
        conflict is already recorded for a key in the same batch,
        subsequent writes for that key don't create duplicate entries.
        """
        cat_map = category_map or {}
        results: list[KnowledgeFactWriteResponse] = []
        # Track which fact keys have had a conflict created in this batch
        conflicts_created: set[str] = set()
        for req in requests:
            category = self._normalize_category(cat_map.get(req.category, req.category))
            result = self._put_fact_internal(
                workspace_id=workspace_id,
                fact_key=req.key,
                request=req,
                category=category,
                _known_conflicts=conflicts_created,
            )
            results.append(result)
        return results

    def get_history(self, workspace_id: str, fact_key: str) -> list[KnowledgeFact]:
        """Return full version history for a fact."""
        return self._read_history(workspace_id, fact_key)

    def resolve_conflict(
        self,
        workspace_id: str,
        fact_key: str,
        choice: Literal["canonical", "reject", "stale"],
        candidate_index: int | None = None,
    ) -> dict[str, Any]:
        """Resolve a conflict and apply the chosen resolution as a new fact version.

        Resolution strategies:
        - ``canonical``: Pick the candidate at ``candidate_index``, write its
          value as the new version.
        - ``reject``: Reject the new (candidate[1]) value, keep existing fact
          intact. Mark conflict resolved.
        - ``stale``: Mark the existing fact as stale and apply the new
          candidate's value as a new version.

        Returns a dict with conflict entry and optionally the applied fact.
        """
        # H3: Read all unresolved conflicts for this key (not just first one)
        conflicts = self.review_queue.list_conflicts(workspace_id, unresolved_only=False)
        unresolved = [
            c for c in conflicts if not c.get("resolved", False) and c.get("key") == fact_key
        ]
        if not unresolved:
            return {"key": fact_key, "resolved": False, "error": "conflict_not_found"}

        conflict_entry = unresolved[0]
        candidates = conflict_entry["candidates"]

        # H2: Validate candidate_index bounds for canonical choice
        if choice == "canonical":
            if candidate_index is None or candidate_index < 0 or candidate_index >= len(candidates):
                return {
                    "key": fact_key,
                    "resolved": False,
                    "error": "INVALID_CANDIDATE_INDEX",
                    "candidate_count": len(candidates),
                }

        # Step 2: Mark ALL unresolved conflicts for this key as resolved
        resolved_entries: list[dict[str, Any]] = []
        for _entry in unresolved:
            resolved_entries.append(
                self.review_queue.resolve_conflict(workspace_id, fact_key, choice, candidate_index)
            )

        # Step 3: Apply the resolution by writing a new fact version
        existing = self.get_fact(workspace_id, fact_key)
        applied_fact: KnowledgeFact | None = None
        if choice == "canonical":
            winner = candidates[candidate_index]
            new_value: dict[str, Any] = winner["value"]
            new_source = (
                KnowledgeSource(**winner["source"]) if winner.get("source") else KnowledgeSource()
            )
            new_confidence = winner.get("confidence")
            applied_fact = self._apply_conflict_write(
                workspace_id,
                fact_key,
                existing,
                new_value,
                new_source,
                new_confidence,
                fact_status="active",
            )
        elif choice == "stale" and existing is not None:
            # Write the new value (candidates[1]) as replacement, mark existing stale
            new_value = candidates[1]["value"]
            new_source = (
                KnowledgeSource(**candidates[1]["source"])
                if candidates[1].get("source")
                else KnowledgeSource()
            )
            new_confidence = candidates[1].get("confidence")
            # Unlike `canonical`, stale resolution first tags old fact as
            # conflicted, then writes the new value as the active version.
            now = datetime.now(tz=UTC)
            new_version = existing.version + 1
            stale_fact = KnowledgeFact(
                workspace_id=workspace_id,
                category=existing.category,
                key=existing.key,
                value=existing.value,
                source=existing.source,
                provenance=existing.provenance,
                confidence=existing.confidence,
                visibility=existing.visibility,
                valid_from=existing.valid_from,
                valid_until=existing.valid_until,
                created_at=existing.created_at,
                updated_at=now,
                version=new_version,
                status="conflicted",
            )
            self._append_history(workspace_id, fact=stale_fact)
            # Then write the new value as active
            applied_fact = self._apply_conflict_write(
                workspace_id,
                fact_key,
                stale_fact,
                new_value,
                new_source,
                new_confidence,
                fact_status="active",
            )
        elif choice == "reject":
            # Keep existing fact, no write needed — conflict just marked resolved
            pass

        result = dict(resolved_entries[0]) if resolved_entries else {}
        if applied_fact is not None:
            result["fact"] = applied_fact.model_dump()
        return result

    def _apply_conflict_write(
        self,
        workspace_id: str,
        fact_key: str,
        existing: KnowledgeFact | None,
        value: dict[str, Any],
        source: KnowledgeSource,
        confidence: float | None,
        *,
        fact_status: str = "active",
    ) -> KnowledgeFact:
        """Write a new fact version as part of conflict resolution.

        This bypasses conflict detection to avoid re-triggering conflicts.
        """
        now = datetime.now(tz=UTC)
        new_version = (existing.version + 1) if existing else 1
        fact = KnowledgeFact(
            workspace_id=workspace_id,
            category=(existing.category if existing else "general"),
            key=fact_key,
            value=value,
            source=source,
            provenance=existing.provenance if existing else [],
            confidence=confidence,
            visibility=existing.visibility if existing else "workspace",
            valid_from=existing.valid_from if existing else None,
            valid_until=existing.valid_until if existing else None,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            version=new_version,
            status=fact_status,  # type: ignore[arg-type]
        )
        self._append_history(workspace_id, fact=fact)

        # Update index
        ws_lock = self._get_workspace_lock(workspace_id)
        with ws_lock:
            index = self._read_index(workspace_id)
            hist_path = self._history_path(workspace_id, fact_key)
            index[fact_key] = {
                "path": str(hist_path.relative_to(self._workspace_facts_path(workspace_id)))
                if hist_path.exists()
                else "",
                "version": new_version,
                "updated_at": now.isoformat(),
                "category": fact.category,
            }
            self._write_index(workspace_id, index)
        return fact

    # ── Latest entry helper ────────────────────────────────────────────────

    def _latest_entry(self, workspace_id: str, fact_key: str) -> KnowledgeFact | None:
        """Read the most recent version from the JSONL history file directly.

        Skips tombstoned (status="deleted") entries — returns the latest
        non-deleted entry, or None if all entries are deleted or the file
        doesn't exist.
        """
        hist_path = self._history_path(workspace_id, fact_key)
        if not hist_path.exists():
            return None
        try:
            lines = hist_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = KnowledgeFact(**json.loads(line))
                if entry.status != "deleted":
                    return entry
            except (json.JSONDecodeError, Exception):
                continue
        return None

    # ── Startup integrity ─────────────────────────────────────────────────

    def _read_history_from_path(self, path: Path) -> list[KnowledgeFact]:
        """Read KnowledgeFacts directly from a given JSONL path.

        Used during index rebuild where we don't have the original fact_key.
        """
        if not path.exists():
            return []
        return self._parse_jsonl(path)

    def _integrity_check(self, workspace_id: str) -> dict[str, Any]:
        """Validate and return the index dict for a workspace.

        - If index.json is missing: creates it via _scan_or_build_index,
          logs a warning ``workspace_facts_index_missing``, returns the
          rebuilt index.
        - If index.json is corrupt (not valid JSON or wrong shape): logs
          an error, starts with an empty index for that workspace, and
          returns an empty dict so subsequent queries include a degraded
          signal rather than blocking the service.
        """
        idx_path = self._index_path(workspace_id)

        if not idx_path.exists():
            ws_dir = self._workspace_facts_path(workspace_id)
            if ws_dir.exists():
                logger.warning(
                    "index.json missing for workspace %s — rebuilding from history", workspace_id
                )
            else:
                logger.info("No workspace directory for %s — creating empty index", workspace_id)
                self._ensure_workspace(workspace_id)
            self._scan_or_build_index(workspace_id)
            return self._read_index(workspace_id)

        try:
            text = idx_path.read_text(encoding="utf-8")
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError as e:
            logger.error(
                "Corrupt index.json for workspace %s: %s — starting with empty facts",
                workspace_id,
                e,
            )
        except OSError as e:
            logger.error(
                "Failed to read index.json for workspace %s: %s — starting with empty facts",
                workspace_id,
                e,
            )
        return {}

    def _scan_history_files(self, workspace_id: str) -> tuple[dict[str, Any], int]:
        """Rebuild the index from JSONL history files.

        Reads every ``.jsonl`` file in ``facts/history/``, takes the last
        valid entry per fact key, and returns a fresh index dict.

        Returns ``(index, recovery_count)`` where ``recovery_count`` is the
        number of unique fact keys recovered from history files that were
        not present in the index before rebuilding (used for a warning log).
        """
        history_dir = self._workspace_facts_path(workspace_id) / "history"
        rebuilt: dict[str, Any] = {}
        recovery_count = 0

        if not history_dir.exists():
            return rebuilt, 0

        for jsonl_path in sorted(history_dir.glob("*.jsonl")):
            entries = self._read_history_from_path(jsonl_path)
            if not entries:
                continue
            latest = entries[-1]
            # Skip tombstoned entries — deleted facts should not reappear
            # in the index after an index rebuild, keeping consistent with
            # delete_fact semantics.
            if latest.status == "deleted":
                continue
            key = latest.key
            new_version = latest.version
            if key not in rebuilt:
                recovery_count += 1
            rebuilt[key] = {
                "path": str(jsonl_path.relative_to(self._workspace_facts_path(workspace_id))),
                "version": new_version,
                "updated_at": latest.updated_at.isoformat(),
                "category": latest.category,
            }

        return rebuilt, recovery_count

    def _scan_or_build_index(self, workspace_id: str) -> None:
        """Rebuild the index from history files if index is missing.

        Called at startup when index.json is missing but the workspace
        directory exists. If history files are found, they are used to
        reconstruct the index.
        """
        rebuilt, recovery_count = self._scan_history_files(workspace_id)
        if recovery_count > 0:
            logger.warning(
                "workspace_facts_index_missing: rebuilt index for workspace %s from %d history entries",
                workspace_id,
                recovery_count,
            )
        if not rebuilt:
            logger.info("No history found for workspace %s — wrote empty index", workspace_id)
        self._write_index(workspace_id, rebuilt)

    # ── Internal ───────────────────────────────────────────────────────────

    def _put_fact_internal(
        self,
        workspace_id: str,
        fact_key: str,
        request: KnowledgeFactWriteRequest,
        category: str,
        *,
        _known_conflicts: set[str] | None = None,
    ) -> KnowledgeFactWriteResponse:
        """Core write logic, invoked under the per-fact lock.

        Conflict detection:
        - If ``expected_previous_version`` is set and mismatches →
          returns ``conflict_detected`` with candidate summary.
        - If no explicit version check but values differ for the same key,
          records a conflict in the review queue and tags the fact
          ``status="conflicted"``.
        - ``honcho_conclusion`` sources default to ``pending_review``.
        """
        lock = self._get_fact_lock(workspace_id, fact_key)
        with lock:
            # Read existing for optimistic concurrency
            existing = self.get_fact(workspace_id, fact_key)

            # ── Version-based conflict detection ───────────────────────────
            if existing is not None and request.expected_previous_version is not None:
                if existing.version != request.expected_previous_version:
                    if _known_conflicts is not None and fact_key in _known_conflicts:
                        # Skip duplicate conflict within batch
                        pass  # fall through to normal write below
                    else:
                        conflict = KnowledgeConflict(
                            key=fact_key,
                            workspace_id=workspace_id,
                            candidates=[
                                {
                                    "value": existing.value,
                                    "source": existing.source.model_dump(),
                                    "confidence": existing.confidence,
                                    "version": existing.version,
                                },
                                {
                                    "value": request.value,
                                    "source": request.source.model_dump(),
                                    "confidence": request.confidence,
                                    "version": existing.version + 1,
                                },
                            ],
                            requires_review=True,
                        )
                        # Persist conflict entry
                        self.review_queue.add_conflict(workspace_id, fact_key, conflict)
                        if _known_conflicts is not None:
                            _known_conflicts.add(fact_key)
                        return KnowledgeFactWriteResponse(
                            key=fact_key,
                            status="conflict_detected",
                            conflict=conflict,
                        )

            # ── Timestamp-based concurrency check ──────────────────────────
            if existing is not None and request.expected_previous_updated_at is not None:
                if existing.updated_at != request.expected_previous_updated_at:
                    return KnowledgeFactWriteResponse(key=fact_key, status="stale_rejected")

            # ── Unchanged check ────────────────────────────────────────────
            if existing is not None and existing.value == request.value:
                return KnowledgeFactWriteResponse(key=fact_key, status="unchanged", fact=existing)

            # ── Value conflict detection (no explicit version check) ───────
            value_conflict = False
            if existing is not None and self._value_conflict_check(existing.value, request.value):
                if _known_conflicts is not None and fact_key in _known_conflicts:
                    value_conflict = True  # still tag the fact conflicted
                else:
                    value_conflict = True
                    conflict = KnowledgeConflict(
                        key=fact_key,
                        workspace_id=workspace_id,
                        candidates=[
                            {
                                "value": existing.value,
                                "source": existing.source.model_dump(),
                                "confidence": existing.confidence,
                                "version": existing.version,
                            },
                            {
                                "value": request.value,
                                "source": request.source.model_dump(),
                                "confidence": request.confidence,
                                "version": existing.version + 1,
                            },
                        ],
                        requires_review=True,
                    )
                    self.review_queue.add_conflict(workspace_id, fact_key, conflict)
                    if _known_conflicts is not None:
                        _known_conflicts.add(fact_key)

            # ── Determine fact status ──────────────────────────────────────
            fact_status: str = "active"
            if request.source.type == "honcho_conclusion":
                fact_status = "pending_review"
            if value_conflict:
                fact_status = "conflicted"

            # ── Write the new fact ─────────────────────────────────────────
            now = datetime.now(tz=UTC)
            new_version = (existing.version + 1) if existing else 1
            fact = KnowledgeFact(
                workspace_id=workspace_id,
                category=category,
                key=fact_key,
                value=request.value,
                source=request.source,
                provenance=request.provenance,
                confidence=request.confidence,
                visibility=request.visibility,
                valid_from=request.valid_from,
                valid_until=request.valid_until,
                created_at=existing.created_at if existing else now,
                updated_at=now,
                version=new_version,
                status=fact_status,  # type: ignore[arg-type]
            )

            # Append-only history
            self._append_history(workspace_id, fact=fact)

            # Update index
            ws_lock = self._get_workspace_lock(workspace_id)
            with ws_lock:
                index = self._read_index(workspace_id)
                hist_path = self._history_path(workspace_id, fact_key)
                index[fact_key] = {
                    "path": str(hist_path.relative_to(self._workspace_facts_path(workspace_id)))
                    if hist_path.exists()
                    else "",
                    "version": new_version,
                    "updated_at": now.isoformat(),
                    "category": category,
                }
                self._write_index(workspace_id, index)

            return KnowledgeFactWriteResponse(key=fact_key, status="written", fact=fact)

    @staticmethod
    def _value_conflict_check(old_value: Any, new_value: Any) -> bool:
        """Return True when two values are materially different.

        Uses simple structural comparison — dicts are compared over
        shared keys only (extraneous keys added per-source are ignored),
        lists are compared element-wise.
        """
        if type(old_value) is not type(new_value):
            return True
        if isinstance(old_value, dict):
            shared = set(old_value.keys()) & set(new_value.keys())
            for k in shared:
                if WorkspaceFactStore._value_conflict_check(old_value[k], new_value[k]):
                    return True
            return False
        if isinstance(old_value, (list, tuple)):
            if len(old_value) != len(new_value):
                return True
            for a, b in zip(old_value, new_value, strict=True):
                if a != b:
                    return True
            return False
        return bool(old_value != new_value)

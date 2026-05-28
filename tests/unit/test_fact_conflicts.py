"""Tests for fact conflict detection and review queue (Story HF.4).

Covers: version conflict detection, value conflict detection,
conflict storage and listing, resolution (canonical/reject/stale),
honcho_conclusion pending_review default, other source types default active.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from llm_wiki.knowledge.models import (
    KnowledgeConflict,
    KnowledgeFactWriteRequest,
    KnowledgeSource,
)


def _write_req(
    *,
    category: str = "workspace.roster",
    key: str = "test.key",
    value: dict,
    source_type: str = "manual_admin",
    expected_previous_version: int | None = None,
) -> KnowledgeFactWriteRequest:
    return KnowledgeFactWriteRequest(
        category=category,
        key=key,
        value=value,
        source=KnowledgeSource(type=source_type),
        expected_previous_version=expected_previous_version,
    )


def _store(temp_dir: Path):
    from llm_wiki.knowledge.storage import WorkspaceFactStore

    return WorkspaceFactStore(wiki_base=str(temp_dir))


# ═══════════════════════════════════════════════════════════
# Version conflict detection (AC: 1)
# ═══════════════════════════════════════════════════════════


class TestVersionConflictDetection:
    """When expected_previous_version doesn't match current, return conflict_detected."""

    @pytest.fixture
    def store(self, temp_dir: Path):
        return _store(temp_dir)

    def test_conflict_when_version_mismatches(self, store):
        ws = "ws-1"
        key = "schedule.time"

        # Write initial fact (version 1)
        r = store.put_fact(ws, _write_req(key=key, value={"time": "08:00"}))
        assert r.status == "written"
        assert r.fact.version == 1

        # Write again (version 2)
        r = store.put_fact(ws, _write_req(key=key, value={"time": "08:10"}))
        assert r.status == "written"

        # Try to write with stale expected version
        r = store.put_fact(
            ws,
            _write_req(
                key=key,
                value={"time": "08:30"},
                expected_previous_version=1,  # Current version is 2
            ),
        )
        assert r.status == "conflict_detected"
        assert r.conflict is not None
        assert r.conflict.key == key
        assert len(r.conflict.candidates) == 2

    def test_conflict_entry_persisted(self, store):
        """Conflict must be recorded in conflicts.jsonl."""
        ws = "ws-1"
        key = "schedule.time"

        store.put_fact(ws, _write_req(key=key, value={"time": "08:00"}))

        # Trigger conflict via version mismatch
        store.put_fact(
            ws,
            _write_req(
                key=key,
                value={"time": "08:10"},
                expected_previous_version=99,  # Guaranteed mismatch
            ),
        )

        # Check conflicts.jsonl exists and has entry
        conflicts = store.review_queue.list_conflicts(ws)
        assert len(conflicts) == 1
        assert not conflicts[0]["resolved"]
        assert conflicts[0]["key"] == key

    def test_no_conflict_when_version_matches(self, store):
        """Matching expected_previous_version → written, not conflict."""
        ws = "ws-1"
        key = "schedule.time"

        store.put_fact(ws, _write_req(key=key, value={"time": "08:00"}))

        r = store.put_fact(
            ws,
            _write_req(
                key=key,
                value={"time": "08:10"},
                expected_previous_version=1,
            ),
        )
        assert r.status == "written"
        assert r.fact.version == 2


# ═══════════════════════════════════════════════════════════
# Value conflict detection (AC: 2)
# ═══════════════════════════════════════════════════════════


class TestValueConflictDetection:
    """When values differ for the same key (no explicit version), record conflict."""

    @pytest.fixture
    def store(self, temp_dir: Path):
        return _store(temp_dir)

    def test_conflict_when_values_differ(self, store):
        """Write without expected_previous_version but with different value → conflict."""
        ws = "ws-1"
        key = "schedule.time"

        first = store.put_fact(ws, _write_req(key=key, value={"time": "08:00"}))
        assert first.status == "written"
        assert first.fact.status == "active"

        # Value conflict: different value for same key
        second = store.put_fact(ws, _write_req(key=key, value={"time": "08:15"}))
        assert second.status == "written"
        assert second.fact.status == "conflicted"

        conflicts = store.review_queue.list_conflicts(ws)
        assert len(conflicts) == 1

    def test_no_conflict_when_values_same(self, store):
        """Same value → unchanged, no conflict."""
        ws = "ws-1"
        key = "schedule.time"

        store.put_fact(ws, _write_req(key=key, value={"time": "08:00"}))
        r = store.put_fact(ws, _write_req(key=key, value={"time": "08:00"}))

        assert r.status == "unchanged"
        conflicts = store.review_queue.list_conflicts(ws)
        assert len(conflicts) == 0

    def test_conflict_different_type(self, store):
        """Different types count as conflict."""
        ws = "ws-1"
        key = "schedule.count"

        store.put_fact(ws, _write_req(key=key, value={"n": 5}))
        r = store.put_fact(ws, _write_req(key=key, value={"n": "five"}))

        assert r.fact.status == "conflicted"
        assert len(store.review_queue.list_conflicts(ws)) == 1


# ═══════════════════════════════════════════════════════════
# Conflict creation and storage (AC: 3)
# ═══════════════════════════════════════════════════════════


class TestConflictStorage:
    """Conflicts are persisted and retrievable."""

    @pytest.fixture
    def store(self, temp_dir: Path):
        return _store(temp_dir)

    def test_conflict_has_proper_shape(self, store):
        ws = "ws-1"
        key = "schedule.time"

        store.put_fact(ws, _write_req(key=key, value={"time": "08:00"}))
        store.put_fact(
            ws,
            _write_req(
                key=key,
                value={"time": "08:15"},
                expected_previous_version=0,
            ),
        )

        conflict = store.review_queue.list_conflicts(ws)[0]
        assert conflict["key"] == key
        assert conflict["workspace_id"] == ws
        assert len(conflict["candidates"]) == 2
        assert conflict["resolved"] is False
        assert "created_at" in conflict
        assert conflict["resolved_at"] is None

    def test_multiple_conflicts_ordered_by_timestamp(self, store):
        ws = "ws-1"
        key1 = "schedule.time"
        key2 = "schedule.door"

        store.put_fact(ws, _write_req(key=key1, value={"time": "08:00"}))
        store.put_fact(
            ws,
            _write_req(key=key1, value={"time": "09:00"}, expected_previous_version=0),
        )

        store.put_fact(ws, _write_req(key=key2, value={"door": "a"}))
        store.put_fact(
            ws,
            _write_req(key=key2, value={"door": "b"}, expected_previous_version=0),
        )

        conflicts = store.review_queue.list_conflicts(ws)
        assert len(conflicts) == 2
        # Most recent first
        assert conflicts[0]["key"] == key2


# ═══════════════════════════════════════════════════════════
# Conflict listing (AC: 4)
# ═══════════════════════════════════════════════════════════


class TestConflictListing:
    """Unresolved conflicts are listed, resolved ones excluded."""

    @pytest.fixture
    def store(self, temp_dir: Path):
        return _store(temp_dir)

    def test_list_unresolved_only_by_default(self, store):
        ws = "ws-1"
        key = "schedule.time"

        store.put_fact(ws, _write_req(key=key, value={"time": "08:00"}))
        store.put_fact(
            ws,
            _write_req(key=key, value={"time": "09:00"}, expected_previous_version=0),
        )

        all_conflicts = store.review_queue.list_conflicts(ws)
        assert len(all_conflicts) == 1

    def test_resolved_excluded_from_list(self, store):
        ws = "ws-1"
        key = "schedule.time"

        store.put_fact(ws, _write_req(key=key, value={"time": "08:00"}))
        store.put_fact(
            ws,
            _write_req(key=key, value={"time": "09:00"}, expected_previous_version=0),
        )

        store.review_queue.resolve_conflict(ws, key, "canonical", 0)

        unresolved = store.review_queue.list_conflicts(ws)
        assert len(unresolved) == 0

    def test_include_resolved_when_requested(self, store):
        ws = "ws-1"
        key = "schedule.time"

        store.put_fact(ws, _write_req(key=key, value={"time": "08:00"}))
        store.put_fact(
            ws,
            _write_req(key=key, value={"time": "09:00"}, expected_previous_version=0),
        )
        store.review_queue.resolve_conflict(ws, key, "canonical", 0)

        all_conflicts = store.review_queue.list_conflicts(ws, unresolved_only=False)
        assert len(all_conflicts) == 1


# ═══════════════════════════════════════════════════════════
# Resolution: canonical (AC: 6)
# ═══════════════════════════════════════════════════════════


class TestResolutionCanonical:
    """Choose the canonical candidate → write it as new version."""

    @pytest.fixture
    def store(self, temp_dir: Path):
        return _store(temp_dir)

    def test_canonical_resolution_marks_resolved(self, store):
        ws = "ws-1"
        key = "schedule.time"

        store.put_fact(ws, _write_req(key=key, value={"time": "08:00"}))
        store.put_fact(
            ws,
            _write_req(key=key, value={"time": "09:00"}, expected_previous_version=0),
        )

        result = store.review_queue.resolve_conflict(ws, key, "canonical", 1)
        assert result["resolved"] is True
        assert result["resolution_choice"] == "canonical"

        # Conflict no longer in unresolved list
        assert len(store.review_queue.list_conflicts(ws)) == 0


# ═══════════════════════════════════════════════════════════
# Resolution: reject (AC: 6)
# ═══════════════════════════════════════════════════════════


class TestResolutionReject:
    """Reject the new candidate, keep existing."""

    @pytest.fixture
    def store(self, temp_dir: Path):
        return _store(temp_dir)

    def test_reject_resolution_marks_resolved(self, store):
        ws = "ws-1"
        key = "schedule.time"

        store.put_fact(ws, _write_req(key=key, value={"time": "08:00"}))
        store.put_fact(
            ws,
            _write_req(key=key, value={"time": "09:00"}, expected_previous_version=0),
        )

        result = store.review_queue.resolve_conflict(ws, key, "reject")
        assert result["resolved"] is True
        assert result["resolution_choice"] == "reject"
        assert len(store.review_queue.list_conflicts(ws)) == 0


# ═══════════════════════════════════════════════════════════
# Resolution: stale (AC: 6)
# ═══════════════════════════════════════════════════════════


class TestResolutionStale:
    """Mark existing as stale, write the new value."""

    @pytest.fixture
    def store(self, temp_dir: Path):
        return _store(temp_dir)

    def test_stale_resolution_marks_resolved(self, store):
        ws = "ws-1"
        key = "schedule.time"

        store.put_fact(ws, _write_req(key=key, value={"time": "08:00"}))
        store.put_fact(
            ws,
            _write_req(key=key, value={"time": "09:00"}, expected_previous_version=0),
        )

        result = store.review_queue.resolve_conflict(ws, key, "stale")
        assert result["resolved"] is True
        assert result["resolution_choice"] == "stale"
        assert len(store.review_queue.list_conflicts(ws)) == 0


# ═══════════════════════════════════════════════════════════
# Honcho_conclusion defaults to pending_review (AC: 7)
# ═══════════════════════════════════════════════════════════


class TestHonchoConclusionPendingReview:
    """honcho_conclusion sources default to pending_review status."""

    @pytest.fixture
    def store(self, temp_dir: Path):
        return _store(temp_dir)

    def test_honcho_conclusion_defaults_to_pending_review(self, store):
        ws = "ws-1"
        key = "honcho.update"

        r = store.put_fact(
            ws,
            _write_req(key=key, value={"update": "new"}, source_type="honcho_conclusion"),
        )
        assert r.status == "written"
        assert r.fact.status == "pending_review"

    def test_non_honcho_defaults_to_active(self, store):
        ws = "ws-1"
        key = "manual.key"

        r = store.put_fact(
            ws,
            _write_req(key=key, value={"data": 1}, source_type="manual_admin"),
        )
        assert r.fact.status == "active"

    def test_google_calendar_defaults_to_active(self, store):
        ws = "ws-1"
        key = "calendar.event"

        r = store.put_fact(
            ws,
            _write_req(key=key, value={"event": "mtg"}, source_type="google_calendar"),
        )
        assert r.fact.status == "active"

    def test_home_assistant_defaults_to_active(self, store):
        ws = "ws-1"
        key = "home.sensor"

        r = store.put_fact(
            ws,
            _write_req(key=key, value={"temp": 72}, source_type="home_assistant"),
        )
        assert r.fact.status == "active"


# ═══════════════════════════════════════════════════════════
# KnowledgeConflict model
# ═══════════════════════════════════════════════════════════


class TestConflictModel:
    """Verify model shapes."""

    def test_conflict_defaults(self):
        c = KnowledgeConflict(key="k", candidates=[])
        assert c.requires_review is True
        assert c.resolved is False
        assert c.resolved_at is None
        assert c.resolution_choice is None

    def test_conflict_with_workspace(self):
        c = KnowledgeConflict(key="k", workspace_id="ws-1", candidates=[{}])
        assert c.workspace_id == "ws-1"

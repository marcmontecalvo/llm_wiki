"""Tests for WorkspaceFactStore storage layer (Story HF.2).

Covers: append-only history, atomic writes, per-fact locking,
startup integrity checks, and workspace directory initialization.
"""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest


def _write_req(category="workspace.roster", key="test.key", value=None, source_type="manual_admin"):
    """Helper to create a KnowledgeFactWriteRequest."""
    from llm_wiki.knowledge.models import KnowledgeFactWriteRequest

    return KnowledgeFactWriteRequest(
        category=category,
        key=key,
        value=value or {},
        source={"type": source_type},
    )


class TestAppendOnlyHistory:
    """Verify that fact history is truly append-only (AC: 2)."""

    @pytest.fixture
    def store(self, temp_dir: Path):
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        return WorkspaceFactStore(wiki_base=str(temp_dir))

    def test_append_only_history_returns_all_versions(self, store):
        ws = "house-1"
        key = "test.key"

        for v in range(1, 4):
            store.put_fact(ws, _write_req(key=key, value={"v": v}))

        history = store.get_history(ws, key)
        assert len(history) == 3
        assert history[0].version == 1
        assert history[1].version == 2
        assert history[2].version == 3

    def test_history_each_line_is_full_fact(self, store):
        """Each JSONL line must be a full KnowledgeFact, not a diff."""
        ws = "house-1"
        key = "test.jsonl"

        for i in range(3):
            store.put_fact(ws, _write_req(key=key, value={"i": i}))

        hist_path = store._history_path(ws, key)
        lines = [line for line in hist_path.read_text().splitlines() if line.strip()]
        assert len(lines) == 3
        for line in lines:
            data = json.loads(line)
            assert data["key"] == key
            assert "version" in data
            assert "workspace_id" in data

    def test_get_latest_returns_last_version(self, store):
        ws = "house-1"
        key = "test.latest"

        for i in range(3):
            store.put_fact(ws, _write_req(key=key, value={"i": i}))

        latest = store.get_fact(ws, key)
        assert latest.value == {"i": 2}
        assert latest.version == 3

    def test_latest_entry_method(self, store):
        """_latest_entry reads the last JSONL line directly."""
        ws = "house-1"
        key = "test.latest_entry"

        for i in range(3):
            store.put_fact(ws, _write_req(key=key, value={"i": i}))

        latest = store._latest_entry(ws, key)
        assert latest is not None
        assert latest.version == 3
        assert latest.value == {"i": 2}

    def test_latest_entry_returns_none_for_missing(self, store):
        assert store._latest_entry("missing", "missing.key") is None


class TestAtomicWrite:
    """Verify temp file + os.replace atomic write pattern (AC: 3)."""

    @pytest.fixture
    def store(self, temp_dir: Path):
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        return WorkspaceFactStore(wiki_base=str(temp_dir))

    def test_atomic_write_preserves_old_data_on_failure(self, temp_dir: Path):
        """If os.replace fails, old data should be preserved."""
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        store = WorkspaceFactStore(wiki_base=str(temp_dir))
        ws = "house-1"
        key = "test.atomic_fail"

        # Write initial data
        store.put_fact(ws, _write_req(key=key, value={"v": "original"}))

        # Now mock os.replace to raise an error
        def failing_replace(*args, **kwargs):
            raise OSError("Simulated disk error")

        with patch("os.replace", failing_replace):
            with pytest.raises(OSError):
                store.put_fact(ws, _write_req(key=key, value={"v": "corrupting"}))

        # Original data should still be intact
        fact = store.get_fact(ws, key)
        assert fact is not None
        assert fact.value == {"v": "original"}


class TestPerFactLocking:
    """Verify per-fact locking prevents data races (AC: 4)."""

    @pytest.fixture
    def store(self, temp_dir: Path):
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        return WorkspaceFactStore(wiki_base=str(temp_dir))

    def test_concurrent_writes_same_key_monotonic_version(self, store):
        """Concurrent writes to the same key must produce monotonic versions."""
        ws = "house-1"
        key = "test.concurrent"
        lock = threading.Lock()
        results: list[int] = []

        def write_version(n: int):
            resp = store.put_fact(ws, _write_req(key=key, value={"worker": n}))
            with lock:
                results.append(resp.fact.version if resp.fact else None)

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(write_version, i) for i in range(20)]
            for f in futures:
                f.exception(timeout=5)
                f.result()

        results.sort()
        expected = list(range(1, 21))
        assert results == expected, f"Expected monotonic versions {expected}, got {results}"

    def test_concurrent_writes_different_keys_parallel(self, store):
        """Concurrent writes to different keys should not block each other."""
        ws = "house-1"
        completed: list[int] = []
        barrier = threading.Barrier(5)

        def write_key(n: int):
            barrier.wait(timeout=10)
            store.put_fact(ws, _write_req(key=f"parallel.key.{n}", value={"n": n}))
            with threading.Lock():
                completed.append(n)

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(write_key, i) for i in range(5)]
            for f in futures:
                f.result()

        assert len(completed) == 5

    def test_lock_released_on_exception(self, store):
        """Per-fact lock is released even if write raises."""
        ws = "house-1"
        key = "test.lock_release"
        from unittest.mock import patch

        # First write succeeds
        store.put_fact(ws, _write_req(key=key, value={"v": 1}))

        # Force a failure on the index write — the lock in _put_fact_internal
        # is acquired before the history write, and the index write happens
        # in _put_fact_internal under the same lock. When _atomic_json fails,
        # the lock context manager must release.
        original_atomic_json = store._atomic_json

        def fail_atomic_json(path, data):
            if path.name == "index.json":
                raise OSError("index write failed")
            return original_atomic_json(path, data)

        with patch.object(store, "_atomic_json", fail_atomic_json):
            with pytest.raises((OSError, IndexError)):
                store.put_fact(ws, _write_req(key=key, value={"v": 2}))

        # Lock must be released — a subsequent write should not deadlock
        store.put_fact(ws, _write_req(key=key, value={"v": 3}))
        fact = store.get_fact(ws, key)
        assert fact is not None


class TestStartupIntegrity:
    """Verify startup integrity checks (AC: 5)."""

    @pytest.fixture
    def store(self, temp_dir: Path):
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        return WorkspaceFactStore(wiki_base=str(temp_dir))

    def test_corrupt_index_no_crash(self, store):
        """Corrupt index.json should not crash — graceful degradation."""
        ws = "house-1"
        for i in range(3):
            store.put_fact(ws, _write_req(key=f"fact.{i}", value={"i": i}))

        # Corrupt the index
        idx_path = store._index_path(ws)
        idx_path.write_text("not valid json {{{")

        # _integrity_check should not crash
        result = store._integrity_check(ws)
        assert result == {}

        # Facts should still be readable from history
        fact = store.get_fact(ws, "fact.0")
        assert fact is not None
        assert fact.value == {"i": 0}

    def test_missing_index_rebuilds_from_history(self, store):
        """Missing index.json → rebuilds from history files."""
        ws = "house-1"
        for i in range(5):
            store.put_fact(ws, _write_req(key=f"fact.{i}", value={"i": i}))

        # Delete index
        store._index_path(ws).unlink()

        # Trigger rebuild via integrity check
        result = store._integrity_check(ws)
        assert isinstance(result, dict)
        assert "fact.0" in result
        assert "fact.4" in result

    def test_missing_index_logs_warning(self, store, caplog):
        """Missing index should log recovery warning."""
        ws = "house-1"
        for i in range(2):
            store.put_fact(ws, _write_req(key=f"fact.{i}", value={"i": i}))
        store._index_path(ws).unlink()

        store._integrity_check(ws)

        assert any(
            "workspace_facts_index_missing" in record.message
            or "index.json missing" in record.message
            for record in caplog.records
        )

    def test_missing_index_first_boot_no_crash(self, temp_dir: Path):
        """New workspace (no directory at all) → no crash, empty index written."""
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        store = WorkspaceFactStore(wiki_base=str(temp_dir))
        ws = "brand-new"

        # No ensure_workspace called — directory doesn't exist, no facts subpath
        result = store._integrity_check(ws)
        assert isinstance(result, dict)
        assert result == {}
        # index.json was created (empty)
        assert store._index_path(ws).exists()

    def test_scan_history_files_returns_recovery_count(self, store):
        """_scan_history_files returns index + count of recovered entries."""
        ws = "house-1"
        for i in range(3):
            store.put_fact(ws, _write_req(key=f"fact.{i}", value={"i": i}))
        store._index_path(ws).unlink()

        rebuilt, count = store._scan_history_files(ws)
        assert len(rebuilt) == 3
        assert count == 3

    def test_scan_history_files_omits_deleted_facts(self, store):
        """Deleted facts should not reappear in rebuilt index."""
        ws = "house-1"
        for i in range(3):
            store.put_fact(ws, _write_req(key=f"fact.{i}", value={"i": i}))

        # Delete one fact (writes a tombstone)
        store.delete_fact(ws, "fact.1")

        # Rebuild index from history
        rebuilt, count = store._scan_history_files(ws)

        assert "fact.0" in rebuilt
        assert "fact.1" not in rebuilt, "Deleted fact must not reappear after rebuild"
        assert "fact.2" in rebuilt

    def test_missing_index_rebuilds_deleted_tombstone(self, store):
        """After a full rebuild with missing index, deleted facts stay deleted."""
        ws = "house-1"
        for i in range(3):
            store.put_fact(ws, _write_req(key=f"fact.{i}", value={"i": i}))
        store.delete_fact(ws, "fact.1")
        store._index_path(ws).unlink()

        store._integrity_check(ws)
        assert store.get_fact(ws, "fact.0") is not None
        assert store.get_fact(ws, "fact.1") is None, (
            "Deleted fact should not reappear after restart"
        )
        assert store.get_fact(ws, "fact.2") is not None

    def test_scan_history_files_empty_dir(self, store):
        """No history files → empty result."""
        ws = "house-1"
        rebuilt, count = store._scan_history_files(ws)
        assert rebuilt == {}
        assert count == 0

    def test_scan_or_build_writes_empty_index_when_no_history(self, store):
        """No history → writes empty index rather than leaving perpetual missing."""
        ws = "empty-ws"

        store._ensure_workspace(ws)
        store._scan_or_build_index(ws)

        idx = store._integrity_check(ws)
        assert isinstance(idx, dict)


class TestWorkspaceDirectoryInit:
    """Verify workspace directory initialization (AC: 5)."""

    @pytest.fixture
    def store(self, temp_dir: Path):
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        return WorkspaceFactStore(wiki_base=str(temp_dir))

    def test_init_creates_directory_structure(self, store):
        """ensure_workspace creates facts/, categories/, history/."""
        ws = "new-ws"
        store._ensure_workspace(ws)

        facts_dir = store._workspace_facts_path(ws)
        assert facts_dir.exists()
        assert (facts_dir / "categories").exists()
        assert (facts_dir / "history").exists()

    def test_init_is_idempotent(self, store):
        """Double init must not error or overwrite."""
        ws = "new-ws"
        store._ensure_workspace(ws)
        store._ensure_workspace(ws)

        facts_dir = store._workspace_facts_path(ws)
        assert facts_dir.exists()
        assert (facts_dir / "categories").exists()
        assert (facts_dir / "history").exists()

    def test_idempotency_preserves_existing_data(self, temp_dir: Path):
        """Double init preserves existing fact data."""
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        store = WorkspaceFactStore(wiki_base=str(temp_dir))
        ws = "data-ws"

        store.put_fact(ws, _write_req(key="existing.key", value={"preserved": True}))

        # Re-init should not overwrite
        store._ensure_workspace(ws)

        fact = store.get_fact(ws, "existing.key")
        assert fact is not None
        assert fact.value == {"preserved": True}

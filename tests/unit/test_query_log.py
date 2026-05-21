"""Tests for Story 1.12: SQLite Query Log (QueryLogStore)."""

import json
import sqlite3
from pathlib import Path

from llm_wiki.query.log import (
    QueryLogEntry,
    QueryLogStore,
    compute_query_hash,
)


class TestComputeQueryHash:
    """Tests for query hash computation."""

    def test_is_deterministic(self):
        h1 = compute_query_hash("  WHAT IS PYTHON  ")
        h2 = compute_query_hash("what is python")
        assert h1 == h2

    def test_lowercases_and_strips(self):
        assert compute_query_hash("Test") == compute_query_hash("test")
        assert compute_query_hash(" test ") == compute_query_hash("test")

    def test_returns_fixed_length_hex(self):
        h = compute_query_hash("anything")
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)


class TestQueryLogStore:
    """Tests for QueryLogStore."""

    def test_creates_db_on_first_write(self, temp_dir: Path):
        QueryLogStore(temp_dir / "query_log.db")
        assert (temp_dir / "query_log.db").exists()

    def test_creates_schema(self, temp_dir: Path):
        QueryLogStore(temp_dir / "query_log.db")
        with sqlite3.connect(temp_dir / "query_log.db") as conn:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = {t[0] for t in tables}
        assert "queries" in table_names

    def test_creates_composite_index(self, temp_dir: Path):
        QueryLogStore(temp_dir / "query_log.db")
        with sqlite3.connect(temp_dir / "query_log.db") as conn:
            indexes = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        index_names = {i[0] for i in indexes}
        assert "idx_query_hash_timestamp" in index_names

    def test_log_append_and_stats(self, temp_dir: Path):
        store = QueryLogStore(temp_dir / "query_log.db")
        entry = QueryLogEntry(
            query_text="what is python", depth="quick", domains=[], result_count=5
        )
        store.log(entry)
        store.log(entry)  # same query twice
        stats = store.stats()
        assert stats["total_rows"] == 2
        assert stats["top_queries"][0]["hits"] == 2

    def test_log_failure_does_not_raise(self, temp_dir: Path):
        bad_store = QueryLogStore(temp_dir / "query_log.db")
        # Override path to simulate disk failure
        bad_store.db_path = Path("/nonexistent/path/query_log.db")
        bad_store.log(
            QueryLogEntry(query_text="q", depth="quick", domains=[], result_count=0)
        )  # Should not raise

    def test_identical_hashes_for_same_query(self, temp_dir: Path):
        store = QueryLogStore(temp_dir / "query_log.db")
        e1 = QueryLogEntry(query_text="what is python", depth="quick", domains=[], result_count=1)
        e2 = QueryLogEntry(
            query_text="what is python", depth="deep", domains=["python"], result_count=2
        )
        store.log(e1)
        store.log(e2)
        with sqlite3.connect(temp_dir / "query_log.db") as conn:
            hashes = conn.execute("SELECT DISTINCT query_hash FROM queries").fetchall()
        assert len(hashes) == 1

    def test_domains_stored_as_json(self, temp_dir: Path):
        store = QueryLogStore(temp_dir / "query_log.db")
        store.log(
            QueryLogEntry(query_text="q", depth="quick", domains=["python", "ai"], result_count=1)
        )
        with sqlite3.connect(temp_dir / "query_log.db") as conn:
            row = conn.execute("SELECT domains FROM queries").fetchone()
        assert json.loads(row[0]) == ["python", "ai"]

    def test_stats_row_count(self, temp_dir: Path):
        store = QueryLogStore(temp_dir / "query_log.db")
        store.log(QueryLogEntry(query_text="a", depth="quick", domains=[], result_count=1))
        store.log(QueryLogEntry(query_text="b", depth="deep", domains=[], result_count=3))
        stats = store.stats()
        assert stats["total_rows"] == 2

    def test_stats_oldest_entry(self, temp_dir: Path):
        store = QueryLogStore(temp_dir / "query_log.db")
        store.log(QueryLogEntry(query_text="a", depth="quick", domains=[], result_count=1))
        stats = store.stats()
        assert stats["oldest_entry"] is not None

    def test_stats_top_queries_fewest(self, temp_dir: Path):
        store = QueryLogStore(temp_dir / "query_log.db")
        stats = store.stats()
        assert stats["total_rows"] == 0
        assert stats["top_queries"] == []

    def test_prune_removes_old_rows(self, temp_dir: Path):
        store = QueryLogStore(temp_dir / "query_log.db")
        with sqlite3.connect(temp_dir / "query_log.db") as conn:
            conn.execute(
                "INSERT INTO queries (query_hash, query_text, depth, domains, result_count, confidence_avg, timestamp) "
                "VALUES ('hash', 'old query', 'quick', '[]', 0, null, '2020-01-01T00:00:00')"
            )
        deleted = store.prune(retention_days=1)
        assert deleted == 1

    def test_prune_keeps_recent_rows(self, temp_dir: Path):
        store = QueryLogStore(temp_dir / "query_log.db")
        store.log(QueryLogEntry(query_text="recent", depth="quick", domains=[], result_count=1))
        deleted = store.prune(retention_days=1)
        assert deleted == 0

    def test_stats_error_returns_error_dict(self, temp_dir: Path):
        store = QueryLogStore(temp_dir / "query_log.db")
        store.db_path = Path("/nonexistent/path/stats.db")
        # Must not crash for write path
        store.log(QueryLogEntry(query_text="q", depth="quick", domains=[], result_count=0))
        stats = store.stats()
        assert "error" in stats

    def test_prune_error_returns_zero(self, temp_dir: Path):
        store = QueryLogStore(temp_dir / "query_log.db")
        store.db_path = Path("/nonexistent/path/prune.db")
        deleted = store.prune(retention_days=1)
        assert deleted == 0

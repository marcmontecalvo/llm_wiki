"""SQLite-backed query log for tracking recurring queries.

Created by Story 1.12 (SQLite Query Log).
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS queries (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    query_hash     TEXT NOT NULL,
    query_text     TEXT NOT NULL,
    depth          TEXT NOT NULL,
    domains        TEXT NOT NULL,
    result_count   INTEGER NOT NULL,
    confidence_avg REAL,
    timestamp      TEXT NOT NULL
)
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_query_hash_timestamp
ON queries (query_hash, timestamp)
"""


def compute_query_hash(text: str) -> str:
    """Deterministic hash of normalized query text."""
    normalized = text.lower().strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


@dataclass
class QueryLogEntry:
    """A single query log entry."""

    query_text: str
    depth: str
    domains: list[str]
    result_count: int
    confidence_avg: float | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def query_hash(self) -> str:
        return compute_query_hash(self.query_text)


class QueryLogStore:
    """Append-only SQLite store for query log entries."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create table and index if they don't exist. Called once on init."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.execute(CREATE_TABLE_SQL)
            conn.execute(CREATE_INDEX_SQL)

    def log(self, entry: QueryLogEntry) -> None:
        """Append a row. Never raises — exceptions are logged."""
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                conn.execute(
                    """INSERT INTO queries
                       (query_hash, query_text, depth, domains, result_count, confidence_avg, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        entry.query_hash,
                        entry.query_text,
                        entry.depth,
                        json.dumps(entry.domains),
                        entry.result_count,
                        entry.confidence_avg,
                        entry.timestamp.isoformat(),
                    ),
                )
        except Exception as e:
            logger.error("Failed to log query: %s", e)
            try:
                from llm_wiki.observability.metrics import (
                    query_log_write_failures_counter,
                )

                query_log_write_failures_counter.add(1)
            except Exception:
                pass  # Never let metrics failures propagate

    def stats(self) -> dict:
        """Return row count, oldest entry, top 10 repeated queries."""
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                count = conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
                oldest = conn.execute("SELECT MIN(timestamp) FROM queries").fetchone()[0]
                top_queries = conn.execute(
                    """SELECT query_text, COUNT(*) as hits
                       FROM queries
                       GROUP BY query_hash
                       ORDER BY hits DESC
                       LIMIT 10"""
                ).fetchall()
            return {
                "total_rows": count,
                "oldest_entry": oldest,
                "top_queries": [{"query": q, "hits": h} for q, h in top_queries],
            }
        except Exception as e:
            logger.error("Failed to get query log stats: %s", e)
            return {"error": str(e)}

    def prune(self, retention_days: int = 90) -> int:
        """Delete rows older than retention_days. Returns number deleted."""
        cutoff = (datetime.utcnow() - timedelta(days=retention_days)).isoformat()
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                cursor = conn.execute("DELETE FROM queries WHERE timestamp < ?", (cutoff,))
                return cursor.rowcount
        except Exception as e:
            logger.error("Failed to prune query log: %s", e)
            return 0

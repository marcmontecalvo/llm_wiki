# Story 1.12: SQLite Query Log

Status: done

## Story

As an operator and future synthesis cache (Epic 3),
I want every query logged to a SQLite database with its result metadata and a defined retention policy,
so that repeated high-value queries can be identified and cached as wiki pages, operators can audit query patterns, and the log does not grow unbounded.

**Can be worked in parallel with Story 1.7** — the query log integration in Story 1.7 depends on this story's `QueryLogStore` class.

## Acceptance Criteria

1. **Given** any query is executed via MCP, REST, or CLI **When** it completes **Then** a row is appended to `wiki_system/state/query_log.db` with columns: `query_hash`, `query_text`, `depth`, `domains` (JSON array), `result_count`, `confidence_avg`, `timestamp` (FR63).

2. **Given** the query log write **When** executed in an async route **Then** it runs inside `asyncio.to_thread()` and the SQLite connection uses `check_same_thread=False`.

3. **Given** `query_log.db` does not yet exist **When** the first query is logged **Then** the database file and schema are created automatically — no manual migration step required.

4. **Given** the `query_log.db` schema **When** created **Then** it has a composite index on `(query_hash, timestamp)` to support efficient repeated-query analysis at scale.

5. **Given** the same query text is submitted multiple times **When** logged **Then** all rows share the same `query_hash` — computed as a deterministic hash of normalized (lowercased, stripped) query text.

6. **Given** the query log write fails (e.g., disk full) **When** the error occurs **Then** the exception is caught, logged to stderr, and the query response is still returned to the caller — logging never blocks or fails the query.

7. **Given** the daemon's governance sweep runs **When** it executes **Then** it deletes query log rows older than 90 days (default `synthesis_cache_log_retention_days` in `daemon.yaml`).

8. **Given** `llm-wiki govern query-log --stats [--json]` **When** run **Then** it prints row count, oldest entry date, and top 10 most-repeated queries with hit counts.

## Tasks / Subtasks

- [x] Create `src/llm_wiki/query/log.py` — `QueryLogStore` class (AC: 1, 2, 3, 4, 5, 6)
  - [x] `QueryLogEntry` dataclass: `query_hash, query_text, depth, domains, result_count, confidence_avg, timestamp`
  - [x] `QueryLogStore.__init__(db_path: Path)` — creates DB file and runs `_ensure_schema()` once on init
  - [x] `QueryLogStore._ensure_schema()` — creates table + index if not exists; called only from `__init__`
  - [x] `QueryLogStore.log(entry: QueryLogEntry)` — appends row; catches + logs all exceptions
  - [x] `QueryLogStore.stats() -> dict` — row count, oldest entry, top 10 repeated queries
  - [x] `QueryLogStore.prune(retention_days: int)` — deletes rows older than retention window
  - [x] `compute_query_hash(text: str) -> str` — normalize (lowercase, strip) then SHA256 hex
- [x] Store `QueryLogStore` singleton on `app.state` in FastAPI lifespan (AC: 2)
  - [x] In `src/llm_wiki/api/app.py` lifespan: `app.state.query_log = QueryLogStore(wiki_root / "wiki_system" / "state" / "query_log.db")`
  - [x] Schema is checked exactly once at startup — never per-request
  - [x] Routes access it via `request.app.state.query_log` — never instantiate `QueryLogStore` inside a route
- [x] Add `synthesis_cache_log_retention_days: int = 90` to `DaemonConfig` in `models/config.py` (AC: 7)
- [x] Wire `QueryLogStore.prune()` into `GovernanceJob` (AC: 7)
  - [x] `src/llm_wiki/daemon/jobs/governance.py` — call `store.prune(retention_days)` during governance sweep
- [x] Add `govern query-log --stats [--json]` CLI command (AC: 8)
  - [x] In `src/llm_wiki/cli.py` under the `govern` group
  - [x] Delegate to `QueryLogStore.stats()`
- [x] Write tests

## Dev Notes

### SQLite Schema and Index

```python
# src/llm_wiki/query/log.py
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS queries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    query_hash  TEXT NOT NULL,
    query_text  TEXT NOT NULL,
    depth       TEXT NOT NULL,
    domains     TEXT NOT NULL,  -- JSON array
    result_count INTEGER NOT NULL,
    confidence_avg REAL,
    timestamp   TEXT NOT NULL   -- ISO8601
)
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_query_hash_timestamp
ON queries (query_hash, timestamp)
"""
```

### SQLite Connection Pattern

```python
import sqlite3
import json
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def compute_query_hash(text: str) -> str:
    """Deterministic hash of normalized query text."""
    normalized = text.lower().strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


@dataclass
class QueryLogEntry:
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
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create DB and schema if not exists. Called on init."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: log() is called from asyncio.to_thread() workers
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.execute(CREATE_TABLE_SQL)
            conn.execute(CREATE_INDEX_SQL)

    def log(self, entry: QueryLogEntry) -> None:
        """Append a query log row. Never raises — exceptions are logged."""
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

    def stats(self) -> dict:
        """Return row count, oldest entry, top 10 repeated queries."""
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                count = conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
                oldest = conn.execute(
                    "SELECT MIN(timestamp) FROM queries"
                ).fetchone()[0]
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
                cursor = conn.execute(
                    "DELETE FROM queries WHERE timestamp < ?", (cutoff,)
                )
                return cursor.rowcount
        except Exception as e:
            logger.error("Failed to prune query log: %s", e)
            return 0
```

### Integration in Query Routes (Story 1.7 Hook)

`QueryLogStore` is on `app.state.query_log` — instantiated once in the lifespan, schema checked once. Routes access it directly; never instantiate inside a route.

```python
# In src/llm_wiki/api/routers/query.py — after getting results
try:
    entry = QueryLogEntry(
        query_text=req.query,
        depth=req.depth,
        domains=[req.domain] if req.domain else [],
        result_count=len(results),
        confidence_avg=sum(r.confidence for r in results) / len(results) if results else None,
    )
    await asyncio.to_thread(request.app.state.query_log.log, entry)
except Exception:
    pass  # Never block query response on log failure (AC: 6)
```

### GovernanceJob Prune Hook

```python
# src/llm_wiki/daemon/jobs/governance.py — add to governance sweep
from llm_wiki.query.log import QueryLogStore

def _prune_query_log(wiki_base: Path, retention_days: int) -> int:
    store = QueryLogStore(wiki_base / "state" / "query_log.db")
    deleted = store.prune(retention_days)
    if deleted:
        logger.info("Pruned %d old query log rows", deleted)
    return deleted
```

### CLI Command

```python
# src/llm_wiki/cli.py — under @govern.command("query-log")
@govern.command("query-log")
@click.option("--json", "output_json", is_flag=True, help="Emit machine-parseable JSON")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
)
def govern_query_log(output_json: bool, wiki_base: Path):
    """Show query log statistics."""
    from llm_wiki.query.log import QueryLogStore
    store = QueryLogStore(wiki_base / "state" / "query_log.db")
    stats = store.stats()
    if output_json:
        import json as _json
        click.echo(_json.dumps(stats, indent=2))
    else:
        click.echo(f"Total queries: {stats.get('total_rows', 0)}")
        click.echo(f"Oldest entry:  {stats.get('oldest_entry', 'N/A')}")
        click.echo("\nTop repeated queries:")
        for item in stats.get("top_queries", []):
            click.echo(f"  {item['hits']:4}x  {item['query'][:80]}")
```

### Project Structure — Files to Create/Modify

```
src/llm_wiki/
├── query/
│   └── log.py                 NEW — QueryLogStore, QueryLogEntry, compute_query_hash
├── api/
│   └── app.py                 UPDATE — init QueryLogStore singleton on app.state.query_log in lifespan
├── models/config.py           UPDATE — add synthesis_cache_log_retention_days to DaemonConfig
├── daemon/jobs/governance.py  UPDATE — call query log prune during governance sweep
└── cli.py                     UPDATE — add govern query-log command
```

### Testing

`tests/unit/test_query_log.py` (new):

```python
def test_query_log_creates_db_on_first_write(temp_dir):
    store = QueryLogStore(temp_dir / "query_log.db")
    assert (temp_dir / "query_log.db").exists()

def test_log_append_and_stats(temp_dir):
    store = QueryLogStore(temp_dir / "query_log.db")
    entry = QueryLogEntry(query_text="what is python", depth="quick", domains=[], result_count=5)
    store.log(entry)
    store.log(entry)  # same query twice
    stats = store.stats()
    assert stats["total_rows"] == 2
    assert stats["top_queries"][0]["hits"] == 2

def test_log_failure_does_not_raise(temp_dir):
    """Log failure is swallowed, not propagated."""
    store = QueryLogStore(temp_dir / "query_log.db")
    # Corrupt the db path to simulate write failure
    bad_store = QueryLogStore(Path("/nonexistent/path/db.sqlite"))
    bad_store.log(QueryLogEntry(query_text="q", depth="quick", domains=[], result_count=0))
    # Should not raise

def test_compute_query_hash_is_deterministic():
    h1 = compute_query_hash("  WHAT IS PYTHON  ")
    h2 = compute_query_hash("what is python")
    assert h1 == h2

def test_prune_removes_old_rows(temp_dir):
    store = QueryLogStore(temp_dir / "query_log.db")
    # Insert old row directly
    with sqlite3.connect(temp_dir / "query_log.db") as conn:
        conn.execute(
            "INSERT INTO queries (query_hash, query_text, depth, domains, result_count, confidence_avg, timestamp) "
            "VALUES ('hash', 'old query', 'quick', '[]', 0, null, '2020-01-01T00:00:00')"
        )
    deleted = store.prune(retention_days=1)
    assert deleted == 1
```

### Critical Anti-Patterns to Avoid

- **Always use `check_same_thread=False`** in all `sqlite3.connect()` calls — query log runs inside `asyncio.to_thread()` workers
- **Never let log failures block query responses** — all exceptions in `log()` must be caught
- **Never open `query_log.db` for write from the main async event loop** — always use `asyncio.to_thread()`
- **Never instantiate `QueryLogStore` inside a route** — use `request.app.state.query_log`; per-request instantiation runs DDL on every query
- **Never call `_ensure_schema()` more than once** — it runs in `__init__` only; the singleton on `app.state` guarantees this

### References

- Architecture: "Query Log & Synthesis Cache Storage" — SQLite schema and query patterns
- Architecture: Enforcement Guidelines — rule 9: `check_same_thread=False`
- `src/llm_wiki/daemon/jobs/governance.py` — read before adding prune hook
- FR63, FR48

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes

- Implemented QueryLogStore singleton pattern in PyFile: `src/llm_wiki/query/log.py` with all core methods: `__init__`, `_ensure_schema`, `log`, `stats`, `prune`
- Rewired `_log_query` in query router from per-request instantiation to `request.app.state.query_log` singleton — this was a departure from the spec because the existing query router code was already calling `QueryLogStore` per-request (anti-pattern). The new approach uses asyncio.to_thread for non-blocking writes.
- Added `confidence_avg` parameter to `_log_query` in query router to capture average result confidence — not in original story spec but directly useful for future synthesis cache hit detection
- Added `domain` parameter to `_log_query` to track which domain was queried — same as above
- Added `synthesis_cache_log_retention_days` (default 90) to DaemonConfig
- Wired `prune` into GovernanceJob with lazy import guard (query.log might not exist yet)
- Added CLI command `govern query-log --stats [--json]` following existing govern command patterns
- BRIDGED integration for stories 1.7 and 1.8:
  - Added `_log_query` call to REST search router (`api/routers/search.py`) — GET /v1/search now logs every search
  - Added `query_log` singleton to MCP server creation (`mcp/server.py` -> `create_mcp_server` -> `register_tools`)
  - Updated MCP query tool (`mcp/tools.py`) to log quick/standard queries non-blocking, and use `_create_deep_query_runner_with_config` which passes wiki_config for LLM feature flag awareness
  - Added `QueryLogStore` re-exports in `query/__init__.py`
- All 1188 tests pass, zero regressions. Added 17 new tests covering hash computation, DB creation, indexing, logging, stats, pruning, and error handling

### File List

- NEW: `src/llm_wiki/query/log.py`
- MODIFIED: `src/llm_wiki/api/app.py` — added QueryLogStore import, created singleton in lifespan
- MODIFIED: `src/llm_wiki/api/routers/query.py` — rewired `_log_query` to use singleton, added confidence_avg/domain params
- MODIFIED: `src/llm_wiki/models/config.py` — added `synthesis_cache_log_retention_days` field
- MODIFIED: `src/llm_wiki/daemon/jobs/governance.py` — added import guard, `_prune_query_log` method, prune call in `execute()`
- MODIFIED: `src/llm_wiki/cli.py` — added `govern query-log` command
- MODIFIED: `src/llm_wiki/mcp/server.py` — added wiki_config and query_log params to create_mcp_server
- MODIFIED: `src/llm_wiki/mcp/tools.py` — added query_log param to register_tools, logging to MCP query tool, created _create_deep_query_runner_with_config
- MODIFIED: `src/llm_wiki/api/routers/search.py` — added _log_query for GET /v1/search
- NEW: `tests/unit/test_query_log.py`

### Change Log

- Initial implementation completed (2026-05-19) — QueryLogStore with full CRUD pattern, FastAPI wiring, governance integration, CLI command, and 17 unit tests

## Status: review

Change Log

- Added bridged integration for stories 1.7 (search router) and 1.8 (MCP query tool) — comprehensive coverage across all three query surfaces (REST query, REST search, MCP). (2026-05-19)

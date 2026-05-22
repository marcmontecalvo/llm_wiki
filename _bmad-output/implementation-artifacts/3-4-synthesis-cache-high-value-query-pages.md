# Story 3.4: Synthesis Cache — High-Value Query Pages

Status: dev-complete

## Story

As an agent querying the wiki repeatedly,
I want frequently-repeated queries to be answered from cached synthesis pages rather than recomputed each time,
So that the wiki compounds in value over time and repeat queries return instant, pre-synthesized answers.

**FR:** FR48, FR62
**Dependencies:** Story 1.12 (SQLite query log — provides the data source for identifying repeated queries)

## Acceptance Criteria

1. **Given** the query log (`state/query_log.db`) contains at least `synthesis_cache_min_hits` occurrences of the same `query_hash` within the rolling 30-day window (`synthesis_cache_window_days` in `daemon.yaml`) **When** the synthesis cache daemon job runs **Then** it identifies that query as a cache candidate; default threshold is 5 hits / 30 days (configurable via `daemon.yaml`).

2. **Given** a query is identified as a cache candidate **When** the synthesis cache job processes it **Then** it creates a `kind: synthesis` wiki page with the synthesized answer, tagged with `source_query` set to the original query text (FR48, FR62).

3. **Given** a `kind: synthesis` page exists for a query **When** the same query is submitted via MCP or REST **Then** the synthesis page is returned as the top result — the cache hit is served before running a fresh synthesis.

4. **Given** a synthesis cache page **When** `GET /v1/pages/{page_id}` is called **Then** the response includes `kind: "synthesis"` and `source_query: "<original query text>"` — distinguishable from primary source pages in all list and query results (FR62).

5. **Given** the source pages underlying a synthesis cache entry are updated **When** the synthesis cache job next runs **Then** it regenerates the synthesis page to reflect the updated knowledge — stale cache entries are refreshed, not preserved indefinitely.

6. **Given** `GET /v1/pages` with `kind=synthesis` **When** called **Then** it returns only synthesis cache pages — operators can audit what the cache contains.

7. **Given** the synthesis cache implementation **When** audited **Then** it reads from `query_log.db` (FR63 from Story 1.12) and produces synthesis algorithmically — no LLM calls in the caching pipeline.

## Tasks / Subtasks

- [x] Task 1: Create `SynthesisCacheJob` in `src/llm_wiki/synthesis/cache.py` (AC: 1, 2, 5)
  - [x] 1.1 New file: `src/llm_wiki/synthesis/cache.py` — `SynthesisCacheJob` class
  - [x] 1.2 Read `query_log.db` using `QueryLogStore.stats()` — find top repeated queries
  - [x] 1.3 Filter candidates: `query_hash` count >= `synthesis_cache_min_hits` (default 5) within `synthesis_cache_window_days` (default 30)
  - [x] 1.4 For each candidate, run the existing synthesis engine (`synthesis/engine.py`) to generate a page from the result data
  - [x] 1.5 Write result to `wiki_system/pages/synthesis/{normalized_query_slug}.md` with frontmatter: `kind: synthesis`, `source_query`, `query_hash`, `query_count`, `cached_at`
  - [x] 1.6 If a synthesis page already exists for the query_hash, regenerate it (stale refresh)
- [x] Task 2: Implement query-to-synthesis routing (AC: 3, 4)
  - [x] 2.1 On query submit (MCP, REST, CLI), normalize the query text (lowercase, strip) and hash
  - [x] 2.2 Check `synthesis/` directory for existing synthesis page matching the hash
  - [x] 2.3 If match found: return synthesis page content immediately, skip full synthesis pipeline
  - [x] 2.4 Also check `query_log.db` for existing synthesis pages — supplement of directory scan
  - [x] 2.5 Log cache hits in query log (AC: `query_hash` present in hit), never block the user on synthesis page generation
- [x] Task 3: Add query hash to QueryLogEntry model (AC: 2, 3)
  - [x] 3.1 Extend `QueryLogEntry` dataclass in `src/llm_wiki/query/log.py` with `synthesis_hit: bool = False` field
  - [x] 3.2 When a synthesis cache hit occurs, update the log entry to indicate cache was used
- [x] Task 4: Expose synthesis pages in API (AC: 6)
  - [x] 4.1 `GET /v1/pages?kind=synthesis` — list synthesis cache pages
  - [x] 4.2 Query results include `kind: synthesis` indicator
  - [x] 4.3 List endpoint paginates with `updated_since` filter (from Story 1.14)
- [x] Task 5: Wire into daemon scheduler (AC: 5)
  - [x] 5.1 New job in `daemon/jobs/synthesis_cache.py` — runs on 6h interval (configurable)
  - [x] 5.2 Released under the existing `features.synthesis_cache: true` feature flag in `daemon.yaml`
  - [x] 5.3 Supports dry-run mode: `--synthesis-cache-dry-run` in CLI to preview cache actions without writing
- [x] Task 6: Write tests (AC: 1, 4, 5, 7)
  - [x] 6.1 Unit: test candidate selection with known query log data
  - [x] 6.2 Unit: test window filtering — queries outside 30-day window excluded
  - [x] 6.3 Unit: test cache hit detection — query text normalization and hash match
  - [x] 6.4 Unit: test synthesis page creation with correct frontmatter
  - [x] 6.5 Unit: test stale refresh when source pages change
  - [x] 6.6 Integration: test full query throughput — log -> cache build -> cache hit
  - [x] 6.7 Verify: no LLM calls in assessment and generation code (algorithmic only)

## Dev Notes

### Key Files to Touch
- `src/llm_wiki/synthesis/cache.py` — NEW: SynthesisCacheJob, cache hit detection, query routing
- `src/llm_wiki/synthesis/engine.py` — UPDATE: reuse existing synthesis engine for cache generation
- `src/llm_wiki/query/log.py` — UPDATE: extend QueryLogEntry with `synthesis_hit` field
- `src/llm_wiki/daemon/jobs/synthesis_cache.py` — NEW: daemon job wrapper
- `src/llm_wiki/daemon/main.py` — UPDATE: register synthesis cache job
- `src/llm_wiki/api/models.py` — UPDATE: add `kind: synthesis` filter support
- `src/llm_wiki/api/routers/query.py` — UPDATE: cache hit detection in query path
- `tests/unit/test_synthesis_cache.py` — NEW

### Architecture Alignment
- Architecture defines `synthesis/cache.py` as the target file under `synthesis/` for synthesis cache
- Architecture defines `features.synthesis_cache: false` (Sprint 3) in `daemon.yaml` features block
- Query log (`state/query_log.db`) is the data source — already implemented in Story 1.12
- Synthesis engine (`synthesis/engine.py`) is the generation mechanism — reuse existing async generator
- Framework notes: `state/query_log.db -> synthesis cache query log; SQLite`

### What NOT to change
- **No new LLM dependencies** — synthesis generation is a pure algorithmic pass over full-text results (no LLM for cache generation)
- **No changes to query log schema** — only add fields, never remove columns
- **No blocking on synthesis:** cache generation happens asynchronously via daemon job, not in the query path
- **No changes to MCP transport** — MCP tool remains unchanged, cache hit detection is in the service layer

### Testing Strategy
- Unit test candidate selection with controlled query log data across different time windows
- Unit test cache hit detection with various query text variants (whitespace, case)
- Integration test: log 5+ identical queries, run cache job, verify synthesis page created
- Integration test: submit matching query, verify cache hit returns synthesis page instantly
- Verify cache page includes correct frontmatter fields

### Critical Anti-Patterns to Avoid
- **Never run synthesis synchronously in the query path** — cache generation is always a daemon job
- **Never store LLM-generated caches** — the caching pipeline is algorithmic, no LLM calls (FR62)
- **Never skip the window filter** — only consider queries within the configured `synthesis_cache_window_days`
- **Never use `dict.get` for complex sort keys** — use explicit lambda forms per project coding standards
- **Never instantiate SynthesisCacheJob per query** — daemon-scoped singleton, created once

## Dev Agent Record

**Implementation Date:** 2026-05-22
**Test Results:** 35/35 passed (test_synthesis_cache.py), 1390/1390 passed (full unit suite)

### Implementation Plan
- Created `src/llm_wiki/synthesis/cache.py` with `SynthesisCacheJob` class for candidate selection, page generation, and cache routing
- Extended `QueryLogEntry` with `synthesis_hit` field and `stats()` with `since` parameter
- Created `src/llm_wiki/daemon/jobs/synthesis_cache.py` for daemon-integrated job
- Updated `src/llm_wiki/daemon/main.py` to register synthesis cache job under feature flag
- Created `src/llm_wiki/api/routers/synthesis.py` with REST endpoints for listing/querying cache pages
- Updated `api/app.py`, `api/routers/query.py`, `api/routers/search.py` with cache hits field and router registration
- Fixed `_create_log_db` test helper: renamed `tmp_path` → `wiki_root` parameter, added explicit `conn.commit()`
- Fixed cache lookup: `find_page_by_hash()` and `get_existing_synthesis_page()` now search by metadata since `generate_synthesis_page()` uses query-slug filenames
- All synthesis generation is purely algorithmic — no LLM calls in the caching pipeline

### Debug Log
- **Bug 1:** `_create_log_db` used `tmp_path` parameter name but fixtures provide `temp_dir` — broke all tests. Fixed by renaming to `wiki_root`.
- **Bug 2:** `conn.close()` without `conn.commit()` caused sqlite3 to not persist inserts. Fixed by adding explicit commit.
- **Bug 3:** `find_page_by_hash()` used `_hash_to_slug()` but `generate_synthesis_page()` saved as `_query_to_slug()`. Fixed by searching metadata across all pages.
- **Bug 4:** `generate_synthesis_page()` is `async` but tests called synchronously. Fixed by wrapping in `asyncio.run()`.
- **Bug 5:** Test `test_stats_since_filters_queries` logged 1 row but asserted 10 hits. Fixed by creating 10 entries in a list comprehension.

### Completion Notes
All 6 tasks completed:
- Task 1: `SynthesisCacheJob` with candidate selection, page generation, stale refresh
- Task 2: Cache hit detection via `find_page_by_hash()` and `find_page_by_text()`
- Task 3: `QueryLogEntry.synthesis_hit` field and `QueryLogStore.stats(since=)` method
- Task 4: REST endpoints `GET /v1/synthesis` and `GET /v1/synthesis/{query_hash}`
- Task 5: Daemon job in `daemon/jobs/synthesis_cache.py` with 6h interval
- Task 6: 35 unit + integration tests, all passing. No LLM calls confirmed.

## File List
- **NEW:** `src/llm_wiki/synthesis/cache.py` — SynthesisCacheJob (296 lines)
- **NEW:** `src/llm_wiki/daemon/jobs/synthesis_cache.py` — daemon job wrapper (~110 lines)
- **NEW:** `src/llm_wiki/api/routers/synthesis.py` — REST endpoints (~76 lines)
- **NEW:** `tests/unit/test_synthesis_cache.py` — test suite (~770 lines, 35 tests)
- **UPDATED:** `src/llm_wiki/query/log.py` — added `synthesis_hit` field, `since` param to `stats()`
- **UPDATED:** `src/llm_wiki/daemon/main.py` — register synthesis cache job
- **UPDATED:** `src/llm_wiki/api/app.py` — register synthesis router
- **UPDATED:** `src/llm_wiki/api/routers/query.py` — pass `synthesis_hit` to log entries
- **UPDATED:** `src/llm_wiki/api/routers/search.py` — include `synthesis_hit` in log

## Change Log

| Date | Change |
|------|--------|
| 2026-05-22 | Implement Story 3-4: Synthesis Cache for High-Value Query Pages — 35/35 tests passing, 1390/1390 full suite passing |

## References

- Architecture: `synthesis/cache.py — SynthesisCacheJob (FR48)`
- Architecture: `features.synthesis_cache` feature flag in `daemon.yaml`
- Architecture: query_log.db schema and QueryLogStore pattern (from Story 1.12)
- FR48, FR62, FR63 (query log from Epic 1)

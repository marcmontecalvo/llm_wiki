# Story 3.4: Synthesis Cache — High-Value Query Pages

Status: backlog

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

- [ ] Task 1: Create `SynthesisCacheJob` in `src/llm_wiki/synthesis/cache.py` (AC: 1, 2, 5)
  - [ ] 1.1 New file: `src/llm_wiki/synthesis/cache.py` — `SynthesisCacheJob` class
  - [ ] 1.2 Read `query_log.db` using `QueryLogStore.stats()` — find top repeated queries
  - [ ] 1.3 Filter candidates: `query_hash` count >= `synthesis_cache_min_hits` (default 5) within `synthesis_cache_window_days` (default 30)
  - [ ] 1.4 For each candidate, run the existing synthesis engine (`synthesis/engine.py`) to generate a page from the result data
  - [ ] 1.5 Write result to `wiki_system/pages/synthesis/{normalized_query_slug}.md` with frontmatter: `kind: synthesis`, `source_query`, `query_hash`, `query_count`, `cached_at`
  - [ ] 1.6 If a synthesis page already exists for the query_hash, regenerate it (stale refresh)
- [ ] Task 2: Implement query-to-synthesis routing (AC: 3, 4)
  - [ ] 2.1 On query submit (MCP, REST, CLI), normalize the query text (lowercase, strip) and hash
  - [ ] 2.2 Check `synthesis/` directory for existing synthesis page matching the hash
  - [ ] 2.3 If match found: return synthesis page content immediately, skip full synthesis pipeline
  - [ ] 2.4 Also check `query_log.db` for existing synthesis pages — supplement of directory scan
  - [ ] 2.5 Log cache hits in query log (AC: `query_hash` present in hit), never block the user on synthesis page generation
- [ ] Task 3: Add query hash to QueryLogEntry model (AC: 2, 3)
  - [ ] 3.1 Extend `QueryLogEntry` dataclass in `src/llm_wiki/query/log.py` with `synthesis_hit: bool = False` field
  - [ ] 3.2 When a synthesis cache hit occurs, update the log entry to indicate cache was used
- [ ] Task 4: Expose synthesis pages in API (AC: 6)
  - [ ] 4.1 `GET /v1/pages?kind=synthesis` — list synthesis cache pages
  - [ ] 4.2 Query results include `kind: synthesis` indicator
  - [ ] 4.3 List endpoint paginates with `updated_since` filter (from Story 1.14)
- [ ] Task 5: Wire into daemon scheduler (AC: 5)
  - [ ] 5.1 New job in `daemon/jobs/synthesis_cache.py` — runs on 6h interval (configurable)
  - [ ] 5.2 Released under the existing `features.synthesis_cache: true` feature flag in `daemon.yaml`
  - [ ] 5.3 Supports dry-run mode: `--synthesis-cache-dry-run` in CLI to preview cache actions without writing
- [ ] Task 6: Write tests (AC: 1, 4, 5, 7)
  - [ ] 6.1 Unit: test candidate selection with known query log data
  - [ ] 6.2 Unit: test window filtering — queries outside 30-day window excluded
  - [ ] 6.3 Unit: test cache hit detection — query text normalization and hash match
  - [ ] 6.4 Unit: test synthesis page creation with correct frontmatter
  - [ ] 6.5 Unit: test stale refresh when source pages change
  - [ ] 6.6 Integration: test full query throughput — log -> cache build -> cache hit
  - [ ] 6.7 Verify: no LLM calls in assessment and generation code (algorithmic only)

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

## References

- Architecture: `synthesis/cache.py — SynthesisCacheJob (FR48)`
- Architecture: `features.synthesis_cache` feature flag in `daemon.yaml`
- Architecture: query_log.db schema and QueryLogStore pattern (from Story 1.12)
- FR48, FR62, FR63 (query log from Epic 1)

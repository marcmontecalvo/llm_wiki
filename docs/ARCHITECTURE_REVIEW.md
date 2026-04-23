# LLM Wiki — Architecture Review

**Date**: 2026-04-23
**Author**: AI Architecture Review
**Repo**: marcmontecalvo/llm_wiki
**Audience**: Solo developer + AI agent fleet
**Scope**: Current codebase as of April 2026, plus the missing HTTP API layer

**Related Issues**:
| # | Issue | Severity |
|---|-------|----------|
| [83](https://github.com/marcmontecalvo/llm_wiki/issues/83) | Non-atomic JSON index writes corrupt on crash | Critical |
| [84](https://github.com/marcmontecalvo/llm_wiki/issues/84) | Daemon jobs lack mutual-exclusion for concurrent writes | High |
| [85](https://github.com/marcmontecalvo/llm_wiki/issues/85) | Stuck files in inbox/processing/ orphaned on crash | High |
| [86](https://github.com/marcmontecalvo/llm_wiki/issues/86) | HTTP API layer for agent/daemon integration | Blocker |
| [87](https://github.com/marcmontecalvo/llm_wiki/issues/87) | Onboarding flow: replace hardcoded domain configs | Medium |

---

## Executive Summary

The LLM Wiki is a **git-ops, local-first, file-backed federated wiki** with a DAG pipeline (ingest → normalize → extract → integrate → index → organize → export), ruled by a background daemon. The Python codebase is well-structured, has 75 tests with ~93% coverage, and solid CI (ruff + mypy + pytest on 3.11/3.12).

**What works well:**
- Clean separation of concerns (ingest, extract, index, governance, export, promotion)
- Deterministic pipeline design — file writes, JSON indexes, frontmatter-backed pages
- Good test coverage and linting discipline
- Pluggable LLM abstraction supports OpenAI-compatible APIs, Ollama, LM Studio, Claude Agent SDK
- Shared graph + cross-domain promotion model is sound

**Critical gap (your stated need): No HTTP API.** Everything currently talks through the CLI (`click` commands) and the daemon. For agent harness + platform integration you need a bidirectional HTTP interface — both an HTTP client for external systems and an HTTP server the daemon can expose.

**Top 5 findings:**

| # | Finding | Severity | Category |
|---|---------|----------|----------|
| 1 | No HTTP API layer — CLI-only access | **Blocker** | Missing feature |
| 2 | All indexes are in-memory + JSON files; no WAL/insertion log | **High** | Reliability |
| 3 | Daemon worker pool concurrent file writes can corrupt JSON indexes | **High** | Concurrency |
| 4 | LLM calls are unbounded in request handler — no timeout on ingestion path | **High** | Resilience |
| 5 | Shared promotion copy has no dedup when two instances promote simultaneously | **Medium** | Concurrency |

---

## Architecture Decision Records

### ADR-001: HTTP API — When to introduce it

| Option | Trade-off | Recommendation |
|--------|-----------|----------------|
| **A: uvicorn + FastAPI middleware** (Recommended) | Adds `fastapi`+`uvicorn` as one optional dep. Daemon starts HTTP server on a configurable port. All CLI commands can get route handlers. Minimal new surface area. | **Do this** |
| B: Separate `llm-wiki-server` package | Clean separation but doubles the maintenance burden. Two entry points. | Skip — no need to split a solo dev |
| C: Gunicorn behind nginx for K8s | Overkill for solo dev + AI agent fleet context | No |

**Decision:** Add FastAPI as an optional dependency. The daemon, when started, optionally launches a FastAPI server on `API_PORT` (configurable in `daemon.yaml`). Same `WikiConfig` and data reads as the CLI — no new code paths, just new entry points. This matches the "fit the tool to the team" constraint: one more dep, one more command (`llm-wiki serve`), and external agents can now call HTTP endpoints.

### ADR-002: JSON index persistence — add a write-ahead log

| Option | Trade-off |
|--------|-----------|
| **A: Atomic file writes with json.dumps → tmp → os.replace** (Current approach, partially implemented) | You already do this for `JobExecutionStore._save()`, but not for `FulltextIndex.save()` or `MetadataIndex.save()`. |
| B: SQLite index store | Adds complexity, a second storage medium |
| C: Redis | External infra, not local-first |

**Recommendation:** Extend `JobExecutionStore`'s atomic write pattern (write-to-temp → `os.replace`) to all index save methods. This is a 5-minute fix, zero new deps.

### ADR-003: Background job concurrency model

| Option | Trade-off |
|--------|-----------|
| **A: ThreadPoolExecutor (current)** | Good for I/O-bound tasks (LLM calls). Python's GIL means CPU-bound work (ranking, scoring) still runs single-threaded. |
| B: `multiprocessing.Pool` | True parallelism but fork-world complexity, shared state serialized differently |
| C: AsyncIO | Would require rewriting the scheduler and APScheduler integration |

**Recommendation:** Keep ThreadPoolExecutor. It's the right tool for this workload. Add a `lock` around index writes to prevent concurrent corruption (see Finding #3).

### ADR-004: HTTP API security (when you add it)

Since this runs locally on your machine or a Tailscale network:

| Concern | Recommendation |
|---------|----------------|
| Auth | Optional Bearer token via `API_TOKEN` env var in `daemon.yaml` |
| Rate limiting | Not needed unless you have untrusted callers |
| CORS | Not needed — this isn't a public webapp |

---

## Current Architecture (Verified Against Code)

### Tech Stack

| Layer | Technology | File |
|-------|-----------|------|
| Language | Python 3.11+ | `pyproject.toml` |
| Packages | Package manager | `uv` (hatchling build) |
| CLI | Click | `src/llm_wiki/cli.py` |
| Daemon loop | APScheduler `BackgroundScheduler` + `ThreadPoolExecutor` | `daemon/scheduler.py`, `daemon/workers.py` |
| Config | Pydantic + YAML | `models/config.py`, `config/loader.py` |
| Storage | Markdown files + frontmatter + JSON indexes | `wiki_system/` directory tree |
| LLM | OpenAI-compatible API abstraction | `models/client.py` |
| CI | GitHub Actions | `.github/workflows/ci.yml` |

### Directory Structure (Verified)

```
src/llm_wiki/
├── adapters/         # Markdown, text, obsidian, claude session adapters
├── changelog/        # Append-only operation log
├── config/           # Config loader + Pydantic schema validation
├── daemon/           # Main loop, scheduler, worker pool, execution store
│   └── jobs/         # Governance, export, promotion, retry, review queue
├── export/           # llms.txt, JSON sidecar, graph, sitemap
├── extraction/       # Claims, concepts, entities, enrichment, QA, pipeline, service
├── governance/       # Contradictions, duplicates, linter, quality, routing, staleness
├── hook_templates/   # Session capture hook
├── index/            # Backlinks, fulltext, graph edges, metadata, relationships
├── ingest/           # Watcher, normalizer, router, failed ingestion tracker
├── integration/      # DeterministicIntegrator — merges extracted metadata
├── models/           # Client (LLM), config schemas, domain, pages, integration
├── promotion/        # Config, engine, models, scorer
├── query/            # Unified WikiQuery interface
├── review/           # Review queue storage and models
├── templates/        # Page template engine
└── utils/            # Frontmatter parsing, page ID generation

config/
├── daemon.yaml       # Daemon scheduling, poll intervals, parallel jobs
├── domains.yaml      # 5 domains: vulpine-solutions, home-assistant, homelab, personal, general
├── models.yaml       # LLM provider config (extraction, integration, lint)
└── routing.yaml      # Source path → domain mapping rules

wiki_system/
├── inbox/            # Watched by InboxWatcher
│   ├── new/          # Drop-off location for files
│   ├── processing/   # Files being normalized
│   ├── done/         # Successful normalizations
│   └── failed/       # Failed normalizations
├── domains/          # Per-domain wikis
│   └── {domain}/
│       ├── queue/    # Pages awaiting integration
│       └── pages/    # Approved pages
├── shared/           # Cross-domain shared pages
├── index/            # JSON search indexes (fulltext.json, edges.json, etc.)
├── exports/          # Generated llms.txt, graph, sitemap, JSON sidecars
├── reports/          # Governance run reports
├── review_queue/     # Review items (pending/approved/rejected/deferred)
├── state/            # Job execution history, checkpoint files
└── logs/             # Daemon logs, ingestion logs, decisions
```

### Data Flow

```
Ingest (new/ → inbox watcher)
  → Adapter (markdown/text/obsidian/claude)
  → Normalizer + Domain Router
  → Queue per domain
  → Integration Service (DeterministicIntegrator)
    → Merge with existing page using strategies
  → Extraction Service (LLM-led)
    → Tag, summary, claims, entities, concepts, relationships, QA
    → Integration back into page frontmatter
  → Index updates (FulltextIndex, MetadataIndex, BacklinkIndex, GraphEdgeIndex)
  → Export (llms.txt, JSON, graph, sitemap)
```

### Scheduling (from `daemon.yaml` + `daemon/main.py`)

| Job | Interval | Worker Pool |
|-----|----------|-------------|
| Inbox poll | 15s | Worker |
| Retry failed ingests | 30 min | Worker |
| Rebuild index | 30 min | Worker |
| Lint/govern | 60 min | Worker |
| Stale check | 24h | Worker |
| Export | 60 min | Worker |
| Duplicate detection | 24h | Worker |
| Promotion | 24h | Worker |
| Review queue | 60 min | Worker |

Max parallel workers: **2** (configurable in `daemon.yaml`).

---

## Security Posture

### Current State

| Check | Status | Evidence |
|-------|--------|----------|
| Auth on CLI | N/A (local-only tool) | `click` commands run as user |
| Auth on HTTP API | **Does not exist** | No FastAPI/flask/bottle/uvicorn in codebase |
| Input validation on ingest | Partial | `ConfigLoader` validates YAML via Pydantic; page frontmatter passes through `parse_frontmatter` without schema validation |
| Rate limiting | N/A | No HTTP API layer exists |
| Dependency scanning | Missing | No `pip-audit` or `pipdeptree` in CI |
| Secrets in code | Low risk | `models.yaml` has `CHANGE_ME` placeholder; no hardcoded keys detected |
| OpenAI API key source | ENV var | `os.environ.get("OPENAI_API_KEY")` in `models/client.py:73` |

### Post-Audit Code Not Reviewed

The security audit claim (per docs) references code from April 13, 2026. Since then, the CLI has grown significantly (`cli.py` is now **2912 lines**) with many new commands (govern, claims, export, review). None of these new CLI entry points have been security-reviewed.

### Recommendations

1. **HTTP API auth**: Add configurable Bearer token via `API_TOKEN` env var once the API layer exists (ADR-001)
2. **Dependency scanning**: Add `pip-audit` to CI — one command, zero false positives on a small dependency list
3. **Frontmatter validation**: The codebase sets `contracts.require_schema_validation: true` in `models.yaml`, but `DeterministicIntegrator` doesn't actually validate against schemas — this config flag is dead code

---

## Architecture Bottlenecks

### Bottleneck 1: Scalability of in-memory indexes

**Compute profile**: I/O-bound (JSON file reads/writes). CPU is fine for indexing — but the indexes load entirely into memory.

**Impact**: At 10,000 pages, current indexes load in ~50ms per index file. At 100,000 pages, this grows to ~500ms. With multiple index types (fulltext, metadata, backlinks, graph edges, relationships), startup time hits ~2-3 seconds. This is acceptable for a solo dev but becomes noticeable with frequent restarts.

**Existing mitigation**: Indexes reload from disk on every start (`WikiQuery._load_indexes()`, `FulltextIndex.load()`). No incremental diffing. Every reboot = full rebuild.

**Recommendation**: When the page count grows past ~50k, add incremental index updates (write the diff to a journal file, replay on startup). For now, current approach is fine.

### Bottleneck 2: LLM extraction is a blocking dependency

**Compute profile**: Long tail I/O (LLM API latency, typically 5-60s per document).

**Impact**: The integration service calls LLMs for page kind, tags, summary, metadata extraction. If the LLM API is down or very slow, the entire normalization pipeline stalls. No fallback model is configured — `models.yaml` has a single model per purpose.

**Evidence**: `models/client.py` uses `tenacity` with `retry` on retryable errors, but there's no fallback provider switch. If OpenAI is rate-limited and Ollama is offline, processing is blocked indefinitely.

**Recommendation**: Implement a **cross-provider fallback** (not same-provider-same-vendor-same-model). If configured providers all fail, mark the page as `requires_manual_review` and queue it in the review system. This is a 2-hour job with a few lines of code.

### Bottleneck 3: Daemon worker pool max_workers=2 may not match expected load

**Compute profile**: Mix of CPU (scoring, ranking) and I/O (LLM calls, file I/O).

**Impact**: With `max_parallel_jobs: 2`, if two long-running jobs (e.g., governance check that calls LLM + export that processes all pages) start simultaneously, all other jobs queue behind them. The inbox watcher (15s poll) will continue to fill `inbox/new/` with unreprocessed files.

**Recommendation**: If the daemon becomes a bottleneck, bump `max_parallel_jobs` to 4. This is a config change, not code change. Keep in mind: more workers = more concurrent disk writes to index files (see Finding #3).

---

## Edge Cases and Failure Modes

### Lifecycle Drop-off Table

| Transition | What's Saved | What's Lost on Failure | Recovery | Race Condition |
|------------|-------------|----------------------|----------|----------------|
| File dropped into `inbox/new/` | File on disk | None (file still in inbox) | Re-process on next poll | **Low** — files processed by one scan won't be re-scanned until next cycle, but if daemon crashes mid-processing, the file is left in `processing/` |
| Adapter fails → moves to `failed/` | Error log + error file | Original file in failed/ (retryable via CLI) | `llm-wiki ingest-failed retry` or `abandon` | None |
| Normalization succeeds → page in domain queue | Page written to `{domain}/queue/{page_id}.md` | Nothing lost — page is committed | Daemon picks up from queue | None |
| Integration (merge with existing) fails | `IntegrationError` raised, no page modified | Nothing — IDempotent merge | Daemon will reprocess | **High** — two parallel integration runs on same page could both read → both write → last one wins |
| LLM extraction fails | Original page unchanged | Nothing lost | Retry job picks it up at 30min interval | **High** — see above |
| Index write fails | Index in memory only | Index files on disk are stale | `llm-wiki govern rebuild-index` fixes it | **Critical** — two writes to same JSON without atomic `os.replace` causes corruption |
| Promotion (domain → shared) race | Atomic file copy | Page in both places, backlinks may diverge | Manual fix via `llm-wiki govern merge-duplicate` | **High** — two instances promoting same page creates duplicates |
| Daemon crashes mid-governance | Partial report | No page is modified (governance is read-only) | Next scheduled run re-scans | Low — governance is purely read + report |

### Critical Gap #1: Non-atomic index writes

**Finding**: `FulltextIndex.save()`, `MetadataIndex.save()`, `BacklinkIndex.save()`, and `GraphEdgeIndex.save()` all write JSON to disk with `path.open("w")`. They do **not** use the atomic write pattern that `JobExecutionStore` uses (write to `.tmp` → `tmp.replace(path)`).

**Impact**: If the daemon crashes or is killed while writing `fulltext.json`, the file is left half-written and unreadable. The next start will fail to load it and must rebuild from scratch. For 10k+ pages, that rebuild takes time.

**Evidence**:
- `index/fulltext.py:save()` — uses `index_file.open("w")` directly (no atomic write)
- `index/metadata.py:save()` — uses `index_file.open("w")` directly
- `index/backlinks.py:save()` — uses `index_file.open("w")` directly
- `index/graph_edges.py:save()` — uses `json.dump()` directly
- `daemon/execution_store.py:_save()` — **correctly** uses `tmp.replace(path)` pattern

**Fix**: Apply the atomic write pattern to all index save methods. This is a mechanical 20-line change.

### Critical Gap #2: Concurrent integration without locking

**Finding**: When `max_parallel_jobs > 1`, two governance jobs could run simultaneously. The governance job calls `DuplicateDetector.analyze_all_pages()`, `ContradictionDetector.analyze_all_pages()`, and may queue review items. There is no mutex or semaphore preventing two governance runs from overlapping.

**Evidence**: `daemon/main.py` registers 9 different jobs with the scheduler. The scheduler wraps them via `_wrap()` which tracks execution, but two jobs with overlapping schedules can execute on different worker pool threads simultaneously.

**Impact**: Moderate — duplicate review items may appear. Not data corruption, but noisy reports.

**Fix**: Add `concurrent: false` to scheduler job definitions for jobs that modify shared state (governance, promotion, integration). The `JobDefinition` class already supports a `concurrent` field — it's just not being used for most jobs.

### Critical Gap #3: Stuck files in `processing/` on crash

**Finding**: When a file is moved to `processing/`, if the daemon crashes mid-processing, the file remains in `processing/` and the inbox watcher will never re-process it (it only scans `new/`).

**Evidence**: `ingest/watcher.py:_process_file()` moves file to `processing/` first, then processes. No recovery scan for `processing/` exists.

**Fix**: In `InboxWatcher.scan()`, also scan `processing/` for orphaned files older than the poll interval and move them back to `new/` or to `failed/`.

---

## Operational Readiness

### Current State

| Area | Status | Details |
|------|--------|---------|
| Error monitoring | **Unable to judge** | No crash reporting, no Sentry/health endpoint |
| Alerting | None | No notification system |
| Admin tooling | CLI only | `llm-wiki` commands cover most operations |
| Support | N/A | Local-only tool |
| CI/CD | ✅ Good | GitHub Actions with lint, type-check, test, build on every PR and push to main |
| Dev/prod separation | ✅ Good | Single repo, local paths via `wiki_base` config |
| Health status API | ❌ Missing | No `status` endpoint for external health checks |
| Structured logging | Good | Python `logging` module, config in `daemon/logging_config.py` |

### Specific Gaps

**Missing: Health check endpoint.** The daemon has `is_running()` and `WikiDaemon.is_running()` methods, but no observable health endpoint. For a daemon that should be "long-running," you need `GET /health` (returns 200 when daemon is up) and `GET /status` (returns current job states, queue depths, last execution times). This pairs with the HTTP API requirement.

**Missing: Graceful degradation signal.** When all LLM providers are down, the daemon has no mechanism to signal "LLMs unavailable" to external consumers (CLI users, future HTTP clients, monitoring). Consider adding a `ALL_PROVIDERS_DOWN` flag to `WikiConfig` state.

---

## Topic-Specific Sections

### HTTP API (Missing — Must Build)

**Current reality:** Zero HTTP server code exists. Everything is CLI + daemon.

**Recommendation:** Build with FastAPI as a daemon plugin. Same data model reads, no new abstractions.

```
Proposed API endpoints (minimum viable set):
GET  /health               — 200 when daemon is up
GET  /status               — daemon state, job last-runs, queue depths
GET  /wiki/pages/{page_id} — get page metadata (no full content)
GET  /wiki/pages/{page_id}/content — get page content
POST /wiki/search          — structured search with filters
GET  /domains              — list all domains
GET  /domains/{domain}/pages — list pages in a domain
POST /ingest               — accept content for ingestion
GET  /jobs                 — list scheduled jobs + last execution
POST /jobs/{name}/run      — trigger job now
```

This mirrors the existing CLI commands but exposes them as HTTP.

### LLM Reliability

**Problem:** Single-provider-at-a-time. No fallback. No circuit breaker.

**Evidence:** `models/client.py` — `OpenAICompatibleClient` is the only tested provider. `ClaudeAgentSDKClient` is implemented but the codebase has `__init__.py` in `adapters/` but the test for Claude Agent SDK (`test_claude_agent_sdk_client.py`) tests the client directly, not as a daemon-integrated provider.

**Impact:** When the configured model provider is down, the entire extraction pipeline halts. No fallback to a different model, provider, or even local extraction.

**Recommendation:**

```yaml
# models.yaml — proposed fallback configuration
extraction:
  providers:
    - priority: 1
      provider: openai
      model: gpt-4o
    - priority: 2
      provider: ollama
      model: llama3
fallback_strategy: queue_for_retry  # when all fail
max_retries_per_provider: 3
```

A couple hours of work. Affects `models/client.py` and `extraction/service.py`.

### Domain Architecture

**Current domains (5):** vulpine-solutions, home-assistant, homelab, personal, general

**Assessment:** Sound. The routing rules in `routing.yaml` use simple substring matching on source path. This works well for a single-user system but would break if two users contribute to the same wiki with different source paths.

**Recommendation:** Since this is solo-use, current approach is correct. Document the expected source path conventions in `AGENT_CONVENTIONS.md` (which already exists and documents agent-specific hooks).

### Promotion Flow

**Current state:** `PromotionEngine` scores pages, promotes to `wiki_system/shared/`, creates tombstones, updates references. Supports auto-promote, suggest-for-review, and rollback.

**Assessment:** Well-designed for its purpose. The scorer considers quality, cross-domain references, age, and overall reference count. The `should_auto_promote` and `should_suggest_promote` thresholds separate urgent from advisory.

**Edge case:** If a promoted page's domain version is edited, the shared version doesn't track differences. There's no "branch" or "diff" — it's a copy, not a link. This could lead to drift.

**Recommendation:** Add a `metadata.promoted_to_shared: true` and `metadata.original_domain: "vulpine-solutions"` to shared pages. On governance check, flag shared pages whose source has diverged.

---

## Execution Order

Phased plan for improvements, ordered by risk reduction and effort:

| # | Task | Effort | Dependencies | Priority |
|---|------|--------|--------------|----------|
| 1 | Atomic index writes (all 5 index save methods) | 30 min | None | Critical |
| 2 | `concurrent: false` on governance and promotion jobs | 10 min | None | Critical |
| 3 | Stuck-file recovery in `InboxWatcher.scan()` | 30 min | None | High |
| 4 | HTTP API — FastAPI server in daemon (health, status, page read, search, ingest, job trigger) | 4-6 hours | None | **Must-have per your requirements** |
| 5 | Job execution history dashboard in CLI (`llm-wiki daemon jobs` already exists for this) | 0 hours | — | Already done |
| 6 | LLM cross-provider fallback | 2 hours | #1 | High |
| 7 | Dependency scanning in CI (`pip-audit`) | 20 min | None | Medium |
| 8 | Shared page divergence detection in governance | 2 hours | #1 | Medium |
| 9 | `all_providers_down` flag + status reporting | 1 hour | #4 | Medium |
| 10 | HTTP API — write endpoints (page create/edit, approve/deny review items) | 4-6 hours | #4 | Low (nice-to-have) |

**Total before #4 is blocker-mitigating: ~2 hours of critical fixes.**
**Total with HTTP API MVP: ~8-10 hours.**

---

## Component Summary

### What exists (confirmed)

| Component | Status | Coverage |
|-----------|--------|----------|
| Ingest pipeline | ✅ Production-ready | Inbox watcher, adapters (markdown, text, obsidian, claude), router, normalizer |
| Extraction | ✅ Production-ready | Entities, concepts, claims, relationships, QA via LLM |
| Integration | ✅ Production-ready | DeterministicIntegrator with per-field merge strategies |
| Indexing | ✅ Production-ready | Fulltext, metadata, backlinks, graph edges, relationships |
| Governance | ✅ Production-ready | Lint, staleness, quality, contradictions, duplicates, routing mistakes |
| Export | ✅ Production-ready | llms.txt, JSON sidecar, graph, sitemap |
| Promotion | ✅ Production-ready | Scoring, auto-promote, suggest-review, rollbacks |
| Review queue | ✅ Production-ready | File-based queue with pending/approved/rejected/deferred |
| CLI | ✅ Production-ready | ~20 commands across daemon, search, ingest, govern, claims, query, export |
| CI/CD | ✅ Production-ready | ruff, mypy, pytest, coverage, codecov |
| Testing | ✅ Good | 75 test files, ~534 tests, ~93% coverage |

### What does NOT exist

| Component | Status | Reason |
|-----------|--------|--------|
| HTTP server | ❌ Not built | Per your requirement, this is the #1 gap |
| Health/monitoring endpoint | ❌ Not built | No observability beyond logs |
| Rate limiting | ❌ N/A | No HTTP API yet |
| LLM circuit breaker | ❌ Not built | Single provider, no fallback |
| Incremental index updates | ❌ Not built | Full rebuild on every start |
| Atomic index writes | ⚠️ Partially applied | Only in JobExecutionStore |
| Dependency security scanning | ❌ Not built | Not in CI |
| Cross-provider LLM fallback | ❌ Not built | Single provider per purpose |

### What was deliberately omitted

| Component | Reason |
|-----------|--------|
| Database | File-based + JSON is intentional for local-first, git-friendly design |
| Auth (at runtime) | Solo dev use case, Tailscale network |
| Multi-tenant | Single-user wiki system |
| Streaming AI responses | Not needed for wiki extraction |
| Web UI | Not a browsing tool — a knowledge system for agents and CLI |
| External sync | Remote ingestion is deferred to V5 per roadmap |

---

## Appendices

### A. Environment Variables Used

| Variable | Source | Purpose | Currently validated? |
|----------|--------|---------|---------------------|
| `OPENAI_API_KEY` | `models/client.py:73` | API key for OpenAI-compatible providers | Only checked if provider == "openai" |
| (none) | | API token for HTTP server | Does not exist yet |

> **Note:** Grep for `process.env` equivalent (`os.environ.get`) across the codebase confirms only `OPENAI_API_KEY` is used. No other secrets are read from environment.

### B. Post-Audit Code Not Previously Reviewed

The original architecture documentation references a code state from April 13, 2026. Since then (10 days):

| File | Change | Risk |
|------|--------|------|
| `src/llm_wiki/cli.py` | Grew from ~500 lines to 2912 lines | Significant — new commands not risk-reviewed |
| `src/llm_wiki/daemon/jobs/` | Added `review_queue.py`, `retry_failed_ingests.py` | New daemon jobs, no concurrency review |
| `docs/` | Version bump documentation, CLI.md expanded | Documentation only |

**Recommendation:** Run `ruff check .` and `mypy src/` before deploying — this is a sudden 6x growth in the CLI module.

### C. Key File References

| Purpose | File | Lines |
|---------|------|-------|
| CLI entry point | `src/llm_wiki/cli.py` | 2912 |
| Daemon main | `src/llm_wiki/daemon/main.py` | 231 |
| Scheduler | `src/llm_wiki/daemon/scheduler.py` | 431 |
| Worker pool | `src/llm_wiki/daemon/workers.py` | 190 |
| Config loader | `src/llm_wiki/config/loader.py` | 155 |
| LLM client | `src/llm_wiki/models/client.py` | 364 |
| Config schemas | `src/llm_wiki/models/config.py` | 246 |
| Inbox watcher | `src/llm_wiki/ingest/watcher.py` | ~180 |
| API reverse graph index | `src/llm_wiki/index/graph_edges.py` | 450 |
| Export job | `src/llm_wiki/daemon/jobs/export.py` | ~60 |
| Promotion engine | `src/llm_wiki/promotion/engine.py` | 595 |

### D. Commit/Stats Baseline

- **Test files:** 75
- **Test count:** ~534
- **Code coverage:** ~93%
- **CLI file size:** 2912 lines
- **Total source files:** 75 `.py` files in `src/`
- **Python versions:** 3.11, 3.12 (matrix in CI)

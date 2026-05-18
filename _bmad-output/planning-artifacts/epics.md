---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-epic-1-stories', 'step-03-epic-2-stories', 'step-03-epic-3-stories', 'step-03-epic-4-placeholder', 'step-04-final-validation']
status: complete
completedAt: '2026-05-17'
revisedAt: '2026-05-17'
inputDocuments:
  - '_bmad-output/planning-artifacts/prd.md'
  - '_bmad-output/planning-artifacts/architecture.md'
  - '_bmad-output/planning-artifacts/prd-validation-report.md'
  - 'docs/IMPLEMENTATION_STATUS.md'
  - 'docs/roadmap.md'
---

# llm_wiki - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for llm_wiki, decomposing the requirements from the PRD and Architecture into implementable stories.

**Critical Context:** V1 library is functionally complete (500+ tests, 93% coverage) but has critical data integrity bugs — non-atomic index writes, no write mutex, and orphaned inbox files on crash — that must be fixed before the service layer is built on top. All core domain logic exists as a Python library. The work ahead is the service pivot (Docker + MCP + REST API), trust layer, cross-domain synthesis, and UX. Since the project is not in production use, fundamental rework is valid scope — we are not constrained by backward compatibility.

## Requirements Inventory

### Functional Requirements

**Knowledge Ingestion (Sprint 1)**
- FR1: The daemon routes sources dropped into the inbox to domains using rules defined in `routing.yaml`; sources matching no rule are held in staging (see FR53)
- FR2: Operators can submit sources for ingestion via MCP, REST, or CLI and receive a job ID
- FR3: The system ingests Claude Code session transcripts (JSONL format) and normalizes them to markdown wiki pages
- FR4: The system ingests plain markdown documents as sources
- FR5: Operators can poll the status of any ingest job by job ID across all three interfaces
- FR6: The system extracts QA pairs from session transcripts as first-class `kind: qa` wiki pages
- FR7: The daemon resumes interrupted ingest batches from a checkpoint without reprocessing already-completed sources
- FR51: The system accepts and durably queues ingest submissions when the daemon is not running, and processes the queue automatically when the daemon next starts
- FR58: Ingest job status `complete` means the resulting pages are committed to the wiki and searchable; an `indexed` timestamp field indicates when the index reflects the new pages

**Knowledge Query & Retrieval (Sprint 1)**
- FR8: Agent harnesses can query the wiki at three depths: quick (index lookup), standard (page content), deep (full synthesis with cross-references)
- FR9: Deep queries return partial results with an explicit `partial: true` flag when synthesis exceeds the timeout threshold
- FR10: Query results include confidence scores, source provenance citations, and contradiction warnings; contradiction warnings include both conflicting claim summaries and the page IDs of conflicting sources
- FR11: Operators and agents can read any single wiki page by page ID or slug, including full frontmatter provenance metadata
- FR12: Operators and agents can list pages filtered by domain, page kind, or tag with cursor-based pagination
- FR54: Deep queries that exceed the timeout threshold before producing any results return a response with `"timed_out": true` alongside `"results": []`, distinguishable from a legitimate empty result set
- FR57: Contradiction warnings in query results include structured claim summaries and the page IDs of the conflicting sources
- FR59: Agents can query across all domains simultaneously in a single call (default); an optional `domain` parameter restricts the query to a specific domain

**Search (Sprint 1-2)**
- FR13: Agent harnesses and operators perform full-text search across all domains, returning ranked results with confidence scores
- FR14: Agent harnesses and operators perform semantic/vector search (when vector extras are installed), returning similarity-ranked results
- FR15: Search results from fulltext and vector indexes are merged into a single ranked list
- FR52: When the vector search dependency is not installed, search returns full-text results with a capability indicator (`"vector_search": false`) rather than an error

**Daemon & Governance (Sprint 1)**
- FR16: The daemon runs all governance jobs on schedule without manual intervention: lint, contradiction detection, staleness detection, export generation, index rebuild
- FR17: The daemon generates structured governance reports readable via CLI
- FR18: Operators can view daemon job schedule, last-run results, and next-run times via MCP, REST, or CLI
- FR19: Operators can trigger an index rebuild manually via MCP, REST, or CLI
- FR20: The daemon flags a contradiction when a new claim directly conflicts with a claim on an existing page — where "directly conflicts" means two pages assert incompatible values for the same subject — and routes conflicts to the review queue before committing to the wiki
- FR21: The daemon detects orphaned and stale pages and surfaces them in governance reports
- FR22: The daemon detects sources routed to the wrong domain and flags them for correction
- FR23: The daemon periodically scans pages for claims lacking a source citation or backlink and flags them in the governance report

**Knowledge Management (Sprint 1-3)**
- FR24: The system maintains an append-only changelog of all page mutations with diff tracking
- FR25: Operators can view and action items in the review queue: approve, reject, or defer via CLI
- FR26: The system applies deterministic merge strategies when new content overlaps existing pages; strategy is determined per-field by the domain's schema configuration in `domains.yaml`; fields without explicit merge configuration use the default merge behavior
- FR27: Operators can manage domain configuration: add domains, set routing rules, define ingestion policies
- FR28: Pages and claims carry confidence scores; low-confidence content is visible and filterable in query results
- FR29: New candidate pages are gated through a promotion queue before being committed to the wiki
- FR53: When a source cannot be routed to any configured domain, it is held in a staging area with a routing-failed status and surfaced in governance reports for manual domain assignment
- FR63: The system logs all queries with their results and query depth; this log is the basis for synthesis cache population and can be queried by operators

**Export & Integration (Sprint 1-2)**
- FR30: Operators can trigger and retrieve AI-consumable exports: `llms.txt`, `llms-full.txt`, JSON-LD graph
- FR31: Exports include freshness metadata (`generated_at`, `page_count`) so consumers can assess staleness
- FR32: Agent harnesses connect via MCP over Streamable HTTP transport (host:port) or stdio transport (process spawn), with no adapter layer required for either
- FR33: The Claude Code integration automatically captures session transcripts via hooks (SessionEnd, PreCompact) into the inbox
- FR34: Operators can install and uninstall Claude Code session capture hooks via CLI

**Service Operations (Sprint 1)**
- FR35: The full service stack (MCP server + REST API + daemon) starts with a single `docker-compose up` command
- FR36: Operators can check service health (daemon status, index freshness) via MCP, REST, or CLI
- FR37: The service exposes an OpenAPI 3.1 spec at `/v1/openapi.json` for REST API autodiscovery
- FR38: MCP clients autodiscover available tools via standard `tools/list`
- FR39: Operators configure the service via host-mounted YAML files without rebuilding the container
- FR40: The daemon recovers from crashes automatically on restart: the scheduler resumes from its last checkpoint, in-progress ingest jobs resume from their saved position, and index integrity is verified before serving queries
- FR41: All index files are written atomically so a crash mid-write never leaves indexes in a partially-written state
- FR55: The service automatically initializes the wiki directory structure on first start if the mounted volume is empty
- FR60: Operators and agents can retrieve the list of configured domains and their metadata (page count, last updated) at runtime via MCP, REST, or CLI
- FR61: `list_pages` supports an `updated_since` filter so agents can efficiently poll for changed pages

**Trust & Provenance (Sprint 2)**
- FR42: Every wiki page claim is tagged as extracted, inferred, or ambiguous at ingest time
- FR43: Pages without valid source citations are automatically marked low-confidence and flagged in governance reports
- FR44: The system scores candidate pages against configurable confidence thresholds before promotion to the wiki

**Cross-Domain Synthesis (Sprint 3)**
- FR45: The system maintains authority scores for pages and entities based on cross-domain reference density
- FR46: Shared entities are promoted to cross-domain status automatically when they appear in multiple domains and meet the configured confidence threshold
- FR47: The system auto-generates cross-domain summary pages for entities appearing in multiple domains, contingent on entity promotion (FR46) being operational
- FR48: The system caches high-value repeated query answers as first-class wiki pages; "high-value" is defined as queries with the same normalized text appearing at least `synthesis_cache_min_hits` times (configurable in `daemon.yaml`, default: 5) within a rolling 30-day window
- FR49: Per-domain dashboards summarize domain health, page count, confidence distribution, and recent changes
- FR50a: The daemon automatically archives topics that exceed the staleness threshold configured in `domains.yaml`
- FR50b: Operators can manually archive any topic via CLI regardless of staleness threshold
- FR62: Pages generated by the synthesis cache are tagged with `kind: synthesis` and include a `source_query` field

### NonFunctional Requirements

**Performance**
- NFR-P1: Quick-depth queries complete in ≤ 200 ms under normal load (single user, ≤ 1,000 pages)
- NFR-P2: Standard-depth queries complete in ≤ 2 s under normal load
- NFR-P3: Deep-depth queries return a response with `partial: true` within the 30 s timeout; never hang indefinitely
- NFR-P4: Ingest throughput: daemon processes at least 10 inbox items per minute under sustained load
- NFR-P5: Full index rebuild completes within 60 s for a wiki of up to 1,000 pages

**Reliability**
- NFR-R1: After a daemon crash and restart, the scheduler, ingest queue, and index integrity are all operational within 60 s — no manual intervention required
- NFR-R2: All index file writes are crash-safe atomic operations; a crash mid-write never leaves a partially-written index on disk
- NFR-R3: Inbox items submitted before a daemon crash are preserved in the durable queue and processed on next start — zero item loss
- NFR-R4: On startup, the daemon performs an index integrity check; if corruption is detected, it triggers an automatic rebuild before serving any queries

**Integration**
- NFR-I1: MCP tool names follow the `verb_noun` convention; all tools are discoverable via `tools/list`
- NFR-I2: REST API conforms to OpenAPI 3.1, published at `/v1/openapi.json`; breaking changes require a new URL path version
- NFR-I3: Every query and status CLI command supports a `--json` flag that emits machine-parseable JSON
- NFR-I4: MCP transport supports both Streamable HTTP (host:port) and stdio (process spawn)

**Operability**
- NFR-O1: `docker-compose up` brings the full stack to operational in ≤ 30 s on a cold start with a pre-warmed image
- NFR-O2: The `/health` endpoint responds within 1 s and accurately reflects daemon liveness, index load status, and scheduler state
- NFR-O3: Domain and daemon config changes take effect on daemon restart with no data loss
- NFR-O4: On first run against an empty volume, the daemon auto-initializes the full `wiki_system/` directory structure

**Data Integrity**
- NFR-D1: Page IDs are deterministic slugs (`{domain}-{title-slug}`); identical inputs always produce the same ID
- NFR-D2: `changelog.jsonl` is append-only; any code path that opens it for write (truncate) is a critical bug
- NFR-D3: Merge strategy application is idempotent — ingesting the same source document twice produces no net change

**Security**
- NFR-S1: The service binds to `0.0.0.0` inside the container; port exposure is controlled by docker-compose port mapping; VM-level network isolation is the security boundary

### Additional Requirements

**P0 Bug Fixes (Sprint 1 prerequisites — must land before service layer):**
- All index `save()` methods must write atomically: write to a temp file, then `os.replace(tmp, target)` — non-atomic writes currently in V1 are a critical bug
- WikiQuery must maintain a `dict[str, threading.Lock]` keyed by index name; all index writes must acquire the per-index lock before calling `save()` — no write mutex exists in V1
- Inbox recovery on startup: files orphaned in `inbox/processing/` on crash must be automatically recovered before daemon begins processing new items

**Daemon Jobs (Sprint 1 — all wired into Docker container):**
- `InboxScanJob` (15s) — pick up new files from `inbox/new/` (FR1, FR7, FR51)
- `QueueToPagesJob` (15min) — promote staged candidates to wiki pages (FR26, FR29)
- `RetryFailedIngestsJob` (30min) — re-queue items in `inbox/failed/` that are eligible for retry; respects `max_retries` per item; emits governance report entry for items that exhaust retries (FR7, FR40)
- `IndexRebuildJob` (30min) — rebuild all indexes + `reload_vector_index()` (FR19, NFR-R4)
- `ExportJob` (60min) — regenerate `llms.txt`, JSON-LD, graph (FR30, FR31)
- `GovernanceJob` (60min) — lint, contradiction detection, staleness, routing mistakes (FR16-23)
- `ReviewQueueJob` (60min) — surface pending promotion candidates (FR25, FR29)
- `StalenessJob` (24h) — flag pages exceeding `staleness_threshold_days` (FR21, FR50a)
- `DuplicatesJob` (24h) — near-duplicate detection
- `PromotionJob` (24h) — score pages for cross-domain promotion (FR45, FR46; requires `cross_domain_promotion: true`)

**Service Layer (Sprint 1 additions):**
- New dependencies: `uv add fastapi uvicorn mcp`
- MCP server using Anthropic `mcp` Python SDK; stdio + Streamable HTTP transport; tools in `src/llm_wiki/mcp/tools.py`
- FastAPI REST API; routers in `src/llm_wiki/api/routers/` (health, query, ingest, search, pages, export, domains); all routes under `/v1` prefix
- WikiQuery as singleton on `app.state`; single instantiation in FastAPI lifespan; never per-request
- Async synthesis engine as `async def` generator yielding `SynthesisChunk`; timeout enforced via `asyncio.timeout(30.0)` — never a synchronous function
- All I/O-touching service calls in async route functions must use `asyncio.to_thread()`
- Error propagation through `src/llm_wiki/api/errors.py` mapper — never `raise HTTPException(...)` inline for known error types
- SQLite query log at `wiki_system/state/query_log.db` (Python stdlib `sqlite3`)

**Docker/Container (Sprint 1):**
- Multi-stage Docker build; uid 1000 `llmwiki` user
- supervisord managing two processes: uvicorn (port `$WIKI_PORT`, default 3050; REST + MCP Streamable HTTP) + WikiDaemon
- Host-mounted volumes: `./wiki_data:/wiki`, `./config:/config:ro`
- `WIKI_ROOT=/wiki` set in Dockerfile
- `stopwaitsecs=30` for daemon supervisord process (mid-write crash safety)

**Multi-User Domain Scoping (Sprint 1, design-now):**
- `domains.yaml` schema: add `scope: shared|personal` and optional `owner: {profile_id}` fields validated by Pydantic
- `WikiQuery.search()`: add `scope_to_profile: str | None` parameter for profile-based domain scoping
- MCP `query` tool: `profile_id` parameter; REST: `X-Profile-Id` header via `Depends(get_profile_id)`
- Domain scope logic lives in `WikiQuery.search()` exclusively — never filter domains in route or tool code

**Fundamental Rework Scope (since not in production):**
- Given no production users, any V1 pattern that conflicts with the target architecture is valid rework scope
- The service pivot is an opportunity to correct architectural debt without migration risk

### UX Design Requirements

N/A — this is a backend API service (MCP + REST + CLI). No UI requirements for Sprint 1-3. Sprint 4 introduces a web UI; UX requirements will be captured at that time.

### FR Coverage Map

| FR                       | Epic   | Notes                                                                                                                     |
| ------------------------ | ------ | ------------------------------------------------------------------------------------------------------------------------- |
| FR1, FR3, FR4, FR6       | Epic 1 | V1 exists; wired into Docker service                                                                                      |
| FR2, FR5, FR58           | Epic 1 | New REST + MCP ingest/status endpoints                                                                                    |
| FR7, FR40, FR41, FR51    | Epic 1 | P0 fixes: atomic writes, crash recovery, checkpoint resume                                                                |
| FR8-12, FR54, FR57, FR59 | Epic 1 | New REST + MCP query endpoints                                                                                            |
| FR13, FR15               | Epic 1 | V1 fulltext exists; expose via REST/MCP                                                                                   |
| FR14, FR52               | Epic 2 | Vector search wired into service + capability indicator                                                                   |
| FR16-23                  | Epic 1 | V1 daemon jobs; run in Docker; expose status via REST/MCP; FR17/FR18 also covered by Governance CLI commands (Story 1.15) |
| FR24-27, FR29            | Epic 1 | V1 exists; expose changelog/review/merge/domains                                                                          |
| FR28                     | Epic 2 | Confidence scores surfaced in all query results                                                                           |
| FR30-31                  | Epic 1 | V1 exports; expose via REST/MCP + freshness metadata                                                                      |
| FR32                     | Epic 1 | New MCP server with Streamable HTTP + stdio transports                                                                    |
| FR33-34                  | Epic 1 | Claude Code hooks; verify CLI commands work in Docker context                                                             |
| FR35-39                  | Epic 1 | Docker + supervisord + YAML config mounts                                                                                 |
| FR42-44                  | Epic 2 | Trust/confidence tagging at ingest; citation enforcement                                                                  |
| FR45-50b                 | Epic 3 | Cross-domain entity promotion, synthesis, dashboards, archive                                                             |
| FR53                     | Epic 1 | Staging area for unrouted sources                                                                                         |
| FR55                     | Epic 1 | Auto-init wiki directory on first start                                                                                   |
| FR60-61                  | Epic 1 | Domain list endpoint; updated_since filter on list_pages                                                                  |
| FR62                     | Epic 3 | Synthesis cache pages tagged kind:synthesis                                                                               |
| FR63                     | Epic 1 | SQLite query log at state/query_log.db                                                                                    |

## Epic List

### Epic 1: Docker Service — "Connect Any Agent Harness in 15 Minutes"
A developer runs `docker-compose up`, points their MCP config at `{host}:{port}`, and has a fully-governed knowledge service running — inbox processing, governance daemon, query interface, and all exports included. This epic includes the P0 bug fixes (atomic writes, write mutex, inbox recovery) as its first stories since they are prerequisites for a reliable service.
**FRs covered:** FR1-13, FR15-27, FR29-41, FR51, FR53-55, FR57-61, FR63
**NFRs:** All P, R, I, O, D, S NFRs

### Epic 2: Trust & Verification — "Know What to Trust"
Operators and agents can see confidence scores on every page and claim. Low-confidence content is flagged before it corrupts downstream reasoning. Vector/semantic search is available alongside full-text.
**FRs covered:** FR14, FR28, FR42-44, FR52
**NFRs:** NFR-P4 (ingest throughput)

### Epic 3: Cross-Domain Intelligence — "Knowledge That Compounds"
Entities shared across domains surface automatically. Repeated high-value queries become cached wiki pages. Per-domain dashboards show health at a glance.
**FRs covered:** FR45-50b, FR62 (uses FR63 from Epic 1)
**NFRs:** NFR-P5 (index rebuild at scale)

### Epic 4: Web UI & Operations — "Operate and Browse as a Human" *(V4 — future)*
A browser-based UI for search, browse, graph visualization, and daemon control. First epic with human-facing interface.
**FRs covered:** V4 features (not yet specified in PRD)

## Epic 1: Docker Service — "Connect Any Agent Harness in 15 Minutes"

A developer runs `docker-compose up`, points their MCP config at `{host}:{port}`, and has a fully-governed knowledge service running — inbox processing, governance daemon, query interface, and all exports included. P0 bug fixes land as the first stories, hardening the foundation before the service layer is built on top.

**Story execution order is significant:** Stories 1.1 and 1.2 fix critical data integrity bugs and must complete before any story that runs V1 daemon code (1.3 onward). Story 1.3 (Docker) and 1.4 (FastAPI skeleton) establish the container and service foundation; all endpoint and MCP stories depend on them. Story 1.9 (domain scoping) is deferred until after REST and MCP surfaces exist. Story 1.5 (feature flags) must land after Story 1.4 and before Story 1.6 so that extraction paths are flag-controlled before any endpoint code is written. Stories 1.16 and 1.17 (performance tests) are sprint acceptance gates — a sprint is not done until these pass.

### Story 1.1: Atomic Index Writes and Write Mutex

As a wiki operator,
I want all index files written atomically and protected by a per-index mutex,
So that daemon crashes never corrupt indexes and concurrent daemon workers never produce inconsistent index state.

**Acceptance Criteria:**

**Given** any index `save()` method is called
**When** it writes to disk
**Then** it uses the tmp→os.replace pattern: write to `NamedTemporaryFile` in the same directory, then `os.replace(tmp, target)`
**And** no index `save()` method uses `open(path, 'w')` directly

**Given** `WikiQuery` is initialized
**When** the instance is created
**Then** it maintains a `dict[str, threading.Lock]` keyed by index file name (e.g., `"fulltext"`, `"vector"`, `"metadata"`, `"backlinks"`, `"graph_edges"`)

**Given** any index write is triggered via `WikiQuery` methods (`add_page`, `remove_page`)
**When** the write begins
**Then** the per-index lock is acquired before calling `save()` and released after — even if `save()` raises

**Given** `IndexRebuildJob` runs its full rebuild sweep
**When** it executes
**Then** it acquires all index locks before starting the sweep and releases all after completion
**And** it is the only code path that bypasses `WikiQuery` methods and directly calls index `save()` — all other callers go through `WikiQuery`

**Given** two daemon workers attempt to write the same index simultaneously
**When** the second arrives at the lock
**Then** it blocks until the first completes — no data race, no silent corruption

**Given** a process crash occurs mid-write to any index file
**When** the service restarts
**Then** no index file is in a partially-written state — the old file remains intact until `os.replace` succeeds atomically

### Story 1.2: Inbox Recovery and Index Integrity on Startup

As a wiki operator,
I want the daemon to automatically recover from crashes and verify index integrity on every startup,
So that the service resumes without data loss or silent corruption after any restart.

**Acceptance Criteria:**

**Given** files exist in `inbox/processing/` when the daemon starts
**When** the daemon initializes
**Then** all files in `processing/` are moved back to `inbox/new/` for reprocessing before the scheduler starts
**And** a warning is logged for each recovered file indicating it was found in an inconsistent state

**Given** the daemon starts (clean or after crash)
**When** it initializes
**Then** it runs an index integrity check before beginning to serve queries or process inbox items
**And** the integrity check verifies each expected index file exists and is non-empty (not a full parse — just existence and size)

**Given** the integrity check detects a missing or zero-byte index file
**When** this occurs
**Then** the daemon triggers a full `IndexRebuildJob` synchronously before accepting any work
**And** the rebuild completes within 60s for a wiki of up to 1,000 pages (NFR-P5)

**Given** a clean startup with no corruption and no orphaned inbox files
**When** the daemon starts
**Then** no rebuild is triggered and the daemon is fully operational within 60s (NFR-R1)

**Given** the daemon restarts after a crash mid-ingest
**When** inbox recovery runs
**Then** no file is permanently lost — all pre-crash inbox submissions are in `inbox/new/` and will be processed on the next scan cycle (NFR-R3)

### Story 1.3: Docker Container and Process Management

**Prerequisite:** Stories 1.1 and 1.2 must be complete — the daemon that runs inside this container has critical data integrity bugs until those stories land; building the container before the P0 fixes are in place exposes a broken daemon.

As a developer,
I want to start the entire LLM Wiki stack with a single command,
So that I can run a fully-operational wiki service without any Python environment setup or manual process management.

**Acceptance Criteria:**

**Given** the repo with a pre-built Docker image
**When** `docker-compose up` is run
**Then** both uvicorn and WikiDaemon are running and healthy within 30s (NFR-O1)

**Given** the container starts
**When** supervisord initializes
**Then** process 1 is uvicorn serving `0.0.0.0:$WIKI_PORT` (REST + MCP Streamable HTTP) and process 2 is WikiDaemon

**Given** WikiDaemon crashes at runtime
**When** supervisord detects the exit
**Then** it restarts the daemon automatically (`autorestart=true`, `startretries=5`)

**Given** the supervisord config for the daemon process
**When** audited
**Then** `stopwaitsecs=30` — never lower, because the daemon may be mid-write when a stop signal arrives

**Given** uvicorn crashes at runtime
**When** supervisord detects the exit
**Then** it restarts uvicorn automatically (`autorestart=true`, `startretries=3`)

**Given** the container
**When** running
**Then** all processes run as uid 1000 (`llmwiki` user) — not root

**Given** `docker-compose.yml`
**When** defined
**Then** it mounts `./wiki_data:/wiki` (read-write) and `./config:/config` (read-only), and sets `WIKI_ROOT=/wiki`

**Given** `daemon.yaml` or `domains.yaml` is modified on the host
**When** the container is restarted
**Then** the new config takes effect without rebuilding the image (NFR-O3)

**Given** `./wiki_data` does not exist on the host
**When** `docker-compose up` is run
**Then** docker creates the directory and the container auto-initializes the wiki structure inside it

### Story 1.4: FastAPI Application Skeleton and Error Handling

As a service developer,
I want a FastAPI application with proper lifespan management, a singleton WikiQuery, and centralized error handling,
So that all REST and MCP surfaces share a reliable, consistent service foundation with no duplicated error logic.

**Acceptance Criteria:**

**Given** the FastAPI app lifespan starts
**When** it runs
**Then** `_maybe_init_wiki_root(wiki_root)` is called **before** `WikiConfig.load()` — a fresh empty volume raises `FileNotFoundError` if this order is reversed

**Given** the FastAPI app lifespan runs
**When** complete
**Then** `WikiQuery` is instantiated exactly once and stored on `app.state.wiki`; the FAISS index loads once here

**Given** a route calls `Depends(get_wiki)`
**When** executed
**Then** it returns `app.state.wiki` — the same singleton for every request; no new `WikiQuery` is constructed

**Given** a `WikiNotFoundError` is raised anywhere in a route or service call
**When** the exception handler fires
**Then** it returns HTTP 404 with body `{"error_code": "WIKI_NOT_FOUND", "message": "...", "rebuild_hint": false}`

**Given** an `IndexStaleError` is raised
**When** handled
**Then** it returns HTTP 503 with `"rebuild_hint": true` in the response body

**Given** a `DomainUnknownError` raised from a user-supplied POST body field
**When** handled
**Then** it returns HTTP 422 (not 404) using the status override pattern in `errors.py`

**Given** a `QueryTimeoutError` occurs during a deep query
**When** it occurs
**Then** it is handled as a normal response branch returning `{"timed_out": true, "partial": true, "results": [...]}` — it is **not** in `ERROR_MAP` and does not become an HTTP error

**Given** any route function calls an I/O-touching service method (disk, FAISS, SQLite)
**When** audited
**Then** every such call is wrapped in `asyncio.to_thread()` — the event loop is never blocked

**Given** all API Pydantic models
**When** defined
**Then** they live in `src/llm_wiki/api/models.py` and are named `{Resource}Response` or `{Resource}Request` — never `Schema`, `Model`, or `Out`

**Given** the FastAPI lifespan completes
**When** the service starts
**Then** an `mcp.Server` instance is created, all MCP tools are registered via `tools.py`, and the Streamable HTTP transport is mounted at `/mcp` on the uvicorn app — the MCP server shares `app.state.wiki` with the REST routes

**Given** the service is fully initialized
**When** the scheduler starts
**Then** `IndexRebuildJob` is constructed with the `WikiQuery` singleton: `scheduler.add_job(IndexRebuildJob(wiki=app.state.wiki), ...)` — the job holds a reference to the same singleton used by all routes


### Story 1.5: Feature Flag System

As an operator,
I want a feature flag system in `daemon.yaml` to enable or disable optional capabilities,
So that the service works fully without any LLM dependency by default and new capabilities can be enabled and tested independently.

**Acceptance Criteria:**

**Given** `daemon.yaml` contains a `features:` block
**When** the service starts
**Then** `WikiConfig` loads and validates all flags; unknown flags are rejected at startup with a clear error

**Given** `features.llm_extraction: false` (default)
**When** any extraction pipeline step runs
**Then** it uses heuristic fallbacks (TF-IDF tags, first-paragraph summary, skip claims) — no LLM client is instantiated, no `models.yaml` is required

**Given** `features.llm_extraction: true`
**When** the service starts
**Then** it reads `models.yaml`, validates the provider config, and instantiates the LLM client; startup fails with a clear error if `models.yaml` is missing or the provider config is invalid

**Given** `features.vector_search: false`
**When** search is executed
**Then** it returns full-text results only with `"vector_search": false` — no error, identical to the missing-dependency path (FR52)

**Given** `features.synthesis_cache: false` or `features.cross_domain_promotion: false`
**When** the daemon scheduler initializes
**Then** the corresponding jobs are not registered and cannot be triggered manually

**Given** `features.lazy_vector_load: false` (default)
**When** the service starts
**Then** the FAISS index loads immediately in the FastAPI lifespan — vector search is available from first request

**Given** `features.lazy_vector_load: true`
**When** the service starts
**Then** the FAISS index is not loaded during lifespan; it loads on the first search call; cold start is faster but the first search pays the load cost

**Given** any health or status response
**When** returned
**Then** it includes `llm_extraction_enabled: bool` and `vector_search_enabled: bool` capability indicators

### Story 1.6: REST Health, Daemon, and Ingest Endpoints

As an operator or integration,
I want REST endpoints to monitor service health, manage the daemon, and submit content for ingestion,
So that I can operate and integrate with the wiki programmatically without a CLI.

**Acceptance Criteria:**

**Given** `GET /v1/health`
**When** called
**Then** it responds within 1s (NFR-O2) with daemon liveness, index load status, and scheduler state

**Given** `GET /v1/daemon/status`
**When** called
**Then** it returns job schedule, last-run results, and next-run times for all registered daemon jobs (FR18)

**Given** `GET /v1/daemon/jobs`
**When** called
**Then** it returns job execution history read from `state/jobs.json`

**Given** `POST /v1/daemon/jobs/index-rebuild`
**When** called
**Then** it triggers an index rebuild asynchronously and returns `{"job_id": "...", "status": "queued"}` (FR19)

**Given** `POST /v1/ingest` with a valid source path or content body
**When** called
**Then** it returns `{"job_id": "...", "status": "queued"}` and the daemon processes the submission (FR2)

**Given** `GET /v1/ingest/{job_id}` with a valid job ID
**When** called
**Then** it returns `{job_id, status, source_path, domain, page_ids, indexed, message}` matching the `IngestStatusResponse` schema (FR5, FR58)

**Given** `GET /v1/ingest/{job_id}` with an unknown job ID
**When** called
**Then** it returns HTTP 404 `WIKI_NOT_FOUND`

**Given** `GET /v1/domains`
**When** called
**Then** it returns the list of configured domains with `page_count` and `last_updated` metadata per domain (FR60)

**Given** all REST responses
**When** any endpoint is called
**Then** the response includes the `X-LLM-Wiki-Version` header

### Story 1.7: REST Query, Search, Pages, and Export Endpoints

As an agent or operator using HTTP,
I want REST endpoints for querying knowledge, searching, reading pages, and retrieving exports,
So that I can access the full wiki capability surface from any HTTP client without MCP.

**Acceptance Criteria:**

**Note on confidence scores:** Sprint 1 returns the confidence values already stored in V1 page frontmatter — no new computation. Sprint 2 (Stories 2.1/2.2) upgrades the confidence computation model. Sprint 1 ACs below test that the `confidence` field is present and passes through correctly, not that the values are accurate.

**Given** `POST /v1/query` with `depth: "quick"`
**When** called under normal load
**Then** it responds in ≤200ms (NFR-P1) with results including `confidence`, `provenance`, and `contradictions`

**Given** `POST /v1/query` with `depth: "standard"`
**When** called under normal load
**Then** it responds in ≤2s (NFR-P2)

**Given** `POST /v1/query` with `depth: "deep"`
**When** called
**Then** it always returns `{"job_id": "...", "status": "queued"}` immediately — never blocks (FR8)

**Given** `GET /v1/query/{job_id}` is called while the job is running
**When** called
**Then** it returns `{"status": "running", "job_id": "..."}` and a `X-Job-TTL: 300` header indicating the job record expires 5 minutes after creation

**Given** `GET /v1/query/{job_id}` when the job completes within 30s
**When** called after completion
**Then** it returns `{"partial": false, "timed_out": false, "results": [...]}` with full synthesis — identical schema to a synchronous quick/standard response

**Given** `GET /v1/query/{job_id}` when synthesis exceeds 30s
**When** the timeout fires and the polled result is retrieved
**Then** it returns `{"partial": true, "timed_out": true, "results": [...whatever completed...]}` — never hangs the caller (NFR-P3, FR9, FR54)

**Given** `GET /v1/query/{job_id}` when synthesis times out before producing any results
**When** called
**Then** `results` is `[]` and `timed_out: true` — distinguishable from a legitimate empty result set (FR54)

**Given** `GET /v1/query/{job_id}` is called after the job completes
**When** called within the 5-minute TTL
**Then** it returns the full query result — identical schema to the synchronous `POST /v1/query` response

**Given** `GET /v1/query/{job_id}` is called after the TTL expires or after a uvicorn restart
**When** called
**Then** it returns HTTP 404 `WIKI_NOT_FOUND` — job state is in-memory only and does not survive restarts

**Given** `GET /v1/search?q=<text>`
**When** called
**Then** it returns merged full-text and vector results (when available), each with confidence scores; response body includes `"vector_search": bool` (FR13, FR15, FR52)

**Given** `GET /v1/pages/{page_id}` when the page exists
**When** called
**Then** it returns full page content plus all frontmatter provenance metadata (FR11)

**Given** `GET /v1/pages/{page_id}` when the page does not exist
**When** called
**Then** it returns HTTP 404 `WIKI_NOT_FOUND`

**Given** `GET /v1/pages` with `?domain=<d>&kind=<k>&cursor=<token>&limit=50`
**When** called
**Then** it returns filtered, paginated results with `next_cursor` and `total_hint` (FR12)

**Given** `POST /v1/export` followed by `GET /v1/export/{format}`
**When** the export exists
**Then** the GET returns export content with `generated_at`, `page_count`, and `Last-Modified` header (FR30, FR31)

**Given** `GET /v1/export/{format}` before any export has been generated
**When** called
**Then** it returns HTTP 404 `EXPORT_NOT_READY`

### Story 1.8: MCP Server and All Tools

As an agent harness,
I want to connect to LLM Wiki over MCP and use all wiki tools via Streamable HTTP or stdio,
So that I can query, ingest, search, and manage wiki pages from any MCP-compatible harness without HTTP clients.

**Acceptance Criteria:**

**Given** the MCP server is running
**When** a harness connects via Streamable HTTP at `http://{host}:{port}/mcp`
**Then** `tools/list` returns all 7 tools: `query`, `ingest`, `ingest_status`, `search`, `read_page`, `list_pages`, `export` (FR38) — Epic 3 (Story 3.5) adds `domain_dashboard` as an 8th tool

**Given** a harness spawns the service as a subprocess (stdio transport)
**When** it calls `tools/list`
**Then** all 7 tools are returned identically to the Streamable HTTP transport (FR32, NFR-I4) — Epic 3 brings the total to 8

**Given** the `query` MCP tool is called with `depth: "quick"` or `depth: "standard"`
**When** executed
**Then** it calls the same underlying service method as `POST /v1/query` and returns the same response schema

**Given** the `query` MCP tool is called with `depth: "deep"` and synthesis exceeds 30s
**When** the timeout fires
**Then** it returns `partial: true, timed_out: true` with partial results — never hangs (FR9)

**Given** the `query` MCP tool is called with a `profile_id` parameter
**When** executed
**Then** it passes `scope_to_profile=profile_id` to `WikiQuery.search()` for multi-user domain scoping

**Given** the `ingest` MCP tool is called with a source
**When** executed
**Then** it returns `{job_id, status: "queued"}` using the same service as `POST /v1/ingest`

**Given** any MCP tool raises a `WikiError`
**When** the error occurs
**Then** it returns a JSON-RPC error object with a numeric `code` and a `message` matching the `error_code` string

**Given** all MCP tool definitions
**When** audited
**Then** they live in `src/llm_wiki/mcp/tools.py` and call the same service methods as the equivalent REST routes — no duplicated business logic in `server.py`

**Given** all MCP tool names
**When** listed
**Then** they follow `verb_noun` snake_case convention: `query`, `ingest`, `search`, `read_page`, `list_pages`, `export` (NFR-I1); `ingest_status` is a grandfathered exception — used consistently across all interfaces; renaming would be a breaking change

### Story 1.9: Multi-User Domain Scoping

**Prerequisite:** Stories 1.6, 1.7, and 1.8 must be complete — this story modifies both REST routes and MCP tools to pass profile scoping through to `WikiQuery.search()`. Implementing it before the REST and MCP surfaces exist requires rework.

As a household operator,
I want domains to carry a scope and optional owner field, and queries to be filterable by profile,
So that household knowledge stays separate from personal knowledge and each member only sees what they should.

**Acceptance Criteria:**

**Given** a `domains.yaml` entry with `scope: shared`
**When** the config is loaded and validated by Pydantic
**Then** it passes validation without error

**Given** a `domains.yaml` entry with `scope: personal` and `owner: marc`
**When** the config is loaded
**Then** both fields are validated and accessible on the domain config object

**Given** a `domains.yaml` entry with no `scope` field
**When** loaded
**Then** it defaults to `scope: shared` — backward compatible with all existing domain configs

**Given** `WikiQuery.search()` is called with `scope_to_profile="marc"`
**When** executed
**Then** results are merged from the `household` domain and the `user-marc` domain only — all other personal domains are excluded

**Given** `WikiQuery.search()` is called with `scope_to_profile=None`
**When** executed
**Then** it queries all configured domains — default behavior, no regression from current behavior

**Given** `WikiQuery.search()` is called with an explicit `domain="household"` parameter
**When** executed
**Then** it queries only the `household` domain regardless of the `scope_to_profile` value

**Given** any REST route or MCP tool that calls search
**When** audited
**Then** domain scope filtering logic is absent from route/tool code — it lives exclusively in `WikiQuery.search()`

**Given** the calling harness sends `X-Profile-Id` (REST) or `profile_id` (MCP)
**When** received
**Then** llm-wiki trusts the value without validation — the calling harness is responsible for identity

### Story 1.10: Auto-Init Wiki on First Start

As an operator,
I want the wiki to initialize its own directory structure on first run,
So that setup requires zero manual steps.

**Acceptance Criteria:**

**Given** an empty host directory mounted at `/wiki`
**When** the service starts for the first time
**Then** `wiki_system/` and all required subdirectories are created before any query is served (FR55, NFR-O4)

**Given** `_maybe_init_wiki_root()` is called on a volume that is already initialized
**When** executed
**Then** it is idempotent — no existing directories or files are re-created, overwritten, or corrupted

**Given** the init function is called
**When** audited
**Then** it is the first call in the FastAPI lifespan, before `WikiConfig.load()` — calling it after raises `FileNotFoundError` on a fresh volume

### Story 1.11: OpenAPI Spec and CI Contract Gate

As a developer or integration,
I want the REST API contract published as an OpenAPI 3.1 spec and validated in CI,
So that integrations can discover all endpoints automatically and API drift is caught before it reaches collaborators.

**Acceptance Criteria:**

**Given** `GET /v1/openapi.json`
**When** called in any environment
**Then** it returns a valid OpenAPI 3.1 specification describing all REST endpoints and their request/response schemas (FR37)

**Given** `scripts/export_openapi.py`
**When** run in CI
**Then** it regenerates `docs/openapi.json` and the CI step fails if the spec has drifted from the committed version — preventing silent API contract drift

**Given** the committed `docs/openapi.json`
**When** a developer is offline
**Then** they can reference the committed spec without running the service

### Story 1.12: SQLite Query Log

As an operator and future synthesis cache (Epic 3),
I want every query logged to a SQLite database with its result metadata and a defined retention policy,
So that repeated high-value queries can be identified and cached as wiki pages, operators can audit query patterns, and the log does not grow unbounded.

**Acceptance Criteria:**

**Given** any query is executed via MCP, REST, or CLI
**When** it completes
**Then** a row is appended to `wiki_system/state/query_log.db` with columns: `query_hash`, `query_text`, `depth`, `domains` (JSON array), `result_count`, `confidence_avg`, `timestamp` (FR63)

**Given** the query log write
**When** executed in an async route
**Then** it runs inside `asyncio.to_thread()` and the SQLite connection uses `check_same_thread=False`

**Given** `query_log.db` does not yet exist
**When** the first query is logged
**Then** the database file and schema are created automatically — no manual migration step required

**Given** the `query_log.db` schema
**When** created
**Then** it has a composite index on `(query_hash, timestamp)` to support efficient repeated-query analysis at scale

**Given** the same query text is submitted multiple times
**When** logged
**Then** all rows share the same `query_hash` — computed as a deterministic hash of normalized (lowercased, stripped) query text

**Given** the query log write fails (e.g., disk full)
**When** the error occurs
**Then** the exception is caught, logged to stderr, and the query response is still returned to the caller — logging never blocks or fails the query

**Given** the daemon's governance sweep runs
**When** it executes
**Then** it deletes query log rows older than 90 days — the rolling retention window required by FR48's 30-day synthesis cache analysis; `synthesis_cache_log_retention_days` in `daemon.yaml` configures this value (default: 90)

**Given** `llm-wiki govern query-log --stats [--json]`
**When** run
**Then** it prints row count, oldest entry date, and top 10 most-repeated queries with hit counts

### Story 1.13: Claude Code Hooks

As a Claude Code user,
I want session capture hooks that automatically feed Claude sessions into the wiki,
So that the wiki stays current without manual ingest steps.

**Acceptance Criteria:**

**Given** `llm-wiki hooks install` is run
**When** executed
**Then** Claude Code `SessionEnd` and `PreCompact` hooks are installed that capture transcripts to `inbox/new/`

**Given** `llm-wiki hooks uninstall` is run
**When** executed
**Then** the hooks are removed cleanly without affecting any other Claude Code configuration

**Given** the hooks are installed and a Claude Code session ends
**When** the `SessionEnd` hook fires
**Then** the transcript is written to `inbox/new/` as a JSONL file and the daemon ingests it on the next scan cycle (FR33)

**Given** `llm-wiki hooks install` is run when hooks are already installed
**When** executed
**Then** it is idempotent — no duplicate hooks are created

### Story 1.14: List Pages Time Filter

As an agent developer,
I want an efficient way to poll for recently-changed pages,
So that agents can sync incrementally without fetching the full page list.

**Acceptance Criteria:**

**Given** `GET /v1/pages?updated_since=2026-05-17T00:00:00Z`
**When** called
**Then** only pages with `updated_at` after the specified ISO8601 timestamp are returned (FR61)

**Given** `GET /v1/pages?updated_since=not-a-date`
**When** called
**Then** it returns HTTP 422 with an appropriate validation error message

**Given** the `list_pages` MCP tool called with an `updated_since` parameter
**When** executed
**Then** it applies the same time filter as the REST endpoint using the same service method

### Story 1.15: Governance CLI Commands

As an operator,
I want CLI commands to read governance reports and trigger governance runs manually,
So that I can inspect daemon health, review what was flagged, and run governance on demand without waiting for the next scheduled job.

**Acceptance Criteria:**

**Given** `llm-wiki govern status [--json]`
**When** called
**Then** it prints the last-run timestamp, outcome (pass/fail/warnings), and warning count for each governance job (lint, contradictions, staleness, routing) — sourced from `state/jobs.json`

**Given** `llm-wiki govern run [lint|contradictions|staleness|all] [--json]`
**When** called
**Then** it triggers the specified governance job synchronously and prints the structured report when complete; `--all` runs all jobs in sequence

**Given** `llm-wiki govern report [--domain <name>] [--json]`
**When** called
**Then** it prints the latest governance report from `reports/`, filtered by domain if specified

**Given** `llm-wiki govern run` is called while the daemon is running the same job
**When** executed
**Then** it waits for the lock or fails with a clear message — it does not silently run a concurrent governance sweep

**Given** any governance CLI command is run with `--json`
**When** executed
**Then** it emits machine-parseable JSON to stdout (NFR-I3)

**Given** `GET /v1/daemon/status`
**When** audited
**Then** it returns governance job last-run results alongside all other daemon jobs — governance is not a separate REST resource (FR18)

**Given** a source dropped into the inbox matches no rule in `routing.yaml`
**When** the inbox scan job processes it
**Then** the file is moved to `inbox/staging/` and a governance report entry is written with `status: routing-failed` and the source path (FR53)

**Given** `llm-wiki govern report` or `GET /v1/daemon/status`
**When** routing-failed items exist in `inbox/staging/`
**Then** they appear in the governance report output with their staging path, arrival time, and `status: routing-failed` — operators can identify and manually assign them (FR53)

**Given** a routing-failed file exists in `inbox/staging/`
**When** the operator runs `llm-wiki ingest <path> --domain <name>`
**Then** the file is moved from `inbox/staging/` to `inbox/new/` and processed normally — the staging area is the only durable hold state for unrouted sources (FR53)

### Story 1.16: Query Performance Baseline Tests

As a developer,
I want automated performance tests covering all three query depths,
So that regressions in query latency are caught before a sprint is declared done.

**Acceptance Criteria:**

**Given** a seeded test wiki of 100 pages across 3 domains
**When** `POST /v1/query` is called with `depth: "quick"`
**Then** the response arrives in ≤ 200ms (NFR-P1); test asserts on `time.perf_counter()` delta

**Given** the same seeded wiki
**When** `POST /v1/query` is called with `depth: "standard"`
**Then** the response arrives in ≤ 2s (NFR-P2)

**Given** the same seeded wiki with `llm_extraction: false`
**When** `POST /v1/query` is called with `depth: "deep"` and the job completes
**Then** the total time from submission to result (including poll) is ≤ 30s (NFR-P3)

**Given** the performance tests
**When** run in CI
**Then** they are tagged `@pytest.mark.performance` and excluded from the default `pytest` run; included via `pytest -m performance`

### Story 1.17: Container Cold Start Test

As a developer,
I want an automated test that verifies the full Docker stack starts within the NFR budget,
So that Docker or supervisord configuration regressions are caught before release.

**Acceptance Criteria:**

**Given** `docker-compose up --build` against a fresh empty volume
**When** the container starts
**Then** `GET /v1/health` returns HTTP 200 within 30s of container start (NFR-O1)

**Given** the cold start test
**When** run
**Then** it is tagged `@pytest.mark.integration` and requires Docker; skipped automatically when Docker is not present

**Given** the health response
**When** examined
**Then** it includes `daemon_running`, `index_loaded`, `llm_extraction_enabled`, and `vector_search_enabled` fields

## Epic 2: Trust & Verification — "Know What to Trust"

Operators and agents can see confidence scores on every page and claim. Every claim is tagged at ingest as extracted, inferred, or ambiguous. Pages lacking source citations are automatically flagged. Vector/semantic search is available alongside full-text, with a clear capability indicator when it is not installed.

**Story execution order is significant:** Story 2.1 establishes trust tags at ingest time. Story 2.2 uses those tags to enforce citation rules and gate promotion. Story 2.3 surfaces the resulting confidence scores in query and search results. Story 2.4 (vector search) is independent of the trust pipeline and can be implemented in parallel with any of 2.1–2.3.

### Story 2.1: Claim Trust Tagging at Ingest

As an operator or auditor,
I want every claim extracted from an ingested source to be tagged as extracted, inferred, or ambiguous,
So that agents and governance tools know the epistemological status of every fact in the wiki before trusting it.

**Acceptance Criteria:**

**Given** a markdown document is ingested
**When** claims are extracted from it
**Then** each claim is tagged with one of: `extracted` (directly stated in source), `inferred` (derived from source by reasoning), or `ambiguous` (unclear provenance or conflicting signals)

**Given** a Claude Code session transcript is ingested
**When** QA pairs and claims are extracted
**Then** each claim carries a trust tag reflecting its origin — `extracted` for direct Q&A pairs, `inferred` for synthesized summaries

**Given** a page is committed to the wiki
**When** its frontmatter is written
**Then** claims include their trust tags as part of the stored page metadata — the tags survive index rebuilds and are returned in `GET /v1/pages/{page_id}`

**Given** the trust tagging logic
**When** implemented
**Then** it is deterministic and algorithmic — no LLM calls; the same source document always produces the same tags

**Given** a claim with tag `ambiguous`
**When** surfaced in query results or governance reports
**Then** it is distinguishable from `extracted` and `inferred` claims — the tag is present in the result payload, not just in stored metadata

**Given** the claim tagging implementation
**When** audited
**Then** it runs inside the existing ingest pipeline (extraction stage) — no new daemon job is required; tagging happens at ingest time, not retroactively (FR42)

### Story 2.2: Citation Enforcement and Confidence Gating

As an operator running governance,
I want pages without valid source citations to be automatically marked low-confidence and surfaced in governance reports, and candidate pages to be scored against a threshold before promotion,
So that hallucinated or unsourced content cannot silently enter the wiki as trusted knowledge.

**Prerequisite:** Story 2.1 must be complete — citation enforcement and confidence gating operate on pages that carry trust tags.

**Acceptance Criteria:**

**Given** a page in the wiki has no valid source citations (empty or missing `sources` field in frontmatter)
**When** the governance job runs
**Then** the page's `confidence` score is set to `0.1` (or below the configured low-confidence threshold) automatically (FR43)

**Given** a page is flagged as low-confidence by citation enforcement
**When** the next governance report is generated
**Then** it appears in the report under a "Low Confidence — No Citations" section with the page ID and title

**Given** a candidate page is scored before promotion
**When** its confidence score is below the configured promotion threshold (default: `0.5` in `domains.yaml`)
**Then** it is held in the promotion queue and not committed to the wiki — a governance report entry explains why (FR44)

**Given** a candidate page meets or exceeds the promotion threshold
**When** scored
**Then** it is promoted to the wiki normally — the threshold gate does not block high-confidence content

**Given** the citation enforcement logic
**When** implemented
**Then** it runs as part of the existing governance job — not a new standalone job; it adds a citation-check pass to the existing governance sweep (FR43)

**Given** `GET /v1/pages` with a confidence filter parameter (e.g., `?min_confidence=0.5`)
**When** called
**Then** it returns only pages meeting or exceeding the threshold — low-confidence pages are filterable, not hidden by default (FR28)

### Story 2.3: Confidence Scores in All Query and Search Results

**Prerequisite:** Stories 2.1 and 2.2 must be complete — confidence scores are computed by the trust tagging and citation enforcement pipeline; surfacing them in results before they are computed produces stale or missing data.

As an agent or operator,
I want every query and search result to include a confidence score,
So that I can distinguish high-confidence compiled knowledge from speculative or low-signal pages and decide how much to rely on each result.

**Acceptance Criteria:**

**Given** `POST /v1/query` at any depth returns results
**When** each result is examined
**Then** it includes a `confidence` field as a float between 0.0 and 1.0 — never omitted, never null

**Given** `GET /v1/search` returns results
**When** each result is examined
**Then** it includes a `confidence` field reflecting the page's stored confidence score

**Given** a query result includes contradiction warnings
**When** returned
**Then** each contradiction includes `claim` (a human-readable summary) and `conflicting_page_id` — structured, not a raw string (FR57)

**Given** `POST /v1/query` with `depth: "quick"` or `"standard"`
**When** the caller filters by confidence
**Then** the `confidence` field on each result is the same value stored in the page's frontmatter — not recalculated per-query

**Given** the MCP `query` and `search` tools return results
**When** examined
**Then** they include `confidence` fields identical to the REST equivalents — same service method, same output schema (FR10, FR28)

**Given** a page with `confidence: 0.0`
**When** returned in results
**Then** it is included but clearly identifiable as zero-confidence — callers can filter client-side; the service does not silently hide low-confidence results unless explicitly filtered

### Story 2.4: Vector Search Integration

As an agent or operator,
I want semantic/vector search available alongside full-text search when the optional extras are installed,
So that conceptually related pages surface in search results even when they don't share exact keywords.

**Acceptance Criteria:**

**Given** the service is running with `uv sync --extra vector` (FAISS + sentence-transformers installed)
**When** `GET /v1/search?q=<text>` is called
**Then** the response includes results from both the fulltext index and the vector index, merged into a single ranked list (FR14, FR15)
**And** the response body includes `"vector_search": true`

**Given** the service is running without the vector extras installed
**When** `GET /v1/search?q=<text>` is called
**Then** the response returns full-text results only with `"vector_search": false` — no error, no exception (FR52)

**Given** vector search is enabled and a query is submitted
**When** results are merged
**Then** the ranking uses Reciprocal Rank Fusion (RRF) combining fulltext and vector scores — implemented as `sorted(page_ids, key=lambda k: rrf_scores[k], reverse=True)` (the lambda form, not `dict.get` — avoids mypy overload trap)

**Given** the MCP `search` tool is called
**When** executed
**Then** it returns `vector_search: bool` in its response — same value as the REST endpoint, driven by the same `WikiQuery.search()` return value; never hardcoded

**Given** the FAISS index is loaded at service startup
**When** a search is executed
**Then** the FAISS call runs inside `asyncio.to_thread()` — never blocks the uvicorn event loop, even though FAISS releases the GIL

**Given** the FAISS index file is missing or corrupt on startup
**When** the service initializes
**Then** vector search degrades gracefully: `add_document` and `search` log a warning and return empty results rather than raising an `ImportError` or crashing the service

## Epic 3: Cross-Domain Intelligence — "Knowledge That Compounds"

Entities shared across domains surface automatically. Repeated high-value queries become cached first-class wiki pages. Per-domain dashboards show knowledge health at a glance. Stale topics are archived without losing their history.

### Story 3.1: Authority Scoring

As an agent or operator,
I want every page to carry an authority score based on how frequently it is referenced across domains,
So that high-signal pages surface first in queries and cross-domain synthesis can identify the most trusted nodes in the knowledge graph.

**Acceptance Criteria:**

**Given** an `IndexRebuildJob` completes
**When** it finishes rebuilding all indexes
**Then** it computes an authority score for each page based on the count of cross-domain backlinks pointing to it
**And** writes the score to each page's `authority_score` frontmatter field (a float 0.0–1.0, normalized across the wiki)

**Given** a page is referenced by pages in multiple distinct domains
**When** authority scores are computed
**Then** cross-domain references contribute more weight to the score than same-domain references — a page referenced from 3 domains scores higher than one referenced 3 times within a single domain

**Given** a page has zero cross-domain backlinks
**When** scored
**Then** its `authority_score` is `0.0` — not omitted; always present in frontmatter

**Given** `GET /v1/pages/{page_id}`
**When** called
**Then** the response includes `authority_score` as a numeric field

**Given** `POST /v1/query` results
**When** authority scores exist
**Then** the ranking algorithm uses `authority_score` as a secondary sort signal after confidence — higher-authority pages rank above equal-confidence lower-authority pages

**Given** the authority scoring implementation
**When** audited
**Then** it is purely algorithmic — computed from the backlink index, no LLM calls (FR45)

### Story 3.2: Entity Promotion to Cross-Domain

As a wiki operator,
I want entities that appear in multiple domains to be automatically promoted to cross-domain status when they meet the confidence threshold,
So that shared knowledge surfaces across domain boundaries without manual curation.

**Acceptance Criteria:**

**Given** an entity page exists in two or more distinct domains with confidence above the configured threshold
**When** the promotion daemon job runs
**Then** the entity is flagged as a cross-domain promotion candidate

**Given** a cross-domain promotion candidate meets the threshold configured in `domains.yaml` (default: appears in ≥ 2 domains, `confidence ≥ 0.6`)
**When** the promotion job processes it
**Then** a shared entity page is created in `wiki_system/shared/` with a tombstone backlink on each original domain page pointing to the shared version (FR46)

**Given** an entity does not meet the promotion threshold
**When** the promotion job evaluates it
**Then** it is left in its original domain — no partial promotion, no silent move

**Given** a promotion threshold is updated in `domains.yaml`
**When** the daemon restarts and the promotion job next runs
**Then** it applies the new threshold without requiring a full wiki rebuild

**Given** an entity is promoted to `shared/`
**When** `POST /v1/query` or `GET /v1/search` is executed
**Then** the shared entity page appears in results for any domain query — it is visible from all domain contexts

**Given** the same entity page is ingested again after promotion
**When** processed
**Then** the merge strategy updates the shared page rather than creating a duplicate — promotion is idempotent (NFR-D3)

### Story 3.3: Cross-Domain Summary Page Generation

As an agent or operator,
I want cross-domain summary pages auto-generated for promoted entities,
So that a single query can surface a comprehensive view of what the wiki knows about an entity across all domains it appears in.

**Acceptance Criteria:**

**Given** an entity has been promoted to cross-domain status (Story 3.2 complete)
**When** the summary generation job runs
**Then** a summary page is created with `kind: concept` aggregating the entity's appearances, key claims, and cross-references from all contributing domains (FR47)

**Given** a summary page is generated
**When** examined
**Then** it includes a description assembled as follows:
- **When `llm_extraction: false`** (claim digest mode): collect all `extracted`-tagged claims for the entity from each contributing domain page, sorted by `confidence` descending; deduplicate by normalized claim text; concatenate top-N claims (N configurable in `daemon.yaml`, default: 10) as the description body
- **When `llm_extraction: true`** (synthesis mode): the claim digest is passed to the LLM for a summarization pass; output replaces the concatenated claims as the description body
- In both modes: source domain links, claim trust tags, and `authority_score` field are included

**Given** the source pages for a cross-domain entity are updated
**When** the summary generation job next runs
**Then** the summary page is regenerated to reflect the updated content — it is always derived, never manually edited

**Given** an entity's source pages drop below the promotion threshold (e.g., one domain page deleted)
**When** the promotion job next evaluates
**Then** the cross-domain summary page is archived (not deleted) and domain pages have their tombstones removed

**Given** `POST /v1/query` with a query matching a cross-domain entity
**When** returned
**Then** the summary page appears in results with higher ranking than individual domain pages for the same entity — it is the canonical cross-domain reference

**Given** the summary generation implementation
**When** audited
**Then** it runs as a daemon job, is fully algorithmic, and produces deterministic output given the same source pages (FR47)

### Story 3.4: Synthesis Cache — High-Value Query Pages

As an agent querying the wiki repeatedly,
I want frequently-repeated queries to be answered from cached synthesis pages rather than recomputed each time,
So that the wiki compounds in value over time and repeat queries return instant, pre-synthesized answers.

**Acceptance Criteria:**

**Given** the query log (`state/query_log.db`) contains at least `synthesis_cache_min_hits` occurrences of the same `query_hash` within the rolling 30-day window (`synthesis_cache_window_days` in `daemon.yaml`)
**When** the synthesis cache daemon job runs
**Then** it identifies that query as a cache candidate; default threshold is 5 hits / 30 days (configurable via `daemon.yaml`)

**Given** a query is identified as a cache candidate
**When** the synthesis cache job processes it
**Then** it creates a `kind: synthesis` wiki page with the synthesized answer, tagged with `source_query` set to the original query text (FR48, FR62)

**Given** a `kind: synthesis` page exists for a query
**When** the same query is submitted via MCP or REST
**Then** the synthesis page is returned as the top result — the cache hit is served before running a fresh synthesis

**Given** a synthesis cache page
**When** `GET /v1/pages/{page_id}` is called
**Then** the response includes `kind: "synthesis"` and `source_query: "<original query text>"` — distinguishable from primary source pages in all list and query results (FR62)

**Given** the source pages underlying a synthesis cache entry are updated
**When** the synthesis cache job next runs
**Then** it regenerates the synthesis page to reflect the updated knowledge — stale cache entries are refreshed, not preserved indefinitely

**Given** `GET /v1/pages` with `kind=synthesis`
**When** called
**Then** it returns only synthesis cache pages — operators can audit what the cache contains

**Given** the synthesis cache implementation
**When** audited
**Then** it reads from `query_log.db` (FR63 from Epic 1) and produces synthesis algorithmically — no LLM calls in the caching pipeline

### Story 3.5: Per-Domain Dashboards

As an operator,
I want per-domain health dashboards summarizing page count, confidence distribution, and recent changes,
So that I can assess the quality and activity of each knowledge domain at a glance without querying individual pages.

**Acceptance Criteria:**

**Given** `GET /v1/domains/{domain}/dashboard`
**When** called for a configured domain
**Then** it returns: `page_count`, `confidence_distribution` (histogram buckets: 0–0.3, 0.3–0.6, 0.6–1.0), `recent_changes` (last 10 page mutations from changelog), `low_confidence_count`, `stale_count`, `last_governance_run` (FR49)

**Given** `GET /v1/domains/{domain}/dashboard` for an unknown domain
**When** called
**Then** it returns HTTP 404 `DOMAIN_UNKNOWN`

**Given** the dashboard endpoint
**When** called
**Then** it responds within 500ms — data is computed from in-memory index state, not a full filesystem scan

**Given** the MCP server
**When** updated for this story
**Then** a `domain_dashboard` tool is added that calls the same service method as the REST endpoint

**Given** `llm-wiki govern dashboard [--domain <name>] [--json]`
**When** run
**Then** it prints the dashboard for the specified domain (or all domains if omitted), with `--json` emitting machine-parseable output (NFR-I3)

**Given** the dashboard data
**When** generated
**Then** it is derived from existing index files (metadata, backlinks, changelog) — no new persistent state is introduced for dashboards

### Story 3.6: Topic Archive Lifecycle

As an operator,
I want stale topics to be automatically archived past their staleness threshold, and to be able to manually archive any topic via CLI,
So that the active query context stays focused on current knowledge without permanently losing historical content.

**Acceptance Criteria:**

**Given** a page whose `updated_at` is older than the `staleness_threshold_days` configured in `domains.yaml` for its domain
**When** the governance daemon job runs
**Then** the page is moved to an `archive/` subdirectory within its domain folder and excluded from normal query results (FR50a)

**Given** an archived page
**When** `GET /v1/pages/{page_id}` is called with its ID
**Then** it is still retrievable — archive preserves the page, it is only excluded from default query/search scope

**Given** `POST /v1/query` or `GET /v1/search`
**When** called without explicit archive inclusion
**Then** archived pages are excluded from results — the active knowledge context does not include stale archived content

**Given** `llm-wiki govern archive <page-id>`
**When** run
**Then** the specified page is archived immediately regardless of its staleness — manual archive is not gated on the threshold (FR50b)

**Given** `llm-wiki govern archive <page-id>` for a page that is already archived
**When** run
**Then** it is idempotent — no error, no duplicate archive entry

**Given** `staleness_threshold_days` is updated in `domains.yaml` to a more restrictive value (fewer days)
**When** the daemon restarts and governance next runs
**Then** pages that now exceed the stricter threshold are archived

**Given** `staleness_threshold_days` is updated in `domains.yaml` to a more permissive value (more days)
**When** the daemon restarts and governance next runs
**Then** pages that no longer exceed the threshold remain archived — threshold relaxation does NOT automatically restore archived pages; restoration is a deliberate operator action only (`llm-wiki govern unarchive <page-id>`)

**Given** `llm-wiki govern unarchive <page-id>`
**When** run
**Then** the specified page is moved back from `archive/` to `pages/` and becomes visible in normal query results

## Epic 4: Web UI & Operations — "Operate and Browse as a Human" *(V4 — Placeholder)*

> **Status:** Placeholder — full story breakdown will be created when Epic 3 is complete and V4 is planned in earnest. No detailed FRs are defined in the PRD yet; the architecture explicitly defers web UI decisions.
>
> **Planning note:** Do not write stories for this epic until the Epic 3 retrospective. The frontend stack, auth surface behavior in a browser context, and graph visualization requirements all require a dedicated planning session — the technical notes below are initial considerations only, not decisions. In particular, the service binds to `0.0.0.0` inside the container with port exposure controlled via docker-compose — a browser UI served from the same origin needs explicit analysis of same-origin and cookie security model concerns that the JSON API does not face.

**Goal:** Make the wiki pleasant to browse and operate for humans, not just agents. After this epic, a developer or operator can navigate the knowledge graph, search and browse by entity/concept/source, edit pages, and control the daemon — all from a browser.

**Known capability areas (to become stories during V4 planning):**

- **Search & Browse UI** — Full-text and semantic search with result previews; browse pages by domain, kind (entity/concept/source/qa/synthesis), and tag; page reader view with frontmatter provenance visible
- **Graph Visualization** — Force-directed graph layout of pages and cross-references; community detection (Louvain algorithm); highlight authority nodes; filter by domain or kind
- **Page Editor** — In-browser page creation and editing; frontmatter fields exposed as structured form inputs; save triggers the standard ingest/merge pipeline (not a bypass)
- **Daemon Control Panel** — View job schedule and last-run results; trigger jobs manually (index rebuild, governance, export); pause/resume individual jobs; view structured daemon logs
- **Richer Exports** — Markdown without frontmatter (clean human-readable export); HTML static site generation; RSS feed of recent changes

**Technical notes for V4 planning (considerations, not decisions):**
- Frontend stack TBD — evaluate at planning time (lightweight options: plain HTML + HTMX; heavier: React/Vue if graph visualization requires it)
- FastAPI serves static files or acts as API backend to a separate frontend process
- Graph visualization likely requires a JavaScript library (D3.js, Cytoscape.js, or similar) — evaluate against Louvain community detection requirements
- Auth requirements for the browser surface need explicit analysis — the `0.0.0.0` + compose model is not sufficient to assume the same no-auth model as the JSON API for a browser surface

**Prerequisite:** Epics 1-3 complete. Epic 4 planning begins after Epic 3 retrospective.

---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: 'complete'
completedAt: '2026-05-17'
inputDocuments:
  - "_bmad-output/planning-artifacts/prd.md"
  - "_bmad-output/planning-artifacts/prd-validation-report.md"
  - "docs/Product_Brief.md"
  - "docs/ARCHITECTURE.md"
  - "docs/ARCHITECTURE_REVIEW.md"
  - "_bmad-output/project-context.md"
workflowType: 'architecture'
project_name: 'llm_wiki'
user_name: 'Marc'
date: '2026-05-17'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
The PRD defines 63+ FRs across 9 categories:

| Category | FRs | Sprints |
|---|---|---|
| Knowledge Ingestion | FR1-7, FR51, FR58 | Sprint 1 |
| Query & Retrieval | FR8-12, FR54, FR57, FR59 | Sprint 1 |
| Search (fulltext + vector) | FR13-15, FR52 | Sprint 1-2 |
| Daemon & Governance | FR16-23 | Sprint 1 |
| Knowledge Management | FR24-29, FR53, FR63 | Sprint 1-3 |
| Export & Integration | FR30-34 | Sprint 1-2 |
| Service Operations | FR35-41, FR55, FR60, FR61 | Sprint 1 |
| Trust & Provenance | FR42-44 | Sprint 2 |
| Cross-Domain Synthesis | FR45-50b, FR62 | Sprint 3 |

**Non-Functional Requirements:**
- **Performance:** ≤200ms quick queries, ≤2s standard, 30s hard timeout for deep synthesis, ≥10 inbox items/min ingest throughput, ≤60s full index rebuild (1,000 pages)
- **Reliability:** 60s crash-to-operational recovery, atomic index writes (zero corruption), zero inbox item loss on crash, startup integrity verification
- **Integration:** OpenAPI 3.1, dual MCP transports (Streamable HTTP + stdio), `--json` flag on all CLI read commands, consistent error codes across all three surfaces
- **Operability:** ≤30s cold start, ≤1s health check response, YAML-file configuration (no container rebuild required)
- **Data Integrity:** Deterministic page IDs, append-only changelog (JSONL), idempotent merge strategies
- **Security:** binds to `0.0.0.0` inside container; docker-compose port mapping controls exposure; VM-level isolation is the security boundary

**Scale & Complexity:**
- Primary domain: API backend + ML/AI tooling (knowledge graph, algorithmic daemon, multi-interface service)
- Complexity level: Medium (brownfield expansion, solo developer, 2-3 day sprints, 4 planned phases)
- Phased delivery: 4 sprints — service pivot → trust layer → cross-domain synthesis → web UI

### Technical Constraints & Dependencies

- **Python 3.11+** with uv; never bare `python3` or `pip`
- **No external database** — filesystem is source of truth; indexes are derived caches
- **No LLM calls in daemon** — all governance is deterministic/algorithmic
- **Docker + host-mounted volume** — no data inside the image; config via mounted YAML
- **Cloud per-household deployment** — each household on a dedicated VM; VM-level isolation is the security boundary; no in-service auth required
- **Optional vector extras** — `faiss-cpu` + `sentence-transformers` behind `uv sync --extra vector`; must degrade gracefully when absent
- **Optional LLM extraction** — controlled by `llm_extraction` feature flag in `daemon.yaml`; when disabled, heuristics handle all extraction; when enabled, provider config in `models.yaml` supports Anthropic, OpenAI, OpenRouter, or local vLLM/Llama (all OpenAI-compatible via `base_url`)
- **Known P0 bugs (Sprint 1 prerequisites):** non-atomic index writes (fix: tmp→os.replace), no write mutex (fix: threading.Lock per index), orphaned inbox files on crash (fix: startup recovery)
- **MCP protocol compliance** must be verified against Homefront (real harness) as Sprint 1 acceptance gate

### Cross-Cutting Concerns Identified

1. **Atomicity & concurrency** — Every index write must use tmp→os.replace; a threading.Lock per index file must guard concurrent daemon workers
2. **Multi-interface parity** — MCP, REST, and CLI expose identical capabilities; error codes (`WIKI_NOT_FOUND`, `INDEX_STALE`, etc.) must be consistent across all three
3. **Crash recovery** — Inbox must recover orphaned `processing/` files on startup; daemon checkpoint/resume; index integrity check before serving queries
4. **Provenance & confidence** — Tags (extracted/inferred/ambiguous) and confidence scores flow from ingest through query response, governance reports, and AI-consumable exports
5. **Daemon job coordination** — max_workers=2 is a hard cap until write mutex lands; scheduling must prevent simultaneous writes to shared index files
6. **Optional dependency degradation** — All FAISS/sentence-transformers paths must guard ImportError at runtime, returning capability indicators rather than errors

## Service Layer Foundation

### Technology Domain

API backend (MCP + REST + CLI) — brownfield expansion of existing Python V1 library.
Core stack is already established; this section records the new service layer additions.

### Established Stack (V1 — No Change)

- Language: Python 3.11+, managed by uv
- CLI: Click 8.1+ — all business logic in service classes; CLI is a thin wrapper
- Validation: Pydantic 2.0+ (v2 API throughout)
- Daemon: APScheduler 3.10+ BackgroundScheduler + ThreadPoolExecutor(max_workers=2)
- Search: FAISS IndexFlatL2 + sentence-transformers (optional extra: `uv sync --extra vector`)
- Retry: tenacity 8.0+
- File watching: watchdog 3.0+
- LLM client: openai 1.0+ (OpenAI-compatible; supports Anthropic/Ollama/LM Studio via base_url)

### New Service Layer Additions (Sprint 1)

**MCP Server: `mcp` Python SDK (latest)**

- Rationale: Reference implementation; supports Streamable HTTP and stdio transports (NFR-I4); standard `tools/list` autodiscovery built-in (FR38); maintained by Anthropic
- Install: `uv add mcp` (install latest; rip out any existing version first)
- Streamable HTTP transport: mounted at `/mcp` on the uvicorn process
- stdio transport: also available; harness spawns process directly
- SSE transport: deprecated in MCP spec — do not use

**REST API: FastAPI + uvicorn**

- Rationale: Native Pydantic v2 integration (shared models with existing codebase); auto-generates OpenAPI 3.1 at `/v1/openapi.json` (FR37, NFR-I2); async-first for concurrent MCP + REST requests; already documented as the planned fix for P0-4
- Install: `uv add fastapi uvicorn`
- All REST routes in `src/llm_wiki/api/` — thin router layer over existing service classes (same pattern as CLI)

**Container: Docker multi-stage build + docker-compose**

- Single image; two runtime processes: uvicorn (REST API + MCP Streamable HTTP) + WikiDaemon
- Process management: supervisord or entrypoint script with process group
- Data volume: host-mounted at `/wiki` (no data inside image)
- Config: host-mounted YAML files at `/config` (NFR-O3)
- Bind: `0.0.0.0` inside container; docker-compose port mapping controls external exposure

**Initialization Command (Sprint 1, Story 1):**

```bash
# No greenfield scaffold — brownfield extension of existing repo
# Service layer setup:
uv add fastapi uvicorn mcp
# Docker build:
docker-compose up --build
```

**Architectural Decisions Made by Service Layer Choice:**

- Shared Pydantic models between REST schemas and existing domain models — no translation layer
- FastAPI dependency injection for WikiConfig and WikiQuery — injected per-request, not global mutable state
- MCP tools defined as thin wrappers over the same service methods as REST routes
- uvicorn runs in the same container as the daemon; they communicate via shared filesystem state (no IPC needed — file system is the source of truth)

## Core Architectural Decisions

### Decision Priority Analysis

**Critical (Block Implementation):**
- Docker process architecture (supervisord — isolation of daemon vs API crashes)
- Index write mutex pattern (central lock registry in WikiQuery)
- Async synthesis engine design (async generator — enables B→C upgrade path)
- Multi-user domain structure (scope field in domains.yaml — Sprint 1)

**Important (Shape Architecture):**
- Deep query strategy per surface (MCP: blocking/timeout; REST: background task + poll)
- Query log storage (SQLite for cross-domain scale)
- Port assignment (3050)
- Daemon logging format (human-readable + --json flag)

**Deferred (Post-MVP):**
- REST streaming for deep queries — async generator protocol already supports it without synthesis changes
- Per-user domain access policies — delegated to calling harness for V1

---

### Process Architecture (Docker)

**Decision:** Two-process container managed by supervisord

- Process 1: uvicorn — FastAPI serving REST API (`/v1/`) + MCP Streamable HTTP (`/mcp`)
- Process 2: WikiDaemon — APScheduler background scheduler
- Rationale: daemon crash is isolated from the query interface; 60s recovery requirement (NFR-R1) met independently per process
- supervisord writes process stdout/stderr to `/var/log/llm-wiki/`; `llm-wiki daemon status` reads `state/jobs.json` (not supervisord)

### Deep Query Async Strategy

**Decision:** Async generator synthesis engine; MCP blocks (up to 30s), REST uses async polling

- **Synthesis engine:** implemented as an async generator producing incremental results internally — enables future streaming upgrade without synthesis re-arch
- **Synthesis behavior:** LLM-optional — when `llm_extraction: false`, synthesis assembles pages sorted by confidence + authority score with source attribution headers (one `SynthesisChunk` per page); when `llm_extraction: true`, assembled content is passed to the LLM for a summarization pass before yielding chunks
- **MCP surface:** `query` tool with `depth: deep` blocks up to 30s and returns the result directly — either `{"partial": false, "timed_out": false, "results": [...]}` on completion or `{"partial": true, "timed_out": true, "results": [...]}` on timeout. MCP tool calls are inherently synchronous; no `job_id` is issued and no polling tool is needed.
- **REST surface:** `POST /v1/query` with `depth: deep` returns `{"job_id": "...", "status": "queued"}` immediately; `GET /v1/query/{job_id}` polls; result schema identical to synchronous quick/standard response once complete
- **Job state:** in-memory dict on `app.state.deep_jobs`; 5-minute TTL; not persisted to disk; 404 on restart is expected and acceptable — client resubmits; REST-only (MCP uses the blocking pattern above)
- **quick/standard depths:** synchronous response only on both MCP and REST; no job_id pattern

### Network & Ports

**Decision:** Default port 3050 (configurable); single port; REST + MCP on same uvicorn process

- REST API: `http://{host}:{port}/v1/`
- MCP Streamable HTTP: `http://{host}:{port}/mcp`
- stdio transport: also available; harness spawns process directly
- Health check: `GET http://{host}:{port}/v1/health`
- Bind: `0.0.0.0:{port}` inside container; docker-compose controls whether port is published to host and on which interface
- Port is set via `WIKI_PORT` env var (default: 3050); never hardcoded

### Index Write Concurrency

**Decision:** Central lock registry in WikiQuery; IndexRebuildJob holds a WikiQuery reference

- `WikiQuery` maintains `dict[str, threading.Lock]` keyed by index name
- All index writes go through `WikiQuery` methods — `WikiQuery` acquires the per-index lock before calling `save()`
- `IndexRebuildJob` is injected with the `WikiQuery` singleton at scheduler setup time; it calls `wiki.acquire_all_locks()` before the rebuild sweep and `wiki.release_all_locks()` after — it does not maintain its own lock registry
- After completing the rebuild and releasing locks, `IndexRebuildJob` calls `wiki.reload_vector_index()` — WikiQuery acquires the vector lock, swaps the in-memory FAISS instance with the newly written file, and releases. This eliminates the stale vector index window between rebuilds.
- Rationale: WikiQuery remains the single lock owner; IndexRebuildJob borrows via explicit methods; FAISS stays current without a process restart

### Query Log & Synthesis Cache Storage

**Decision:** SQLite at `wiki_system/state/query_log.db` (Python stdlib `sqlite3`)

- Schema: `queries(id, query_hash, query_text, depth, domains, result_count, confidence_avg, timestamp)`
- Cross-domain analysis (`SELECT query_hash, COUNT(*) FROM queries WHERE json_array_length(domains) > 1 GROUP BY query_hash HAVING COUNT(*) > 5`) enables synthesis cache candidate identification (FR48) without full-file scans
- Scales to 50+ domains: domain lists stored as JSON arrays; indexed by `(query_hash, timestamp)`
- Append-write per query; synthesis cache job reads periodically — no concurrent write contention with index files
- No new dependency (Python 3.11 stdlib); file lives on host-mounted volume; inspectable via `sqlite3` CLI

### Feature Flags

**Decision:** `features:` block in `daemon.yaml`; provider config in `models.yaml`

```yaml
# daemon.yaml
features:
  llm_extraction: false        # LLM tag/summary/claim extraction — off by default
  vector_search: true          # sentence-transformers — on by default
  synthesis_cache: false       # Sprint 3
  cross_domain_promotion: false # Sprint 3
```

```yaml
# models.yaml — LLM provider config (only read when llm_extraction: true)
extraction:
  provider: anthropic          # anthropic | openai | openrouter | local
  model: claude-haiku-4-5-20251001
  api_key_env: ANTHROPIC_API_KEY  # reads from env var; never hardcoded
  base_url: null               # null = provider default
                               # openrouter: https://openrouter.ai/api/v1
                               # local vLLM/Llama: http://localhost:8000/v1
  timeout_seconds: 30
  max_retries: 2
```

All providers use the OpenAI-compatible API — `base_url` override covers OpenRouter and local vLLM/Llama with no code changes.

**Extraction fallback behavior when `llm_extraction: false`:**

| Task | LLM path | Heuristic fallback |
|---|---|---|
| Kind classification | LLM classifies entity/concept/page | First-heading pattern + keyword rules |
| Tags | LLM generates 3-5 tags | Top TF-IDF terms from page content |
| Summary | LLM writes 1-2 sentences | First non-heading paragraph, truncated |
| Entities | LLM extracts with descriptions | Skip or spaCy NER (optional dep) |
| Claims | LLM extracts atomic facts | Skip — confidence scoring uses heuristic path |

### Confidence Scoring

**Decision:** Configurable weighted scorer; weights per-domain in `domains.yaml`

```yaml
# domains.yaml — confidence weight config per domain
domains:
  - name: household
    confidence_weights:
      citation_presence: 0.4   # has valid source citations
      trust_tag: 0.2           # extracted > inferred > ambiguous (llm_extraction only)
      source_count: 0.2        # more sources = higher confidence
      backlink_count: 0.1      # referenced by other pages
      recency: 0.1             # newer = higher confidence
```

Default weights apply when not specified. When `llm_extraction: false`, `trust_tag` weight redistributes to `citation_presence`. Score is always a float 0.0–1.0; never omitted.

### Daemon Logging Format

**Decision:** Human-readable logs + `--json` flag on all CLI read commands

- Daemon operational logs: human-readable to stdout/supervisord (operator-friendly)
- `llm-wiki daemon jobs --json`: emits structured JSON from `state/jobs.json` (authoritative job record)
- Consistent with established CLI convention (NFR-I3: `--json` flag on all query/status commands)

---

### Multi-User Household Architecture

**Deployment topology:** One llm-wiki instance per household, running as a sidecar container alongside the agent harness on a dedicated VM.

**Domain structure for multi-user households:**

```yaml
# domains.yaml — household instance
domains:
  - name: household
    scope: shared          # visible to all members
    description: Shared household knowledge

  - name: user-{profile_id}
    scope: personal        # scoped to one profile
    owner: {profile_id}
    description: Personal knowledge for {name}
```

**Query scoping semantics:**

| `domain` param | Returns |
|---|---|
| omitted | `household/` + requesting profile's `user-{id}/` merged |
| `household` | household-only results |
| `user-{id}` | that profile's personal domain only |
| `all` | all domains |

**Profile identity:** passed via `X-Profile-Id` header (REST) or `profile_id` MCP tool parameter. The calling harness is responsible for populating this — llm-wiki trusts the caller. Domain scope filtering logic lives exclusively in `WikiQuery.search()`.

**Cross-pollination (personal → shared knowledge):**

- Sprint 3 cross-domain synthesis (FR45-47) handles automatic entity promotion
- When an entity in `user-{id}/` is referenced across enough sources/domains, it becomes a candidate for promotion to `household/`
- Promotion thresholds configurable per-household in `domains.yaml`

**Sprint 1 implications (design now, not deferred):**

1. `domains.yaml` schema: add `scope: shared|personal` and optional `owner: {profile_id}` — validated by Pydantic on startup
2. `WikiQuery.search()`: add `scope_to_profile: str | None` — when set, merges `household/` + `user-{id}/` results
3. MCP `query` tool: `profile_id` parameter; REST: `X-Profile-Id` header via `Depends(get_profile_id)`
4. Daemon governance: scope-aware job execution — `GovernanceJob` runs `household/` globally, `user-{id}/` per owner

## Implementation Patterns & Consistency Rules

**Critical conflict points identified:** 13 areas where AI agents could make incompatible choices in the new service layer.

---

### FastAPI Route Structure

**Pattern:** One router file per resource group; all routers mounted in `src/llm_wiki/api/app.py`

```
src/llm_wiki/api/
├── app.py            # FastAPI app instance; lifespan; mounts all routers
├── deps.py           # Depends() functions (get_wiki, get_profile_id)
├── errors.py         # WikiError → HTTP exception mapping
├── models.py         # All API Pydantic request/response models
└── routers/
    ├── health.py     # GET /v1/health, GET /v1/daemon/status, GET /v1/daemon/jobs
    ├── query.py      # POST /v1/query, GET /v1/query/{job_id}
    ├── ingest.py     # POST /v1/ingest, GET /v1/ingest/{job_id}
    ├── search.py     # GET /v1/search
    ├── pages.py      # GET /v1/pages, GET /v1/pages/{page_id}
    ├── export.py     # POST /v1/export, GET /v1/export/{format}
    └── domains.py    # GET /v1/domains
```

**Rules:**
- Router files are thin — delegate to existing service/index classes immediately; no business logic in router functions
- All routers use `APIRouter(prefix="/v1", tags=[...])` — never put `/v1` in individual route paths
- Same delegation pattern as `cli.py`: parse params → call service → return response model

### MCP Tool Definitions

**Pattern:** All MCP tools in `src/llm_wiki/mcp/tools.py`; server in `src/llm_wiki/mcp/server.py`

```
src/llm_wiki/mcp/
├── server.py    # MCP Server instance; registers all tools; startup/shutdown
└── tools.py     # All @server.tool() definitions — thin wrappers over service classes
```

**Rules:**
- MCP tool names: `verb_noun` snake_case — `query`, `ingest`, `read_page`, `list_pages`, `search`, `export`, `ingest_status` (`ingest_status` is a grandfathered exception to the `verb_noun` rule; it is used consistently in all interfaces and renaming would be a breaking change)
- Each MCP tool calls the same service method as the equivalent REST route — shared service layer, two transport skins
- MCP tool parameter names match REST body/query parameter names exactly
- MCP Streamable HTTP transport endpoint: `/mcp` at `http://{host}:{port}/mcp`

### WikiQuery Dependency Injection

**Pattern:** WikiQuery is a **singleton on `app.state`**, initialized once in the FastAPI lifespan. Never per-request.

```python
# src/llm_wiki/api/app.py — single allowed WikiQuery instantiation
@asynccontextmanager
async def lifespan(app: FastAPI):
    wiki_root = Path(os.environ["WIKI_ROOT"])
    _maybe_init_wiki_root(wiki_root)        # must run before WikiConfig.load() (FR55)
    config = WikiConfig.load(wiki_root / "config")
    app.state.wiki = WikiQuery(config)      # FAISS loads once here
    app.state.deep_jobs: dict[str, DeepQueryJob] = {}  # in-memory job state
    yield

# src/llm_wiki/deps.py  (package root — shared by both api/ and mcp/)
def get_wiki(request: Request) -> WikiQuery:
    return request.app.state.wiki           # shared singleton; reads are thread-safe

def get_profile_id(x_profile_id: str | None = Header(default=None)) -> str | None:
    return x_profile_id                     # X-Profile-Id header; caller is responsible for identity
```

**Rules:**
- Never instantiate WikiQuery inside a route function, tool function, or dependency function — the **single allowed instantiation** is in `app.py` lifespan
- All routes and MCP tools access WikiQuery via `Depends(get_wiki)` or `request.app.state.wiki`
- WikiQuery singleton is shared between uvicorn thread pool and daemon's `ThreadPoolExecutor` — `threading.Lock` is process-wide; the central lock registry in WikiQuery protects both correctly. Do NOT add a second locking layer in route or tool code
- FAISS index always loads at startup; daemon rebuilds update the file on disk; in-memory index is refreshed via `reload_vector_index()` after rebuild or on process restart

### Startup Init Sequence

**Pattern:** `_maybe_init_wiki_root()` must be the first call in lifespan — before `WikiConfig.load()`

```python
def _maybe_init_wiki_root(wiki_root: Path) -> None:
    """Auto-initialize wiki directory structure on first start (FR55, NFR-O4)."""
    if not (wiki_root / "domains").exists():
        WikiInitializer.initialize(wiki_root)
```

**Rule:** If called after `WikiConfig.load()`, a fresh empty volume raises `FileNotFoundError` before init runs.

### Error Propagation

**Pattern:** WikiErrors → `errors.py` mapper → consistent HTTP response; `QueryTimeoutError` handled inline

```python
# src/llm_wiki/api/errors.py
ERROR_MAP: dict[type[WikiError], tuple[int, str]] = {
    WikiNotFoundError:     (404, "WIKI_NOT_FOUND"),
    DomainUnknownError:    (404, "DOMAIN_UNKNOWN"),   # default; override to 422 when domain is user-supplied POST body
    IngestError:           (422, "INGEST_ERROR"),
    IndexStaleError:       (503, "INDEX_STALE"),
    DaemonNotRunningError: (503, "DAEMON_NOT_RUNNING"),
    ExportNotReadyError:   (404, "EXPORT_NOT_READY"),
    InvalidDepthError:     (422, "INVALID_DEPTH"),
}
# QueryTimeoutError is NOT in ERROR_MAP — it is a normal response variant, not an error
```

**REST error response envelope (always):**
```json
{"error_code": "WIKI_NOT_FOUND", "message": "...", "rebuild_hint": false}
```

**Timeout is a normal response branch, not an error:**
```python
result = await run_deep_query(req.query, pages)
if result.timed_out:
    return QueryResponse(timed_out=True, partial=True, results=result.partial_results)
return QueryResponse(timed_out=False, results=result.results)
```

**Rules:**
- `errors.py` is the single source of truth for WikiError → HTTP status code mapping
- Never `raise HTTPException(status_code=...)` inline for a known WikiError type — raise the WikiError; let the exception handler call `errors.py`
- `DomainUnknownError` on POST body (user-supplied input) → override to 422: `raise wiki_error_to_http(e, status_override=422)`
- `rebuild_hint: true` only on `INDEX_STALE` errors
- MCP errors: JSON-RPC error object with `code` (numeric) and `message` matching `error_code` string; numeric codes: `-32001` WIKI_NOT_FOUND, `-32002` DOMAIN_UNKNOWN, `-32003` INGEST_ERROR, `-32004` INDEX_STALE, `-32005` DAEMON_NOT_RUNNING, `-32006` EXPORT_NOT_READY, `-32007` INVALID_DEPTH
- CLI errors: exit code 1; stderr message; `--json` flag emits `{"error_code": "...", "message": "..."}`

### REST Response Envelope

**Pattern:** Direct Pydantic response models for success; no wrapper for single-resource responses; pagination envelope for lists

```python
# CORRECT — direct model
@router.get("/v1/pages/{page_id}", response_model=PageResponse)
async def read_page(...): ...

# CORRECT — pagination envelope for lists
{"pages": [...], "next_cursor": "string|null", "total_hint": 0}

# WRONG — do not wrap single resources
return {"data": page, "status": "ok"}
```

### API Pydantic Model Naming

**Pattern:** `{Resource}Response` for returns; `{Resource}Request` for POST bodies; all in `src/llm_wiki/api/models.py`

```
PageResponse, PageListResponse
QueryRequest, QueryResponse, DeepQueryJob
IngestRequest, IngestStatusResponse
SearchResponse
ExportResponse
HealthResponse, DaemonStatusResponse
```

Domain models (`PageFrontmatter`, etc.) are never returned directly from routes — always mapped to an API response model.

### Async/Sync Boundary

**Pattern:** FastAPI route functions are `async def`; all I/O-touching service calls use `asyncio.to_thread()`

```python
# USE to_thread() — any I/O operation (disk, database, FAISS)
page = await asyncio.to_thread(wiki.get_page, page_id)
results = await asyncio.to_thread(wiki.search, query)
await asyncio.to_thread(log_query, db_path, entry)

# DO NOT use to_thread() — pure in-memory, no I/O
job = app.state.deep_jobs.get(job_id)      # dict lookup
error_code = ERROR_MAP[type(exc)][1]        # dict lookup
config_val = request.app.state.wiki.config  # already-loaded object
```

**Rules:**
- All existing service/index classes remain synchronous — do not convert them to async
- FAISS search releases the GIL but is CPU-intensive — always wrap in `asyncio.to_thread()`; it will saturate a CPU core for the search duration regardless of GIL release
- All `sqlite3.connect()` calls must include `check_same_thread=False` — query log writes run inside thread pool workers

### Synthesis Async Generator Protocol

**Pattern:** Synthesis engine is an `async def` generator; timeout enforced via `asyncio.timeout()`

```python
# src/llm_wiki/query/synthesis.py
async def synthesize(
    query: str,
    pages: list[WikiPage],
) -> AsyncGenerator[SynthesisChunk, None]:
    """Yields SynthesisChunk(text: str, is_final: bool, sources: list[str])."""
    ...

# Consumer — deep query handler
async def run_deep_query(query: str, pages: list[WikiPage], timeout: float = 30.0) -> DeepQueryResult:
    chunks: list[SynthesisChunk] = []
    timed_out = False
    try:
        async with asyncio.timeout(timeout):
            async for chunk in synthesize(query, pages):
                chunks.append(chunk)
    except TimeoutError:
        timed_out = True
    return DeepQueryResult(chunks=chunks, timed_out=timed_out, partial=timed_out)
```

**Rule:** Never implement synthesis as a synchronous function returning a complete result. The generator protocol is the architectural invariant that enables future REST streaming without synthesis re-arch. Changing the generator protocol is a breaking change across both MCP and REST surfaces.

### Deep Query Job State

**Pattern:** In-memory dict on `app.state.deep_jobs`; TTL 5 minutes; never persisted to disk

```python
# job lifecycle: created → running → complete/failed → evicted after 5min TTL
app.state.deep_jobs[job_id] = DeepQueryJob(status="running", created_at=now())
# background cleanup task runs every 60s; removes entries older than 5min
```

**Rules:**
- Do NOT store deep query job state in `state/jobs.json` — that is the authoritative daemon job history, not transient HTTP job state
- If uvicorn restarts mid-query, the `job_id` becomes invalid — client receives 404 on poll; this is expected V1 behavior; document with `X-Job-TTL: 300` header on job creation response
- MCP deep queries use blocking tool call (max 30s); in-memory job state is REST-only

### Domain Scope & Profile Scoping

**Pattern:** `X-Profile-Id` header for REST; `profile_id` parameter for MCP tools; both flow to `WikiQuery.search(scope_to_profile=...)`

```python
# REST — X-Profile-Id header injected via Depends
@router.post("/v1/query")
async def query(req: QueryRequest, wiki=Depends(get_wiki), profile_id=Depends(get_profile_id)):
    results, vector_search = await asyncio.to_thread(
        wiki.search, req.query, domain=req.domain, scope_to_profile=profile_id
    )

# MCP tool — explicit profile_id parameter
@server.tool()
async def query(query: str, domain: str | None = None, profile_id: str | None = None):
    ...
```

**Rules:**
- Domain scope logic lives in `WikiQuery.search()` exclusively — never filter domains in route or tool code
- All search responses (REST and MCP) must include `vector_search: bool` from `WikiQuery.search()` — never hardcode it
- The calling harness is responsible for populating `profile_id` / `X-Profile-Id` on all outgoing requests; llm-wiki trusts the caller

### Query Log Write Pattern

**Pattern:** SQLite at `wiki_system/state/query_log.db`; one connection per write via context manager

```python
# src/llm_wiki/query/log.py
def log_query(db_path: Path, entry: QueryLogEntry) -> None:
    # check_same_thread=False required: runs inside asyncio.to_thread() thread pool
    with sqlite3.connect(db_path, check_same_thread=False) as conn:
        conn.execute(INSERT_SQL, (
            entry.query_hash, entry.query_text,
            entry.depth, json.dumps(entry.domains),
            entry.result_count, entry.confidence_avg,
            entry.timestamp.isoformat(),
        ))
```

### Docker Process & Container Patterns

**Process management (supervisord):**
```ini
[program:uvicorn]
command=uvicorn llm_wiki.api.app:app --host 0.0.0.0 --port %(ENV_WIKI_PORT)s
autorestart=true
startretries=3
stopwaitsecs=10

[program:daemon]
command=python -m llm_wiki.daemon.main
autorestart=true
startretries=5
stopwaitsecs=30   ; daemon may be mid-write; never lower this value
```

**Container user and volume permissions:**
```dockerfile
RUN adduser --disabled-password --uid 1000 --gecos "" llmwiki
USER llmwiki
```
```yaml
# docker-compose.yml
volumes:
  - ./wiki_data:/wiki       # host dir must be owned by uid 1000
  - ./config:/config:ro
```
Host setup required: `sudo chown -R 1000:1000 ./wiki_data`

**Volume paths (fixed inside container):**

| Host path | Container path | Purpose |
|---|---|---|
| `./wiki_data` | `/wiki` | wiki_system/ directory tree |
| `./config` | `/config` (read-only) | daemon.yaml, domains.yaml, models.yaml, routing.yaml |

`WIKI_ROOT=/wiki` set in Dockerfile. Never hardcode local dev paths.

---

### Enforcement Guidelines

**Top 3 critical rules — failure here causes data corruption or broken API contracts:**

1. **Map all WikiErrors through `errors.py`** — never `raise HTTPException(...)` inline for a known error type
2. **Use `asyncio.to_thread()` for all I/O-touching service calls** in async route functions (disk, FAISS, SQLite)
3. **Never instantiate WikiQuery in a route/tool/dep function** — the single allowed instantiation is in `app.py` lifespan

**Rules 4–13 — cause inconsistency or incorrect behavior if violated:**

4. Put new FastAPI routes in `src/llm_wiki/api/routers/{resource}.py` — never in `app.py` directly
5. Name API Pydantic models `{Resource}Request` / `{Resource}Response` — never `Schema`, `Model`, or `Out`
6. Put MCP tool definitions in `src/llm_wiki/mcp/tools.py` — never inline in `server.py`
7. Domain scope logic lives in `WikiQuery.search()` only — never filter domains in route or tool code
8. All search responses must include `vector_search: bool` from `WikiQuery.search()` — never hardcode
9. All `sqlite3.connect()` calls must include `check_same_thread=False`
10. `QueryTimeoutError` is a normal response branch — never put it in `ERROR_MAP`
11. `_maybe_init_wiki_root()` must be called before `WikiConfig.load()` in lifespan
12. Never lower `stopwaitsecs` for the daemon supervisord process below 30
13. Synthesis engine must be an async generator yielding `SynthesisChunk` — never a synchronous function returning a complete result

**Anti-patterns:**
```python
# ❌ Inline error mapping
raise HTTPException(status_code=404, detail="not found")

# ❌ Blocking the event loop
async def read_page(...):
    return wiki.get_page(page_id)       # no to_thread — blocks uvicorn

# ❌ WikiQuery per-request
def get_wiki(config=Depends(get_config)) -> WikiQuery:
    return WikiQuery(config)            # FAISS reloads on every request

# ❌ QueryTimeoutError in error map
ERROR_MAP = {QueryTimeoutError: (200, "QUERY_TIMEOUT")}  # 200 is not an error

# ❌ Synthesis as synchronous function
def synthesize(query, pages) -> SynthesisResult:          # blocks; no streaming upgrade path
    return SynthesisResult(...)
```

## Project Structure & Boundaries

### Complete Project Directory Structure

```
llm_wiki/
├── pyproject.toml                     # uv/hatchling build; extras: vector, claude-agent
├── uv.lock
├── .python-version                    # 3.11
├── README.md
├── Dockerfile                         # multi-stage build; uid 1000 llmwiki user
├── docker-compose.yml                 # wiki_data + config mounts; port 3050
├── supervisord.conf                   # uvicorn + daemon processes
├── .dockerignore
├── .github/
│   └── workflows/
│       └── ci.yml                     # Python 3.11 + 3.12 matrix; ruff, mypy, pytest, codecov
├── scripts/
│   └── export_openapi.py              # exports docs/openapi.json; run in CI for contract drift detection
├── config/                            # example configs (mounted read-only at /config in container)
│   ├── daemon.yaml
│   ├── domains.yaml
│   ├── models.yaml
│   └── routing.yaml
├── docs/
│   ├── openapi.json                   # committed OpenAPI 3.1 spec; offline reference for integrators
│   ├── ARCHITECTURE.md
│   ├── CLI.md
│   └── ...
├── src/
│   └── llm_wiki/
│       ├── __init__.py
│       ├── cli.py                     # Click CLI — thin wrappers only; no business logic
│       ├── deps.py                    # get_wiki(), get_profile_id(); shared by api/ and mcp/
│       ├── exceptions.py              # ALL WikiError subclasses — single canonical definition
│       ├── initializer.py             # WikiInitializer.initialize(wiki_root); idempotent
│       │
│       ├── api/
│       │   ├── __init__.py
│       │   ├── app.py                 # FastAPI app; lifespan; _maybe_init_wiki_root(); mounts routers
│       │   ├── errors.py              # ERROR_MAP; wiki_error_to_http(); imports from llm_wiki.exceptions
│       │   ├── models.py              # API Pydantic models (split to api/models/ when >300 lines)
│       │   └── routers/
│       │       ├── __init__.py
│       │       ├── health.py          # GET /v1/health, /v1/daemon/status, /v1/daemon/jobs
│       │       ├── query.py           # POST /v1/query, GET /v1/query/{job_id}
│       │       ├── ingest.py          # POST /v1/ingest, GET /v1/ingest/{job_id}
│       │       ├── search.py          # GET /v1/search
│       │       ├── pages.py           # GET /v1/pages, GET /v1/pages/{page_id}
│       │       ├── export.py          # POST /v1/export, GET /v1/export/{format}
│       │       └── domains.py         # GET /v1/domains
│       │
│       ├── mcp/
│       │   ├── __init__.py
│       │   ├── server.py              # MCP Server; Streamable HTTP at /mcp; tool registration
│       │   └── tools.py              # @server.tool() definitions; imports from llm_wiki.deps
│       │
│       ├── synthesis/                 # top-level module; Sprint 3 expansion ready
│       │   ├── __init__.py
│       │   └── engine.py             # async generator; SynthesisChunk; asyncio.timeout()
│       │   # Sprint 3 additions (don't create yet):
│       │   # cache.py               — SynthesisCacheJob (FR48)
│       │   # cross_domain.py        — CrossDomainSummaryJob (FR47)
│       │   # authority.py           — AuthorityScorer (FR45)
│       │
│       ├── hooks/                     # Claude Code session capture (FR33, FR34)
│       │   ├── __init__.py
│       │   └── manager.py            # HooksManager.install() / .uninstall()
│       │
│       ├── daemon/
│       │   ├── __init__.py
│       │   ├── __main__.py           # entry point: `python -m llm_wiki.daemon`
│       │   ├── main.py               # WikiDaemon; BackgroundScheduler; ThreadPoolExecutor(max_workers=2)
│       │   └── jobs/
│       │       ├── __init__.py
│       │       ├── inbox_scan.py      # InboxScanJob (15s) — FR1, FR7, FR51
│       │       ├── queue_to_pages.py  # QueueToPagesJob (15min) — FR26, FR29
│       │       ├── retry_failed.py    # RetryFailedIngestsJob (30min)
│       │       ├── index_rebuild.py   # IndexRebuildJob (30min) — FR19, NFR-R4
│       │       ├── export.py          # ExportJob (60min) — FR30, FR31
│       │       ├── governance.py      # GovernanceJob (60min) — FR16-23
│       │       ├── review_queue.py    # ReviewQueueJob (60min) — FR25, FR29
│       │       ├── staleness.py       # StalenessJob (24h) — FR21, FR50a
│       │       └── duplicates.py      # DuplicatesJob (24h)
│       │
│       ├── models/
│       │   ├── __init__.py
│       │   ├── page.py                # PageFrontmatter + subtypes; generate_page_id(); create_frontmatter()
│       │   └── config.py              # WikiConfig; DaemonConfig; DomainsYAML (scope/owner fields Sprint 1)
│       │
│       ├── query/
│       │   ├── __init__.py
│       │   ├── search.py              # WikiQuery; scope_to_profile; threading.Lock registry
│       │   └── log.py                # QueryLogStore (SQLite; check_same_thread=False)
│       │
│       ├── index/
│       │   ├── __init__.py
│       │   ├── fulltext.py            # FulltextIndex — TF-IDF BM25; atomic save
│       │   ├── vector.py              # VectorIndex — FAISS IndexFlatL2 384-dim; optional dep guard
│       │   ├── metadata.py            # MetadataIndex — tag/kind/domain/status lookups
│       │   ├── backlinks.py           # BacklinkIndex — reverse link tracking
│       │   └── graph.py               # GraphEdgeIndex — bidirectional typed edges
│       │
│       ├── ingestion/
│       │   ├── __init__.py
│       │   ├── watcher.py             # InboxWatcher — watchdog FileSystemEventHandler
│       │   ├── normalizer.py          # Normalizer → NormalizedDocument
│       │   ├── router.py              # DomainRouter — routing.yaml rules; staging on no-match (FR53)
│       │   ├── integrator.py          # DeterministicIntegrator — merge strategies; rollback on failure
│       │   ├── tracker.py             # FailedIngestionTracker
│       │   └── adapters/
│       │       ├── __init__.py
│       │       ├── markdown.py        # MarkdownAdapter (FR4)
│       │       ├── text.py
│       │       ├── obsidian.py
│       │       └── claude_session.py  # ClaudeSessionAdapter (FR3, FR6, FR33)
│       │
│       ├── extraction/
│       │   ├── __init__.py
│       │   ├── enrichment.py          # EnrichmentPipeline
│       │   ├── claims.py              # claim extraction + provenance tagging (FR42)
│       │   ├── entities.py
│       │   ├── concepts.py
│       │   ├── relationships.py
│       │   └── qa.py                  # QA pair generation (FR6)
│       │
│       ├── governance/
│       │   ├── __init__.py
│       │   ├── linter.py              # frontmatter validation; orphan detection (FR16)
│       │   ├── staleness.py           # staleness detection; archive lifecycle (FR21, FR50a)
│       │   ├── quality.py             # multi-factor quality scoring (FR28)
│       │   ├── contradictions.py      # negation/numerical/semantic contradiction detection (FR20)
│       │   ├── duplicates.py          # near-duplicate detection
│       │   └── routing_mistakes.py    # wrong-domain detection (FR22)
│       │
│       ├── review/
│       │   └── queue.py               # ReviewQueue — pending/approved/rejected/deferred (FR25)
│       │
│       ├── export/
│       │   ├── __init__.py
│       │   ├── llms_text.py           # LlmsTextExporter (FR30)
│       │   ├── llms_full.py
│       │   ├── json_sidecar.py
│       │   ├── graph.py
│       │   └── sitemap.py
│       │
│       ├── promotion/
│       │   ├── __init__.py
│       │   ├── scorer.py              # PromotionScorer — authority scoring (FR45)
│       │   └── engine.py              # PromotionEngine — auto-promote thresholds (FR46)
│       │
│       └── llm/
│           └── client.py              # LLMClient — OpenAI-compatible; base_url override
│
└── tests/
    ├── conftest.py                    # temp_dir, wiki_root fixtures — always use these
    ├── unit/
    │   ├── test_query_search.py
    │   ├── test_query_log.py
    │   ├── test_synthesis_engine.py
    │   ├── test_exceptions.py         # all WikiError subclasses in exceptions.py
    │   ├── test_initializer.py        # WikiInitializer idempotency
    │   ├── test_hooks_manager.py
    │   ├── test_index_fulltext.py
    │   ├── test_index_vector.py       # pytest.importorskip("faiss"); @pytest.mark.slow
    │   ├── test_index_metadata.py
    │   ├── test_index_backlinks.py
    │   ├── test_index_graph.py
    │   ├── test_ingestion_adapters.py
    │   ├── test_ingestion_router.py
    │   ├── test_ingestion_integrator.py
    │   ├── test_governance_linter.py
    │   ├── test_governance_contradictions.py
    │   ├── test_governance_duplicates.py
    │   ├── test_review_queue.py
    │   ├── test_export_llms.py
    │   ├── test_promotion.py
    │   ├── test_api_errors.py
    │   ├── test_api_models.py
    │   └── test_mcp_tools.py
    └── integration/
        ├── test_ingest_pipeline.py
        ├── test_query_pipeline.py
        ├── test_api_integration.py    # FastAPI TestClient; full request/response cycle
        └── test_docker_startup.py     # @pytest.mark.integration; cold start ≤30s; /v1/health
```

### Structural Rules

1. **`llm_wiki/deps.py` is the shared DI root** — both `api/` and `mcp/` import `get_wiki()` and `get_profile_id()` from here. Never import from `llm_wiki.api.deps` in MCP code.
2. **`exceptions.py` is the only place to define `WikiError` subclasses** — never define exceptions in routers, tools, or service files. Verify: `grep -r 'class.*Error.*WikiError' src/` must return only `exceptions.py` hits.
3. **`api/models.py` split threshold** — split into `api/models/` sub-package when >300 lines; `__init__.py` re-exports all public models so import paths don't change for callers.
4. **`synthesis/` is top-level** — `query/synthesis.py` does not exist. Sprint 3 additions extend `synthesis/` without moving files.
5. **Daemon entry point** — supervisord runs `python -m llm_wiki.daemon` via `__main__.py`. Never reference `daemon/main.py` directly in process configs.
6. **OpenAPI contract gate** — `scripts/export_openapi.py` runs in CI; `docs/openapi.json` diff is surfaced for review on any change. API additions are allowed; removals/renames require explicit review.

### Architectural Boundaries

**API Boundary — configurable port (default 3050):**
```
MCP harnesses  →  http://{host}:{port}/mcp  (Streamable HTTP)
               →  stdio (process spawn)
REST clients   →  http://{host}:{port}/v1/
                    │
            uvicorn (FastAPI)
                    │
            api/routers/*  →  service classes  →  WikiQuery (app.state.wiki, singleton)
```

**Daemon Boundary — filesystem only, no network:**
```
APScheduler (BackgroundScheduler)
    └── reads/writes /wiki/wiki_system/ directly
    └── WikiQuery (shared singleton with API; threading.Lock guards writes)
    └── no HTTP calls; no shared memory with uvicorn except the filesystem
```

**Config Boundary — read-only at startup:**
```
/config/*.yaml  →  WikiConfig.load()  →  Pydantic validation  →  app.state.wiki
```
Config changes take effect on process restart (NFR-O3). No hot-reload in V1.

**Data Boundary — filesystem as source of truth:**
```
/wiki/wiki_system/
    ├── domains/*/pages/*.md  →  authoritative; never query indexes for page existence
    ├── index/*.json, *.faiss →  derived caches; rebuilt by IndexRebuildJob on corruption
    ├── state/jobs.json        →  authoritative daemon job history; atomic writes only
    ├── state/query_log.db     →  synthesis cache query log; SQLite
    └── logs/changelog.jsonl  →  append-only; never open for write/truncate
```

### Runtime Volume Structure

```
wiki_data/                          # host dir, owned by uid 1000; mounted at /wiki
└── wiki_system/
    ├── inbox/
    │   ├── new/                    # sources arrive here
    │   ├── processing/             # orphans recovered on startup (P0-3 fix)
    │   ├── done/
    │   └── failed/
    ├── domains/
    │   └── {domain}/
    │       ├── pages/             # published pages — source of truth
    │       └── queue/             # staging before promotion
    ├── shared/                    # cross-domain promoted entities (FR46)
    ├── index/
    │   ├── fulltext.json
    │   ├── vector_index.faiss
    │   ├── vector_meta.json
    │   ├── metadata.json
    │   ├── backlinks.json
    │   └── graph_edges.json
    ├── exports/
    ├── reports/
    ├── review_queue/
    │   ├── pending/
    │   ├── approved/
    │   ├── rejected/
    │   └── deferred/
    ├── state/
    │   ├── jobs.json              # authoritative daemon job history
    │   └── query_log.db           # synthesis cache query log (SQLite)
    └── logs/
        └── changelog.jsonl        # append-only; never truncate

config/                             # host dir; read-only at /config
├── daemon.yaml
├── domains.yaml
├── models.yaml
└── routing.yaml
```

### Integration Points

**Agent harness → llm-wiki:**
- MCP Streamable HTTP: `http://{host}:{port}/mcp`; runs as sidecar container on same VM
- MCP stdio: process spawn; harness selects transport per connection config
- Profile scoping: `X-Profile-Id` header (REST), `profile_id` param (MCP); harness populates these
- llm-wiki trusts the caller; no auth layer in llm-wiki itself
- Domain contract: omit `domain` → household + user-{id} merged; `household` → shared only; `user-{id}` → personal only

**Claude Code hooks → inbox:**
- `SessionEnd` / `PreCompact` hooks write to `wiki_system/inbox/new/`
- `hooks/manager.py` manages install/uninstall (FR33, FR34)

**Development workflow:**
```bash
uv sync --extra vector
uv run uvicorn llm_wiki.api.app:app --reload --port 3050   # local REST + MCP
uv run python -m llm_wiki.daemon                            # daemon separately
docker-compose up --build                                   # full stack
uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run pytest  # CI gates
```

---

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:**
All technology choices are compatible and work together without conflict. FastAPI + uvicorn are native async Python; Pydantic v2 is FastAPI's native validation layer; FAISS + sentence-transformers are optional extras guarded at import time; APScheduler runs in a separate thread pool isolated from uvicorn's event loop; SQLite handles concurrent writes from thread pool workers via `check_same_thread=False`. supervisord's two-process model cleanly separates the uvicorn and daemon concern boundaries.

**Pattern Consistency:**
Implementation patterns are consistent across all three interfaces (CLI, REST, MCP). Naming conventions (`verb_noun` for MCP, `/v1/{resource}` for REST, `{Resource}Request`/`{Resource}Response` for Pydantic models) are enforced by structural rules. Error handling routes through a single `errors.py` ERROR_MAP for both REST and MCP. Async/sync boundaries consistently use `asyncio.to_thread()` for all I/O in async contexts.

**Structure Alignment:**
The directory structure directly supports all architectural decisions: `deps.py` at package root eliminates cross-module DI imports; `synthesis/` as a top-level module enables Sprint 3 expansion without file moves; `exceptions.py` as the single canonical location supports the ERROR_MAP pattern; the `api/models.py` split threshold is pre-specified. All four boundaries (API, daemon, config, data) map to specific, non-overlapping filesystem paths.

### Requirements Coverage Validation ✅

**Epic/Feature Coverage:**
All 9 FR categories have direct architectural support. Sprint 1 FRs are covered by the complete directory structure and implementation patterns. Sprint 2 FRs (trust and provenance) are supported by the existing extraction pipeline and claims tracking. Sprint 3 FRs (cross-domain synthesis) are pre-positioned in `synthesis/` with the async generator protocol as the invariant.

**Functional Requirements Coverage:**

| FR Group | Coverage |
|---|---|
| FR1-7, FR51, FR58 (ingestion) | InboxScanJob + adapters + normalizer + router + integrator |
| FR8-12, FR54, FR57, FR59 (query) | WikiQuery.search() + query log + synthesis engine |
| FR13-15, FR52 (search) | FulltextIndex + VectorIndex + RRF fusion in WikiQuery |
| FR16-23 (governance) | GovernanceJob + governance/* modules |
| FR24-29, FR53, FR63 (knowledge mgmt) | ReviewQueue + QueueToPagesJob + PromotionEngine |
| FR30-34 (export + integration) | ExportJob + export/* + HooksManager |
| FR35-41, FR55, FR60, FR61 (service ops) | FastAPI routes + initializer + health endpoints |
| FR42-44 (trust + provenance) | claims.py + provenance tagging in extraction pipeline |
| FR45-50b, FR62 (synthesis) | synthesis/engine.py + synthesis/* expansion path |

**Non-Functional Requirements Coverage:**
- **Performance:** ≤200ms supported by WikiQuery singleton (FAISS loads once) + `asyncio.to_thread()` for non-blocking routes; 30s timeout enforced via `asyncio.timeout()` in synthesis engine
- **Reliability:** Atomic index writes (tmp→`os.replace`) + threading.Lock registry in WikiQuery; 60s crash recovery via supervisord `autorestart=true`; `startretries=5` for daemon
- **Integration:** OpenAPI 3.1 auto-generated by FastAPI + committed to `docs/openapi.json`; dual MCP transports documented; `--json` flag pattern documented for all CLI read commands
- **Operability:** ≤30s cold start via minimal lifespan setup + FAISS lazy load on first search; YAML config takes effect on restart (NFR-O3)
- **Data Integrity:** `generate_page_id()` enforced throughout; changelog JSONL append-only pattern documented; idempotent merge strategies in DeterministicIntegrator
- **Security:** `0.0.0.0` binding inside container; docker-compose port mapping controls exposure; VM-level isolation is the security boundary

### Implementation Readiness Validation ✅

**Decision Completeness:**
All 13 critical decisions are documented with specific versions, exact APIs, and code examples: FastAPI+uvicorn on port 3050, Pydantic v2 model naming, supervisord `nodaemon=true`, FAISS IndexFlatL2 (384-dim), SQLite `check_same_thread=False`, synthesis async generator protocol, WikiQuery singleton lifespan pattern, ERROR_MAP design (including the counter-intuitive exclusion of `QueryTimeoutError`), and domain scope via `deps.py`.

**Structure Completeness:**
Complete directory tree defined to the file level for all 50+ source files. All integration points mapped: API boundary (port 3050), daemon boundary (filesystem-only, no network), config boundary (read-only at startup), data boundary (filesystem as source of truth). Component boundaries explicitly stated with anti-pattern code blocks.

**Pattern Completeness:**
13 critical rules documented, with the top 3 failure modes highlighted separately. Anti-pattern code blocks provided for all critical failure modes. Async/sync boundary documented with specific examples of what requires `asyncio.to_thread()` vs. what does not. Synthesis generator protocol documented as an architectural invariant with explicit prohibition on converting it to a synchronous function. Error handling fully specified including the `ERROR_MAP` design and why `QueryTimeoutError` is excluded.

### Gap Analysis Results

**Important Gaps:**
1. **supervisord `nodaemon=true` operational note:** Without this directive, the Docker container exits immediately after supervisord forks. Documented in the supervisord.conf pattern — critical for first-time Docker setup and must appear in the `[supervisord]` section explicitly.

*(Previously: FAISS in-memory staleness after IndexRebuildJob — resolved. `IndexRebuildJob` now calls `wiki.reload_vector_index()` after completing the rebuild sweep; WikiQuery acquires the vector lock, swaps the in-memory FAISS instance from the new file, and releases. See Index Write Concurrency section.)*

**Nice-to-Have Gaps:**
1. **FR61 `updated_since` filter:** Not yet included in search patterns. Straightforward MetadataIndex query filter addition to `WikiQuery.search()` when FR61 is scheduled for implementation.
2. **Docker HEALTHCHECK directive:** Not present in the Dockerfile pattern. Recommend adding `HEALTHCHECK CMD curl -f http://localhost:${WIKI_PORT:-3050}/v1/health || exit 1` as a standard Docker health probe for container readiness detection.

### Validation Issues Addressed

All architectural issues surfaced during Advanced Elicitation (Code Review Gauntlet + Self-Consistency Validation in Step 5; Architecture Decision Records in Step 6) were resolved before validation:

| ADR | Issue | Resolution |
|---|---|---|
| ADR-1 | Cross-module DI conflict: `mcp/tools.py` importing from `api/deps.py` | `deps.py` moved to package root; both api/ and mcp/ import from `llm_wiki.deps` |
| ADR-2 | WikiQuery DI contradiction (per-request construction vs. FAISS singleton) | WikiQuery is a singleton on `app.state` via lifespan; never instantiated in Depends |
| ADR-3 | `QueryTimeoutError` in ERROR_MAP returns HTTP 200 as an error | Removed from ERROR_MAP; handled as normal inline response branch |
| ADR-4 | Synthesis at `query/synthesis.py` requires file move at Sprint 3 | Located at `synthesis/engine.py` top-level from Sprint 1 |
| ADR-5 | supervisord missing `nodaemon=true` causing container exit | Added `[supervisord]` section with `nodaemon=true` |
| ADR-6 | Deep query REST transport — sync vs async | Both MCP and REST use async polling for deep queries; in-memory job state; 404-on-restart acceptable |
| ADR-7 | Profile scoping inconsistency across REST and MCP | `X-Profile-Id` header (REST) + `profile_id` MCP param both route to `WikiQuery.search(scope_to_profile=...)` |
| ADR-8 | Query log: JSONL insufficient for cross-domain analysis (FR48, 50+ domains) | SQLite at `state/query_log.db` with `check_same_thread=False` |

### Architecture Completeness Checklist

**Requirements Analysis**

- [x] Project context thoroughly analyzed
- [x] Scale and complexity assessed
- [x] Technical constraints identified
- [x] Cross-cutting concerns mapped

**Architectural Decisions**

- [x] Critical decisions documented with versions
- [x] Technology stack fully specified
- [x] Integration patterns defined
- [x] Performance considerations addressed

**Implementation Patterns**

- [x] Naming conventions established
- [x] Structure patterns defined
- [x] Communication patterns specified
- [x] Process patterns documented

**Project Structure**

- [x] Complete directory structure defined
- [x] Component boundaries established
- [x] Integration points mapped
- [x] Requirements to structure mapping complete

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level:** High — all 16 checklist items verified; no critical gaps remain; all ADRs resolved.

**Key Strengths:**
- All 13 implementation rules are specific, verifiable, and include counter-examples and anti-pattern code blocks
- Sprint 3 expansion pre-positioned: `synthesis/` module structure + async generator protocol ensure no re-arch needed at Sprint 3
- Multi-user domain scoping fully specified: `X-Profile-Id` / `profile_id` pattern, `WikiQuery.search(scope_to_profile=...)`, household + personal domain merge semantics
- Feature flag system enables LLM-optional operation from day one; heuristic path is first-class, not a fallback footnote
- Brownfield constraints respected throughout: existing file-based storage, daemon job patterns, and APScheduler wiring are unchanged
- Error handling consolidated: single `exceptions.py` + single `errors.py` ERROR_MAP eliminates scattered exception handling across routers and tools

**Areas for Future Enhancement:**
- Docker `HEALTHCHECK` directive (add to Dockerfile for container orchestration readiness probes)
- FR61 `updated_since` filter in `WikiQuery.search()` (when scheduled)
- REST streaming upgrade for deep query endpoint (async generator protocol already supports it without synthesis changes)

### Implementation Handoff

**AI Agent Guidelines:**
- Follow all architectural decisions exactly as documented
- Use implementation patterns consistently across all components
- Respect project structure and boundaries — no new top-level modules without architecture update
- Refer to this document for all architectural questions; `project-context.md` for Python/framework rules

**First Implementation Priority:**
Sprint 1 — implement in this order to avoid re-work:
1. `exceptions.py` + `initializer.py` — no deps; used by everything above them
2. `deps.py` — depends on WikiQuery (already exists); shared DI foundation
3. `api/app.py` lifespan + `api/errors.py` ERROR_MAP — stack wiring
4. `api/routers/health.py` + `api/routers/query.py` — validate the full stack end-to-end
5. `mcp/server.py` + `mcp/tools.py` — parallel to REST; shares `deps.py`
6. `synthesis/engine.py` — async generator; needed by deep query route
7. `query/log.py` SQLite store — needed by query routes
8. `Dockerfile` + `supervisord.conf` + `docker-compose.yml` — container packaging

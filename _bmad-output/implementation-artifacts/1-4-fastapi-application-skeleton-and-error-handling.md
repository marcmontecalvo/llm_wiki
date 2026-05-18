# Story 1.4: FastAPI Application Skeleton and Error Handling

Status: ready-for-dev

## Story

As a service developer,
I want a FastAPI application with proper lifespan management, a singleton WikiQuery, and centralized error handling,
so that all REST and MCP surfaces share a reliable, consistent service foundation with no duplicated error logic.

## Acceptance Criteria

1. **Given** the FastAPI app lifespan starts **When** it runs **Then** `_maybe_init_wiki_root(wiki_root)` is called **before** `WikiConfig.load()` — a fresh empty volume raises `FileNotFoundError` if this order is reversed.

2. **Given** the FastAPI app lifespan runs **When** complete **Then** `WikiQuery` is instantiated exactly once and stored on `app.state.wiki`; the FAISS index loads once here.

3. **Given** a route calls `Depends(get_wiki)` **When** executed **Then** it returns `app.state.wiki` — the same singleton for every request; no new `WikiQuery` is constructed.

4. **Given** a `WikiNotFoundError` is raised anywhere in a route or service call **When** the exception handler fires **Then** it returns HTTP 404 with body `{"error_code": "WIKI_NOT_FOUND", "message": "...", "rebuild_hint": false}`.

5. **Given** an `IndexStaleError` is raised **When** handled **Then** it returns HTTP 503 with `"rebuild_hint": true` in the response body.

6. **Given** a `DomainUnknownError` raised from a user-supplied POST body field **When** handled **Then** it returns HTTP 422 (not 404) using the status override pattern in `errors.py`.

7. **Given** a `QueryTimeoutError` occurs during a deep query **When** it occurs **Then** it is handled as a normal response branch returning `{"timed_out": true, "partial": true, "results": [...]}` — it is **not** in `ERROR_MAP` and does not become an HTTP error.

8. **Given** any route function calls an I/O-touching service method (disk, FAISS, SQLite) **When** audited **Then** every such call is wrapped in `asyncio.to_thread()` — the event loop is never blocked.

9. **Given** all API Pydantic models **When** defined **Then** they live in `src/llm_wiki/api/models.py` and are named `{Resource}Response` or `{Resource}Request` — never `Schema`, `Model`, or `Out`.

10. **Given** the FastAPI lifespan completes **When** the service starts **Then** an `mcp.Server` instance is created, all MCP tools are registered via `tools.py`, and the Streamable HTTP transport is mounted at `/mcp` on the uvicorn app — the MCP server shares `app.state.wiki` with the REST routes.

11. **Given** the service is fully initialized **When** the scheduler starts **Then** `IndexRebuildJob` is constructed with the `WikiQuery` singleton: `scheduler.add_job(IndexRebuildJob(wiki=app.state.wiki), ...)`.

12. **Given** `synthesize()` is called with `llm_extraction: false` **When** executed **Then** it uses the heuristic path (pages sorted by confidence, concatenated) and `DeepQueryResult.was_heuristic` is `true` — no LLM is attempted.

13. **Given** `synthesize()` is called with `llm_extraction: true` and the LLM call raises any exception **When** the error occurs **Then** the exception is logged, execution falls back to the heuristic path, the query response is still returned, and `DeepQueryResult.was_heuristic` is `true` — synthesis never propagates an LLM error to the caller.

## Tasks / Subtasks

- [ ] Create `src/llm_wiki/exceptions.py` — canonical WikiError subclasses (AC: 4, 5, 6, 7)
  - [ ] `WikiError(Exception)` — base class
  - [ ] `WikiNotFoundError(WikiError)` — 404 WIKI_NOT_FOUND
  - [ ] `DomainUnknownError(WikiError)` — 404 (or 422 when user-supplied) DOMAIN_UNKNOWN
  - [ ] `IngestError(WikiError)` — 422 INGEST_ERROR
  - [ ] `IndexStaleError(WikiError)` — 503 INDEX_STALE (rebuild_hint: true)
  - [ ] `DaemonNotRunningError(WikiError)` — 503 DAEMON_NOT_RUNNING
  - [ ] `ExportNotReadyError(WikiError)` — 404 EXPORT_NOT_READY
  - [ ] `InvalidDepthError(WikiError)` — 422 INVALID_DEPTH
  - [ ] `QueryTimeoutError(WikiError)` — NOT in ERROR_MAP; normal response branch
- [ ] Create `src/llm_wiki/initializer.py` — wiki directory structure setup (AC: 1)
  - [ ] `WikiInitializer.initialize(wiki_root: Path)` — idempotent; creates all required subdirs
  - [ ] `_maybe_init_wiki_root(wiki_root: Path)` — calls initialize only if `domains/` doesn't exist
- [ ] Create `src/llm_wiki/deps.py` — shared DI functions (AC: 3)
  - [ ] `get_wiki(request: Request) -> WikiQuery` — returns `request.app.state.wiki`
  - [ ] `get_profile_id(x_profile_id: str | None = Header(default=None)) -> str | None`
- [ ] Create `src/llm_wiki/api/errors.py` — ERROR_MAP and exception handler (AC: 4, 5, 6, 7)
  - [ ] `ERROR_MAP: dict[type[WikiError], tuple[int, str]]` — maps exception types to (status_code, error_code)
  - [ ] `rebuild_hint` is True only for `IndexStaleError`
  - [ ] `QueryTimeoutError` MUST NOT be in ERROR_MAP
  - [ ] `wiki_error_to_http(exc, status_override=None)` — converts WikiError to HTTPException
  - [ ] `register_exception_handlers(app: FastAPI)` — registers all handlers on the app
- [ ] Create `src/llm_wiki/api/models.py` — API Pydantic request/response models (AC: 9)
  - [ ] `ErrorResponse(error_code: str, message: str, rebuild_hint: bool = False)`
  - [ ] `HealthResponse`, `DaemonStatusResponse` (stub — populated in Story 1.6)
  - [ ] `QueryRequest(query: str, depth: str = "quick", domain: str | None = None)`
  - [ ] `QueryResponse(results: list, timed_out: bool = False, partial: bool = False, vector_search: bool = False)`
  - [ ] `IngestRequest`, `IngestStatusResponse` (stub)
  - [ ] `SearchResponse` (stub)
  - [ ] `PageResponse`, `PageListResponse` (stub)
  - [ ] `ExportResponse` (stub)
- [ ] Create `src/llm_wiki/api/app.py` — FastAPI app + lifespan (AC: 1, 2, 3, 8, 10, 11)
  - [ ] `_maybe_init_wiki_root(wiki_root)` called FIRST in lifespan
  - [ ] Load config from `WIKI_CONFIG_DIR` env var (default `/config`)
  - [ ] Instantiate `WikiQuery(config)` once → `app.state.wiki`
  - [ ] Initialize `app.state.deep_jobs: dict[str, DeepQueryJob] = {}`
  - [ ] Mount MCP server at `/mcp` (see MCP skeleton below)
  - [ ] Register exception handlers via `register_exception_handlers(app)`
  - [ ] Add `X-LLM-Wiki-Version` middleware
- [ ] Create `src/llm_wiki/synthesis/engine.py` — async generator (AC: 7 via deep query support)
  - [ ] `SynthesisChunk(text: str, is_final: bool, sources: list[str])`
  - [ ] `_synthesize_heuristic(query, pages)` — heuristic fallback: pages sorted by confidence, concatenated
  - [ ] `_synthesize_llm(query, pages)` — raises `NotImplementedError` until Epic 2; marked as the LLM path
  - [ ] `synthesize(query, pages, llm_extraction: bool)` — single entry point; routes to LLM or heuristic; catches all LLM exceptions and falls back to heuristic with error logging
  - [ ] `run_deep_query(query, pages, llm_extraction, timeout=30.0) -> DeepQueryResult` — uses `asyncio.timeout()`
  - [ ] `DeepQueryResult(chunks: list, timed_out: bool, partial: bool, was_heuristic: bool)`
- [ ] **MCP SDK spike — complete before writing any MCP skeleton code** (AC: 10)
  - [ ] Run `uv add mcp` and inspect the installed package: verify exact import paths for `Server`, the Streamable HTTP transport class, and the ASGI mount API
  - [ ] Write a minimal spike in `src/llm_wiki/mcp/server.py`: create an `mcp.Server`, register one no-op tool (`tools/list` returns `[]`), mount at `/mcp`, and verify `GET /mcp` responds without error using `TestClient`
  - [ ] **Do not proceed to Stories 1.6–1.9 MCP work until this spike passes** — all downstream MCP tools depend on the correct mount API
  - [ ] Document the verified import paths in a comment at the top of `server.py`
- [ ] Create `src/llm_wiki/mcp/server.py` + `tools.py` skeleton (AC: 10)
  - [ ] `server.py`: implement using the verified SDK API from the spike above
  - [ ] `tools.py`: empty module; tools registered in Story 1.8
- [ ] Create `src/llm_wiki/api/routers/__init__.py` (empty — routers added in 1.6/1.7)
- [ ] Write tests (see Testing section)

## Dev Notes

### WikiConfig Loading — Current vs Target

**Current state:** `WikiConfig` is defined in `src/llm_wiki/models/config.py` and has `domains`, `daemon`, `routing`, `models` fields. However, looking at `src/llm_wiki/config/loader.py` (the actual loader), there's a `load_config()` function. The FastAPI app should use the existing config loading infrastructure, not duplicate it.

**Check first:** Read `src/llm_wiki/config/loader.py` before implementing — the exact API for loading config may differ from `WikiConfig.load()`.

### WikiQuery Constructor — Current State

`WikiQuery` in `src/llm_wiki/query/search.py` currently takes `wiki_base` and `index_dir` params. After Story 1.1, it will have `_index_locks`. The FastAPI lifespan should instantiate it with the path to the wiki root (`WIKI_ROOT` env var).

**Important:** `WikiQuery` is synchronous. FAISS loads during `__init__`. This blocks the event loop. Solution: wrap in `asyncio.to_thread()` OR keep it synchronous in the lifespan (lifespan runs once, not per-request, so blocking here is acceptable as a startup cost).

### `_maybe_init_wiki_root()` Order Constraint

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    wiki_root = Path(os.environ.get("WIKI_ROOT", "wiki_system"))
    config_dir = Path(os.environ.get("WIKI_CONFIG_DIR", "/config"))

    # MUST be first — WikiConfig.load() raises FileNotFoundError on empty volume
    _maybe_init_wiki_root(wiki_root)

    config = load_config(config_dir)              # SECOND
    app.state.wiki = WikiQuery(wiki_root=wiki_root, config=config)  # THIRD — FAISS loads here
    app.state.deep_jobs: dict[str, Any] = {}
    yield
```

### ERROR_MAP Pattern

```python
# src/llm_wiki/api/errors.py
from llm_wiki.exceptions import (
    WikiNotFoundError, DomainUnknownError, IngestError,
    IndexStaleError, DaemonNotRunningError, ExportNotReadyError, InvalidDepthError,
)

ERROR_MAP: dict[type, tuple[int, str]] = {
    WikiNotFoundError:      (404, "WIKI_NOT_FOUND"),
    DomainUnknownError:     (404, "DOMAIN_UNKNOWN"),
    IngestError:            (422, "INGEST_ERROR"),
    IndexStaleError:        (503, "INDEX_STALE"),
    DaemonNotRunningError:  (503, "DAEMON_NOT_RUNNING"),
    ExportNotReadyError:    (404, "EXPORT_NOT_READY"),
    InvalidDepthError:      (422, "INVALID_DEPTH"),
}
# QueryTimeoutError is intentionally absent — it's a normal response branch

def wiki_error_to_http(exc: WikiError, status_override: int | None = None) -> HTTPException:
    status, error_code = ERROR_MAP.get(type(exc), (500, "INTERNAL_ERROR"))
    if status_override is not None:
        status = status_override
    rebuild_hint = isinstance(exc, IndexStaleError)
    return HTTPException(
        status_code=status,
        detail={"error_code": error_code, "message": str(exc), "rebuild_hint": rebuild_hint},
    )
```

### MCP Server Skeleton

**Run the spike first.** The import paths and mount API below are based on the expected SDK shape but must be verified against the installed package before use. After `uv add mcp`, check the actual module structure and update these snippets if they differ.

```python
# src/llm_wiki/mcp/server.py
# VERIFIED IMPORTS — update after spike confirms actual SDK API
from mcp.server import Server
from mcp.server.streamable_http import StreamableHTTPTransport  # verify this path

def create_mcp_server(wiki) -> tuple[Server, StreamableHTTPTransport]:
    """Create MCP server and transport. Tools registered in tools.py."""
    server = Server("llm-wiki")
    from llm_wiki.mcp.tools import register_tools
    register_tools(server, wiki)
    transport = StreamableHTTPTransport(server)  # verify constructor signature
    return server, transport
```

```python
# src/llm_wiki/api/app.py — in lifespan, after wiki singleton created
from llm_wiki.mcp.server import create_mcp_server
_, mcp_transport = create_mcp_server(app.state.wiki)
app.mount("/mcp", mcp_transport)  # verify mount API accepts ASGI transport directly
```

### `X-LLM-Wiki-Version` Header Middleware

```python
# In app.py
from llm_wiki import __version__

@app.middleware("http")
async def add_version_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-LLM-Wiki-Version"] = __version__
    return response
```

### Synthesis Engine — Async Generator Invariant

The synthesis engine MUST be an async generator. This is an architectural invariant that enables future REST streaming. Never convert it to a synchronous function.

`synthesize()` is the single call site for all callers. It handles the `llm_extraction` flag and LLM failure fallback internally — callers never need to choose a path. The `was_heuristic` flag on `DeepQueryResult` tells callers (and logs) which path ran.

**Fallback contract:**
- `llm_extraction: false` → heuristic path directly, no LLM attempted
- `llm_extraction: true` → try LLM; on any exception (connection error, API error, timeout) log the error and fall back to heuristic; set `was_heuristic: true` on the result

```python
# src/llm_wiki/synthesis/engine.py
from dataclasses import dataclass, field
from typing import AsyncGenerator
import asyncio
import logging

logger = logging.getLogger(__name__)

@dataclass
class SynthesisChunk:
    text: str
    is_final: bool = False
    sources: list[str] = field(default_factory=list)

@dataclass
class DeepQueryResult:
    chunks: list[SynthesisChunk]
    timed_out: bool
    partial: bool
    was_heuristic: bool = False  # True if LLM was unavailable/failed or llm_extraction=false

async def _synthesize_heuristic(
    query: str,
    pages: list,
) -> AsyncGenerator[SynthesisChunk, None]:
    """Heuristic fallback: pages sorted by confidence, concatenated. Sprint 1 implementation.
    Also serves as the permanent fallback when LLM synthesis fails in later epics."""
    for page in sorted(pages, key=lambda p: getattr(p, 'confidence', 0.0), reverse=True):
        yield SynthesisChunk(
            text=f"## {getattr(page, 'title', page)}\n\n{getattr(page, 'content', '')}",
            sources=[getattr(page, 'id', str(page))],
        )
    yield SynthesisChunk(text="", is_final=True)

async def _synthesize_llm(
    query: str,
    pages: list,
) -> AsyncGenerator[SynthesisChunk, None]:
    """LLM-based synthesis. Implemented in Epic 2. Raises NotImplementedError until then."""
    raise NotImplementedError("LLM synthesis not yet implemented — Epic 2")
    yield  # makes this an async generator

async def synthesize(
    query: str,
    pages: list,
    llm_extraction: bool = False,
) -> AsyncGenerator[SynthesisChunk, None]:
    """Single entry point for synthesis. Handles fallback internally.

    If llm_extraction is False OR the LLM call fails, falls back to heuristic silently
    (with error logging on unexpected LLM failure). Callers check was_heuristic on
    DeepQueryResult to know which path ran.
    """
    if llm_extraction:
        try:
            async for chunk in _synthesize_llm(query, pages):
                yield chunk
            return
        except NotImplementedError:
            pass  # expected until Epic 2
        except Exception as e:
            logger.error("LLM synthesis failed, falling back to heuristic: %s", e)
    async for chunk in _synthesize_heuristic(query, pages):
        yield chunk

async def run_deep_query(
    query: str,
    pages: list,
    llm_extraction: bool = False,
    timeout: float = 30.0,
) -> DeepQueryResult:
    chunks: list[SynthesisChunk] = []
    timed_out = False
    was_heuristic = not llm_extraction  # will be updated below if LLM fails
    try:
        async with asyncio.timeout(timeout):
            async for chunk in synthesize(query, pages, llm_extraction=llm_extraction):
                chunks.append(chunk)
    except TimeoutError:
        timed_out = True
    # was_heuristic: true if flag was off, or if LLM raised and we fell through
    was_heuristic = not llm_extraction or not any(
        True for c in chunks if not c.is_final
    ) or was_heuristic
    return DeepQueryResult(
        chunks=chunks,
        timed_out=timed_out,
        partial=timed_out,
        was_heuristic=was_heuristic,
    )
```

### Project Structure — Files to Create

All files are NEW (this story creates the service layer skeleton):

```
src/llm_wiki/
├── exceptions.py              NEW — all WikiError subclasses
├── initializer.py             NEW — WikiInitializer, _maybe_init_wiki_root()
├── deps.py                    NEW — get_wiki(), get_profile_id()
├── api/
│   ├── __init__.py            NEW
│   ├── app.py                 NEW — FastAPI app + lifespan
│   ├── errors.py              NEW — ERROR_MAP, exception handlers
│   ├── models.py              NEW — API Pydantic models
│   └── routers/
│       └── __init__.py        NEW (empty — routers added in 1.6/1.7)
├── mcp/
│   ├── __init__.py            NEW
│   ├── server.py              NEW — MCP server + /mcp mount
│   └── tools.py               NEW (stub — tools added in 1.8)
└── synthesis/
    ├── __init__.py            NEW
    └── engine.py              NEW — async generator + timeout logic
```

UPDATE `src/llm_wiki/__init__.py` — add `__version__ = "0.1.0"` if not present.

### Testing

**Unit tests for exception handling:** `tests/unit/test_api_errors.py` (new):

```python
def test_wiki_not_found_maps_to_404():
    exc = WikiNotFoundError("page not found")
    http_exc = wiki_error_to_http(exc)
    assert http_exc.status_code == 404
    assert http_exc.detail["error_code"] == "WIKI_NOT_FOUND"
    assert http_exc.detail["rebuild_hint"] is False

def test_index_stale_has_rebuild_hint_true():
    exc = IndexStaleError("stale")
    http_exc = wiki_error_to_http(exc)
    assert http_exc.status_code == 503
    assert http_exc.detail["rebuild_hint"] is True

def test_domain_unknown_status_override_to_422():
    exc = DomainUnknownError("unknown domain")
    http_exc = wiki_error_to_http(exc, status_override=422)
    assert http_exc.status_code == 422

def test_query_timeout_error_not_in_error_map():
    assert QueryTimeoutError not in ERROR_MAP
```

**Integration tests using `TestClient`:** `tests/integration/test_api_integration.py` (new):

```python
from fastapi.testclient import TestClient
from llm_wiki.api.app import app

def test_unknown_route_returns_404():
    client = TestClient(app)
    r = client.get("/v1/nonexistent")
    assert r.status_code == 404

def test_version_header_present():
    client = TestClient(app)
    r = client.get("/v1/health")
    assert "X-LLM-Wiki-Version" in r.headers
```

**Unit tests for WikiInitializer:** `tests/unit/test_initializer.py` (new):

```python
def test_initialize_is_idempotent(temp_dir):
    WikiInitializer.initialize(temp_dir)
    WikiInitializer.initialize(temp_dir)  # should not raise
    assert (temp_dir / "domains").is_dir()

def test_maybe_init_skips_if_already_initialized(temp_dir):
    (temp_dir / "domains").mkdir()
    _maybe_init_wiki_root(temp_dir)  # should be no-op
    # no exception raised
```

### Critical Anti-Patterns to Avoid

- **Never put WikiQuery instantiation in a route or dependency function** — only in `app.py` lifespan
- **Never put QueryTimeoutError in ERROR_MAP** — it's a normal response branch, not an error
- **Never `raise HTTPException` inline for known WikiError types** — always go through `wiki_error_to_http()`
- **Never call `WikiConfig.load()` before `_maybe_init_wiki_root()`** — fresh volume raises FileNotFoundError
- **Never define WikiError subclasses outside `exceptions.py`** — they all live there

### References

- Architecture: "FastAPI Route Structure" — complete patterns
- Architecture: "Error Propagation" — ERROR_MAP design and why QueryTimeoutError is excluded
- Architecture: "Startup Init Sequence" — `_maybe_init_wiki_root()` ordering
- Architecture: "Synthesis Async Generator Protocol" — never convert to sync
- Architecture: "WikiQuery Dependency Injection" — singleton on app.state
- Architecture: Enforcement Guidelines — top 3 critical rules

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List

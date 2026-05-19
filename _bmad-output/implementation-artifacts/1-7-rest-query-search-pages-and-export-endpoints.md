# Story 1.7: REST Query, Search, Pages, and Export Endpoints

Status: done

## Story

As an agent or operator using HTTP,
I want REST endpoints for querying knowledge, searching, reading pages, and retrieving exports,
so that I can access the full wiki capability surface from any HTTP client without MCP.

**Prerequisites:** Stories 1.4 (FastAPI skeleton), 1.5 (feature flags), 1.6 (health/ingest endpoints), and 1.12 (SQLite query log) should be complete or worked in parallel.

**Note on confidence scores:** Sprint 1 returns the confidence values already stored in V1 page frontmatter — no new computation. Sprint 2 (Stories 2.1/2.2) upgrades the confidence computation model. Sprint 1 ACs test that the `confidence` field is present and passes through correctly, not that the values are accurate.

## Acceptance Criteria

1. **Given** `POST /v1/query` with `depth: "quick"` **When** called under normal load **Then** it responds HTTP 200 in ≤200ms (NFR-P1) with results including `confidence`, `provenance`, and `contradictions`.

2. **Given** `POST /v1/query` with `depth: "standard"` **When** called under normal load **Then** it responds HTTP 200 in ≤2s (NFR-P2).

3. **Given** `POST /v1/query` with `depth: "deep"` **When** called **Then** it immediately returns HTTP 202 Accepted with `{"job_id": "...", "status": "queued"}` — never blocks (FR8). HTTP 202 signals "accepted but not yet complete"; clients branch on status code to distinguish synchronous results (200) from async jobs (202).

4. **Given** `GET /v1/query/{job_id}` is called while the job is running **When** called **Then** it returns `{"status": "running", "job_id": "..."}` and a `X-Job-TTL: 300` header.

5. **Given** `GET /v1/query/{job_id}` when the job completes within 30s **When** called after completion **Then** it returns `{"partial": false, "timed_out": false, "results": [...]}`.

6. **Given** `GET /v1/query/{job_id}` when synthesis exceeds 30s **When** the timeout fires **Then** it returns `{"partial": true, "timed_out": true, "results": [...whatever completed...]}`.

7. **Given** `GET /v1/query/{job_id}` when synthesis times out before producing any results **When** called **Then** `results` is `[]` and `timed_out: true` (FR54).

8. **Given** `GET /v1/query/{job_id}` is called after the TTL expires or after a uvicorn restart **When** called **Then** it returns HTTP 404 `WIKI_NOT_FOUND` — job state is in-memory only.

9. **Given** `GET /v1/search?q=<text>` **When** called **Then** it returns merged full-text and vector results, each with confidence scores (FR13, FR15). Vector search is always active — there is no `vector_search` flag in the response.

10. **Given** `GET /v1/pages/{page_id}` when the page exists **When** called **Then** it returns full page content plus all frontmatter provenance metadata (FR11).

11. **Given** `GET /v1/pages/{page_id}` when the page does not exist **When** called **Then** it returns HTTP 404 `WIKI_NOT_FOUND`.

12. **Given** `GET /v1/pages` with `?domain=<d>&kind=<k>&cursor=<token>&limit=50` **When** called **Then** it returns filtered, paginated results with `next_cursor` and `total_hint` (FR12).

13. **Given** `POST /v1/export` followed by `GET /v1/export/{format}` **When** the export exists **Then** the GET returns export content with `generated_at`, `page_count`, and `Last-Modified` header (FR30, FR31).

14. **Given** `GET /v1/export/{format}` before any export has been generated **When** called **Then** it returns HTTP 404 `EXPORT_NOT_READY`.

## Tasks / Subtasks

- [x] Create `src/llm_wiki/api/routers/query.py` (AC: 1-8)
  - [x] `POST /v1/query` — dispatches to quick/standard (sync) or deep (async background task)
  - [x] `GET /v1/query/{job_id}` — polls in-memory `app.state.deep_jobs` dict
  - [x] Deep query: creates background task using `asyncio.create_task()` running `run_deep_query()`
  - [x] TTL cleanup: background task cleans up jobs older than 5 minutes
  - [x] Log query to query log via `QueryLogStore.log()` (Story 1.12)
- [x] Create `src/llm_wiki/api/routers/search.py` (AC: 9)
  - [x] `GET /v1/search?q=<text>` — calls `WikiQuery.search()` via `asyncio.to_thread()`
  - [x] Response does NOT include `vector_search` — vector search is always active
- [x] Create `src/llm_wiki/api/routers/pages.py` (AC: 10, 11, 12)
  - [x] `GET /v1/pages/{page_id}` — reads page from filesystem; raises `WikiNotFoundError` if missing
  - [x] `GET /v1/pages` — filtered + paginated list from `MetadataIndex`; cursor-based pagination
- [x] Create `src/llm_wiki/api/routers/export.py` (AC: 13, 14)
  - [x] `POST /v1/export` — triggers export job asynchronously
  - [x] `GET /v1/export/{format}` — reads from `wiki_system/exports/`; 404 if not found (raises `ExportNotReadyError`)
- [x] Update `src/llm_wiki/api/models.py` with query/search/page/export models
  - [x] `QueryRequest(query: str, depth: Literal["quick","standard","deep"] = "quick", domain: str | None = None)`
  - [x] `QueryResultItem(page_id, title, confidence, provenance, contradictions)`
  - [x] `QueryResponse(results, timed_out, partial, was_heuristic, job_id=None, status=None)` — no `vector_search` field
  - [x] `SearchResultItem(page_id, title, confidence, score)`
  - [x] `SearchResponse(results)` — no `vector_search` field; vector search is always active
  - [x] `PageResponse(page_id, title, content, frontmatter, domain, kind, confidence)`
  - [x] `PageListResponse(pages, next_cursor, total_hint)`
  - [x] `ExportResponse(format, content, generated_at, page_count)`
- [x] Mount routers in `src/llm_wiki/api/app.py`
- [x] Write tests

## Dev Notes

### Deep Query Job State — In-Memory Only

```python
# In app.state (set in lifespan):
app.state.deep_jobs: dict[str, "DeepQueryJob"] = {}

# DeepQueryJob dataclass:
@dataclass
class DeepQueryJob:
    status: Literal["running", "complete", "failed"]
    created_at: datetime
    result: QueryResponse | None = None

    @property
    def is_expired(self) -> bool:
        return (datetime.utcnow() - self.created_at).total_seconds() > 300  # 5-minute TTL
```

**Critical:** Job state is lost on uvicorn restart. `GET /v1/query/{job_id}` returns 404 after restart. This is expected and documented — client resubmits. Do NOT persist deep query jobs to `state/jobs.json`.

### Deep Query Background Task Pattern

```python
@router.post("/v1/query")
async def query(
    req: QueryRequest,
    request: Request,
    wiki: WikiQuery = Depends(get_wiki),
    profile_id: str | None = Depends(get_profile_id),
) -> QueryResponse:
    if req.depth == "deep":
        job_id = str(uuid.uuid4())
        request.app.state.deep_jobs[job_id] = DeepQueryJob(
            status="running", created_at=datetime.utcnow()
        )
        asyncio.create_task(_run_deep_query(job_id, req, wiki, request.app.state))
        # 202 Accepted: request received, result not yet available — poll GET /v1/query/{job_id}
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=202,
            content=QueryResponse(job_id=job_id, status="queued", results=[]).model_dump(),
        )

    # quick/standard: synchronous
    pages = await asyncio.to_thread(wiki.search, req.query, domain=req.domain, scope_to_profile=profile_id)
    results = [_page_to_result(p) for p in pages[:10 if req.depth == "quick" else 50]]
    return QueryResponse(results=results, timed_out=False, partial=False)

async def _run_deep_query(job_id: str, req: QueryRequest, wiki: WikiQuery, state) -> None:
    try:
        pages = await asyncio.to_thread(wiki.search, req.query)
        result = await run_deep_query(req.query, pages)
        state.deep_jobs[job_id].status = "complete"
        state.deep_jobs[job_id].result = QueryResponse(
            results=[_chunk_to_result(c) for c in result.chunks],
            timed_out=result.timed_out,
            partial=result.partial,
        )
    except Exception as e:
        state.deep_jobs[job_id].status = "failed"
        logger.error("Deep query %s failed: %s", job_id, e)
```

### Job TTL Cleanup

Add a periodic cleanup background task in the FastAPI lifespan:

```python
# In lifespan, after yield setup:
async def _cleanup_deep_jobs():
    while True:
        await asyncio.sleep(60)
        expired = [jid for jid, j in app.state.deep_jobs.items() if j.is_expired]
        for jid in expired:
            del app.state.deep_jobs[jid]

asyncio.create_task(_cleanup_deep_jobs())
```

### WikiQuery.search() Return Shape

**Read `src/llm_wiki/query/search.py` before implementing** to verify exact return type of `search()`. After Story 1.1 and the scope_to_profile work in Story 1.9, `search()` will accept `scope_to_profile: str | None`. For Story 1.7, add the parameter signature now even if domain scoping logic comes in Story 1.9.

### Cursor-Based Pagination

```python
# Simple cursor: base64-encoded offset integer
import base64

def encode_cursor(offset: int) -> str:
    return base64.b64encode(str(offset).encode()).decode()

def decode_cursor(cursor: str) -> int:
    try:
        return int(base64.b64decode(cursor).decode())
    except Exception:
        raise InvalidDepthError("Invalid cursor")  # reuse closest error; or add CursorInvalidError
```

### Export Endpoint Pattern

```python
@router.get("/v1/export/{format}")
async def get_export(format: str, wiki: WikiQuery = Depends(get_wiki)) -> Response:
    exports_dir = wiki.wiki_base / "exports"
    # Format name → filename mapping
    fmt_map = {"llms-txt": "llms.txt", "llms-full-txt": "llms-full.txt", "json-ld": "graph.jsonld"}
    filename = fmt_map.get(format)
    if not filename:
        raise InvalidDepthError(f"Unknown export format: {format}")

    path = exports_dir / filename
    if not path.exists():
        raise ExportNotReadyError(f"Export '{format}' not yet generated. POST /v1/export to trigger.")

    content = await asyncio.to_thread(path.read_text, encoding="utf-8")
    stat = await asyncio.to_thread(path.stat)
    last_modified = datetime.utcfromtimestamp(stat.st_mtime).strftime("%a, %d %b %Y %H:%M:%S GMT")

    return Response(
        content=content,
        media_type="text/plain",
        headers={"Last-Modified": last_modified},
    )
```

### Page Read Pattern

```python
@router.get("/v1/pages/{page_id}", response_model=PageResponse)
async def read_page(page_id: str, wiki: WikiQuery = Depends(get_wiki)) -> PageResponse:
    page = await asyncio.to_thread(wiki.get_page, page_id)
    if page is None:
        raise WikiNotFoundError(f"Page not found: {page_id}")
    return PageResponse(...)
```

**Check if `WikiQuery.get_page()` exists** — read `src/llm_wiki/query/search.py`. If it doesn't, add it.

### Query Log Integration (Story 1.12 Dependency)

The query route must log each query. If Story 1.12 isn't complete yet, add a stub:

```python
# Log query (Story 1.12 provides full implementation)
try:
    await asyncio.to_thread(log_query, wiki.wiki_base / "state/query_log.db", entry)
except Exception:
    pass  # Never block query on log failure
```

### Project Structure — Files to Create/Modify

```
src/llm_wiki/api/
├── app.py          UPDATE — include all 4 new routers
├── models.py       UPDATE — add all query/search/page/export models
└── routers/
    ├── query.py    NEW
    ├── search.py   NEW
    ├── pages.py    NEW
    └── export.py   NEW
```

### Testing

`tests/integration/test_api_integration.py` — add:

```python
def test_quick_query_returns_confidence(client):
    r = client.post("/v1/query", json={"query": "test", "depth": "quick"})
    assert r.status_code == 200
    # Results may be empty on test wiki, but response shape must be correct
    body = r.json()
    assert "results" in body
    assert "vector_search" in body

def test_deep_query_returns_job_id(client):
    r = client.post("/v1/query", json={"query": "test", "depth": "deep"})
    assert r.status_code == 202  # 202 Accepted — async job; poll GET /v1/query/{job_id}
    assert "job_id" in r.json()
    assert r.json()["status"] == "queued"

def test_quick_query_returns_200(client):
    r = client.post("/v1/query", json={"query": "test", "depth": "quick"})
    assert r.status_code == 200  # 200 = synchronous result in body

def test_job_poll_after_ttl_returns_404(client):
    r = client.get("/v1/query/nonexistent-job-id")
    assert r.status_code == 404
    assert r.json()["error_code"] == "WIKI_NOT_FOUND"

def test_export_not_ready_returns_404(client):
    r = client.get("/v1/export/llms-txt")
    assert r.status_code == 404

def test_page_not_found_returns_404(client):
    r = client.get("/v1/pages/no-such-page")
    assert r.status_code == 404
```

### Critical Anti-Patterns to Avoid

- **Never block the event loop** — all I/O in async route functions must use `asyncio.to_thread()`
- **Never store deep query jobs in `state/jobs.json`** — that is for daemon job history only
- **Never add a `vector_search` field to search responses** — vector search is always active; the field is removed
- **QueryTimeoutError is NOT an error** — handle it as a normal `timed_out: true` response branch
- **Never return 200 for deep query submission** — use 202 Accepted; clients use status code to distinguish synchronous results (200) from async jobs (202)
- **`X-Job-TTL: 300` header** must be present on `GET /v1/query/{job_id}` responses while running

### References

- Architecture: "Deep Query Async Strategy" — MCP vs REST patterns
- Architecture: "Deep Query Job State" — in-memory dict; TTL 5 min; not persisted
- Architecture: "Async/Sync Boundary" — `asyncio.to_thread()` rules
- `src/llm_wiki/query/search.py` — read before implementing search endpoint
- Story 1.12: `src/llm_wiki/query/log.py` — query logging dependency

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes

Implemented all 4 routers, updated models, mounted in app.py, added 16 integration tests.
- Added `scope_to_profile` parameter to `WikiQuery.search()` (pre-empt for Story 1.9)
- Deep query uses in-memory job dict with 5-minute TTL; cleaned up by background task
- Query logging stubbed with try/except (Story 1.12 provides `QueryLogStore`)
- No `vector_search` field in response models (vector search always active)
- All 1306 tests pass (1290 existing + 16 new); mypy clean; ruff clean

### File List

- **Created:** `src/llm_wiki/api/routers/query.py`
- **Created:** `src/llm_wiki/api/routers/search.py`
- **Created:** `src/llm_wiki/api/routers/pages.py`
- **Created:** `src/llm_wiki/api/routers/export.py`
- **Modified:** `src/llm_wiki/api/models.py` — replaced stub models with full schema
- **Modified:** `src/llm_wiki/api/app.py` — mounted 4 new routers, added TTL cleanup task
- **Modified:** `src/llm_wiki/query/search.py` — added `scope_to_profile` parameter
- **Created:** `tests/integration/test_story_1_7.py` — 16 integration tests

### Change Log

- Addressed code review findings - 0 items (initial implementation) - Date: 2026-05-18

# Story 1.6: REST Health, Daemon, and Ingest Endpoints

Status: done

## Story

As an operator or integration,
I want REST endpoints to monitor service health, manage the daemon, and submit content for ingestion,
so that I can operate and integrate with the wiki programmatically without a CLI.

**Prerequisites:** Stories 1.4 (FastAPI skeleton) and 1.5 (feature flags) must be complete.

## Acceptance Criteria

1. **Given** `GET /v1/health` **When** called **Then** it responds within 1s (NFR-O2) with daemon liveness, index load status, scheduler state, and `llm_extraction_enabled`. There is no `vector_search_enabled` field — vector search is always on.

2. **Given** `GET /v1/daemon/status` **When** called **Then** it returns job schedule, last-run results, and next-run times for all registered daemon jobs (FR18).

3. **Given** `GET /v1/daemon/jobs` **When** called **Then** it returns job execution history read from `state/jobs.json`.

4. **Given** `POST /v1/daemon/jobs/index-rebuild` **When** called **Then** it triggers an index rebuild asynchronously and returns `{"job_id": "...", "status": "queued"}` (FR19).

5. **Given** `POST /v1/ingest` with a valid source path or content body **When** called **Then** it returns `{"job_id": "...", "status": "queued"}` and the daemon processes the submission (FR2).

6. **Given** `GET /v1/ingest/{job_id}` with a valid job ID **When** called **Then** it returns `{job_id, status, source_path, domain, page_ids, indexed, message}` matching the `IngestStatusResponse` schema (FR5, FR58).

7. **Given** `GET /v1/ingest/{job_id}` with an unknown job ID **When** called **Then** it returns HTTP 404 `WIKI_NOT_FOUND`.

8. **Given** uvicorn restarts after a `POST /v1/ingest` was submitted **When** `GET /v1/ingest/{job_id}` is called after the restart **Then** the job status is still returned correctly — ingest job state is persisted to `state/user_jobs.json`, not held in memory.

8. **Given** `GET /v1/domains` **When** called **Then** it returns the list of configured domains with `page_count` and `last_updated` metadata per domain (FR60).

9. **Given** all REST responses **When** any endpoint is called **Then** the response includes the `X-LLM-Wiki-Version` header (set by middleware in Story 1.4).

## Tasks / Subtasks

- [x] Create `src/llm_wiki/api/routers/health.py` (AC: 1, 2, 3)
  - [x] `GET /v1/health` — reads `WikiQuery` state + daemon job state from `state/jobs.json`
  - [x] `GET /v1/daemon/status` — returns job schedule and last-run from `JobExecutionStore`
  - [x] `GET /v1/daemon/jobs` — returns full history from `state/jobs.json`
  - [x] All responses use `HealthResponse` and `DaemonStatusResponse` from `api/models.py`
- [x] Create `src/llm_wiki/api/routers/ingest.py` (AC: 4, 5, 6, 7)
  - [x] `POST /v1/daemon/jobs/index-rebuild` — queues `IndexRebuildJob` async
  - [x] `POST /v1/ingest` — queues ingest job; returns `{job_id, status: "queued"}`
  - [x] `GET /v1/ingest/{job_id}` — polls ingest status; 404 on unknown
- [x] Create `src/llm_wiki/api/routers/domains.py` (AC: 8)
  - [x] `GET /v1/domains` — returns domain list with page_count and last_updated
- [x] Add ingest job tracking via `UserJobStore` (AC: 5, 6, 7)
  - [x] Create `src/llm_wiki/api/user_jobs.py` — `UserJobStore` class
    - [x] Persists to `wiki_base / "state" / "user_jobs.json"` using atomic write pattern (Story 1.1)
    - [x] `save(job_id: str, status: IngestStatusResponse) -> None`
    - [x] `get(job_id: str) -> IngestStatusResponse | None`
    - [x] `list_all() -> list[IngestStatusResponse]`
    - [x] All writes via `asyncio.to_thread()` in routes
  - [x] Store `UserJobStore` instance on `app.state.user_job_store` in lifespan
  - [x] **Do not** put ingest jobs in `app.state.ingest_jobs` dict — use `UserJobStore` only
  - [x] **Do not** use a TTL or in-memory cleanup — persisted jobs survive restarts; prune via governance retention if needed
- [x] Update `src/llm_wiki/api/models.py` with concrete models (AC: 1, 2, 6, 8)
  - [x] Flesh out `HealthResponse(daemon_running, index_loaded, scheduler_state, llm_extraction_enabled)` — no `vector_search_enabled`, vector search is always on
  - [x] `DaemonStatusResponse(jobs: list[JobStatus])`
  - [x] `JobStatus(job_name, last_run, next_run, last_result, status)`
  - [x] `IngestRequest(source_path: str | None, content: str | None, domain: str | None)`
  - [x] `IngestStatusResponse(job_id, status, source_path, domain, page_ids, indexed, message)`
  - [x] `DomainInfo(name, scope, page_count, last_updated)`
  - [x] `DomainListResponse(domains: list[DomainInfo])`
- [x] Mount routers in `src/llm_wiki/api/app.py` (all three routers)
- [x] Write tests

  **Tests (tests/integration/test_api_integration.py):**
  - AC1: `test_health_returns_200`, `test_health_fields_are_correct_types`, `test_version_header_in_health`
  - AC2: `test_daemon_status_returns_200`
  - AC3: `test_daemon_jobs_returns_200`
  - AC4: `test_index_rebuild_triggers_async`
  - AC5: `test_ingest_post_returns_queued`, `test_ingest_post_then_get`, `test_ingest_persists_to_disk`
  - AC6: `test_ingest_post_then_get`
  - AC7: `test_ingest_get_unknown_returns_404`
  - AC8: `test_domains_returns_list`, `test_domains_version_header`
  - AC9: `test_version_header_in_health`, `test_domains_version_header` (12 total tests, all pass)

## Dev Notes

### Async/IO Constraint

Every route that touches disk, the index, or SQLite **must** use `asyncio.to_thread()`. The event loop must never block.

```python
# CORRECT
@router.get("/v1/health", response_model=HealthResponse)
async def health(wiki: WikiQuery = Depends(get_wiki)) -> HealthResponse:
    status = await asyncio.to_thread(wiki.health)
    jobs_state = await asyncio.to_thread(read_jobs_state, wiki_base / "state/jobs.json")
    return HealthResponse(...)

# WRONG — blocks the event loop
@router.get("/v1/health")
async def health(wiki: WikiQuery = Depends(get_wiki)):
    return wiki.health()  # sync I/O on event loop
```

### JobExecutionStore — Reading job state

`src/llm_wiki/daemon/execution_store.py` contains `JobExecutionStore` with methods to read job state from `state/jobs.json`. Use this class directly rather than reading the file manually.

```python
from llm_wiki.daemon.execution_store import JobExecutionStore

def read_daemon_status(wiki_base: Path) -> list[dict]:
    store = JobExecutionStore(state_dir=wiki_base / "state")
    return store.list_all()   # verify actual method name in execution_store.py
```

**Read `src/llm_wiki/daemon/execution_store.py` before implementing** to get exact method signatures.

### Index Rebuild — Async Trigger Pattern

The `POST /v1/daemon/jobs/index-rebuild` endpoint must trigger the rebuild asynchronously and return immediately. Use `asyncio.create_task()`:

```python
@router.post("/v1/daemon/jobs/index-rebuild")
async def trigger_index_rebuild(
    request: Request,
    wiki: WikiQuery = Depends(get_wiki),
) -> dict:
    job_id = str(uuid.uuid4())

    async def _run():
        from llm_wiki.daemon.jobs.index_rebuild import IndexRebuildJob
        job = IndexRebuildJob(wiki=wiki)
        await asyncio.to_thread(job.execute)

    asyncio.create_task(_run())
    return {"job_id": job_id, "status": "queued"}
```

### Ingest Job Pattern

Ingest jobs are persisted to `state/user_jobs.json` via `UserJobStore` — they survive uvicorn restarts. Deep query jobs remain in-memory only (they are ephemeral 30s synthesis operations; persisting them adds I/O on the hot path with no benefit).

```python
# POST /v1/ingest — write to inbox/new/ and persist job status
@router.post("/v1/ingest")
async def submit_ingest(
    req: IngestRequest,
    request: Request,
    wiki: WikiQuery = Depends(get_wiki),
) -> IngestStatusResponse:
    job_id = str(uuid.uuid4())
    # Write content to inbox/new/ so daemon's InboxScanJob picks it up
    inbox_path = wiki.wiki_base / "inbox" / "new" / f"api-ingest-{job_id}.md"
    await asyncio.to_thread(inbox_path.write_text, req.content or "", encoding="utf-8")
    status = IngestStatusResponse(job_id=job_id, status="queued", ...)
    # Persist — survives uvicorn restarts
    await asyncio.to_thread(request.app.state.user_job_store.save, job_id, status)
    return status

# GET /v1/ingest/{job_id} — read from UserJobStore, not app.state dict
@router.get("/v1/ingest/{job_id}")
async def get_ingest_status(
    job_id: str,
    request: Request,
) -> IngestStatusResponse:
    status = await asyncio.to_thread(request.app.state.user_job_store.get, job_id)
    if status is None:
        raise WikiNotFoundError(f"Ingest job not found: {job_id}")
    return status
```

### UserJobStore — Atomic JSON Persistence

```python
# src/llm_wiki/api/user_jobs.py
import json
import os
import tempfile
from pathlib import Path
from llm_wiki.api.models import IngestStatusResponse

class UserJobStore:
    def __init__(self, state_dir: Path) -> None:
        self._path = state_dir / "user_jobs.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("{}", encoding="utf-8")

    def save(self, job_id: str, status: IngestStatusResponse) -> None:
        data = self._load_raw()
        data[job_id] = status.model_dump()
        self._write_atomic(data)

    def get(self, job_id: str) -> IngestStatusResponse | None:
        data = self._load_raw()
        raw = data.get(job_id)
        return IngestStatusResponse(**raw) if raw else None

    def list_all(self) -> list[IngestStatusResponse]:
        return [IngestStatusResponse(**v) for v in self._load_raw().values()]

    def _load_raw(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _write_atomic(self, data: dict) -> None:
        with tempfile.NamedTemporaryFile(
            "w", dir=self._path.parent, delete=False, suffix=".tmp", encoding="utf-8"
        ) as f:
            json.dump(data, f, indent=2, default=str)
            tmp = f.name
        os.replace(tmp, self._path)
```

### Domain Page Count — Reading from MetadataIndex

```python
# GET /v1/domains — page_count from MetadataIndex, last_updated from filesystem
async def list_domains(wiki: WikiQuery = Depends(get_wiki)) -> DomainListResponse:
    domains_config = wiki.config.domains.domains
    result = []
    for domain in domains_config:
        page_count = await asyncio.to_thread(
            lambda d=domain.id: count_pages_in_domain(wiki.wiki_base, d)
        )
        result.append(DomainInfo(name=domain.id, scope=getattr(domain, 'scope', 'shared'), page_count=page_count))
    return DomainListResponse(domains=result)
```

### Router Mounting in app.py

```python
# src/llm_wiki/api/app.py — add after other setup
from llm_wiki.api.routers import health, ingest, domains

app.include_router(health.router)
app.include_router(ingest.router)
app.include_router(domains.router)
```

All routers use `APIRouter(prefix="/v1", tags=[...])` — never put `/v1` in individual route paths.

### Project Structure — Files to Create/Modify

```
src/llm_wiki/api/
├── app.py              UPDATE — include routers; init UserJobStore on app.state
├── models.py           UPDATE — flesh out HealthResponse, IngestStatusResponse, etc.
├── user_jobs.py        NEW — UserJobStore (persists to state/user_jobs.json)
└── routers/
    ├── health.py       NEW
    ├── ingest.py       NEW
    └── domains.py      NEW
```

### Testing

`tests/integration/test_api_integration.py` — add with `TestClient`:

```python
def test_health_returns_200(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert "daemon_running" in body
    assert "llm_extraction_enabled" in body
    assert "vector_search_enabled" not in body  # vector search is always on, not a flag

def test_ingest_unknown_job_id_returns_404(client):
    r = client.get("/v1/ingest/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error_code"] == "WIKI_NOT_FOUND"

def test_domains_returns_list(client):
    r = client.get("/v1/domains")
    assert r.status_code == 200
    assert "domains" in r.json()
```

Create a `client` fixture in `conftest.py`:

```python
@pytest.fixture
def client(wiki_root):
    from fastapi.testclient import TestClient
    from llm_wiki.api.app import app
    # Point app at test wiki_root
    import os
    os.environ["WIKI_ROOT"] = str(wiki_root)
    with TestClient(app) as c:
        yield c
```

### Critical Anti-Patterns to Avoid

- **Never block the event loop** — all I/O in route functions must use `asyncio.to_thread()`
- **Never put `/v1` in individual route paths** — use `APIRouter(prefix="/v1")`
- **Never access `state/jobs.json` directly** — use `JobExecutionStore`
- **Never define error responses inline** — use `wiki_error_to_http()` from `errors.py`
- **Never store ingest jobs in `app.state` dict** — use `UserJobStore` which persists to `state/user_jobs.json`; in-memory ingest state is lost on restart
- **Never persist deep query jobs** — they are ephemeral 30s operations; use in-memory dict with TTL as defined in Story 1.7

### References

- Architecture: "FastAPI Route Structure" — router file pattern
- Architecture: "Async/Sync Boundary" — `asyncio.to_thread()` rules
- `src/llm_wiki/daemon/execution_store.py` — read before implementing health/status routes
- Story 1.4: `api/app.py` lifespan, `api/errors.py` ERROR_MAP, `api/models.py`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log

- **Router import shadowing**: Inside `create_app()`, the local function `def health()` shadowed the imported `health` router module. Fixed by keeping router imports lazy (inside `create_app()`) and renaming the legacy route to `_legacy_health()`.
- **Test client lifespan**: `TestClient(app)` with a `lifespan` parameter runs the lifespan when used as a context manager (`with TestClient(app):`). Tests must create a fresh `create_app()` per fixture to avoid shared state across tests.

### Completion Notes

Implemented all 9 acceptance criteria for Story 1.6 (REST Health, Daemon, and Ingest Endpoints):

1. **Models** — Replaced stub models in `api/models.py` with concrete Pydantic models: `HealthResponse`, `DaemonStatusResponse`, `JobStatus`, `IngestRequest`, `IngestStatusResponse`, `DomainInfo`, `DomainListResponse`. Removed the old `running`/`config_dir` fields from HealthResponse per spec.

2. **UserJobStore** — Created `api/user_jobs.py` with atomic JSON persistence to `state/user_jobs.json`. Supports `save()`, `get()`, `list_all()`. Used in routes via `asyncio.to_thread()`.

3. **Health router** — `GET /v1/health` returns daemon liveness, index loaded status, scheduler state, and LLM extraction flag. No `vector_search_enabled` field. `GET /v1/daemon/status` and `GET /v1/daemon/jobs` read from `JobExecutionStore`.

4. **Ingest router** — `POST /v1/ingest` writes content to `inbox/new/`, persists job status, returns `{"job_id": "...", "status": "queued"}`. `GET /v1/ingest/{job_id}` returns status or 404 with `WIKI_NOT_FOUND`. `POST /v1/daemon/jobs/index-rebuild` fires async task.

5. **Domains router** — `GET /v1/domains` reads configured domains from config YAML, looks up page counts from `MetadataIndex.by_domain`, and computes last_updated from metadata timestamps.

6. **App wiring** — Routers mounted in `app.py`. `UserJobStore` initialized on `app.state.user_job_store` during lifespan.

All 12 integration tests pass. Full test suite: 1287 passed (3 pre-existing bootstrap failures).

### Dev Agent Record

### File List

**New files:**
- `src/llm_wiki/api/user_jobs.py` — UserJobStore for persistent ingest job tracking
- `src/llm_wiki/api/routers/health.py` — health/daemon status endpoints
- `src/llm_wiki/api/routers/ingest.py` — ingest/index-rebuild endpoints
- `src/llm_wiki/api/routers/domains.py` — domain listing endpoint
- `tests/integration/test_api_integration.py` — 12 integration tests for all endpoints

**Modified files:**
- `src/llm_wiki/api/models.py` — fleshed out stub models (HealthResponse, DaemonStatusResponse, IngestRequest, IngestStatusResponse, DomainInfo, DomainListResponse, JobStatus)
- `src/llm_wiki/api/app.py` — mounted routers, initialized UserJobStore in lifespan

# Story 1.6: REST Health, Daemon, and Ingest Endpoints

Status: ready-for-dev

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

- [ ] Create `src/llm_wiki/api/routers/health.py` (AC: 1, 2, 3)
  - [ ] `GET /v1/health` — reads `WikiQuery` state + daemon job state from `state/jobs.json`
  - [ ] `GET /v1/daemon/status` — returns job schedule and last-run from `JobExecutionStore`
  - [ ] `GET /v1/daemon/jobs` — returns full history from `state/jobs.json`
  - [ ] All responses use `HealthResponse` and `DaemonStatusResponse` from `api/models.py`
- [ ] Create `src/llm_wiki/api/routers/ingest.py` (AC: 4, 5, 6, 7)
  - [ ] `POST /v1/daemon/jobs/index-rebuild` — queues `IndexRebuildJob` async
  - [ ] `POST /v1/ingest` — queues ingest job; returns `{job_id, status: "queued"}`
  - [ ] `GET /v1/ingest/{job_id}` — polls ingest status; 404 on unknown
- [ ] Create `src/llm_wiki/api/routers/domains.py` (AC: 8)
  - [ ] `GET /v1/domains` — returns domain list with page_count and last_updated
- [ ] Add ingest job tracking via `UserJobStore` (AC: 5, 6, 7)
  - [ ] Create `src/llm_wiki/api/user_jobs.py` — `UserJobStore` class
    - [ ] Persists to `wiki_base / "state" / "user_jobs.json"` using atomic write pattern (Story 1.1)
    - [ ] `save(job_id: str, status: IngestStatusResponse) -> None`
    - [ ] `get(job_id: str) -> IngestStatusResponse | None`
    - [ ] `list_all() -> list[IngestStatusResponse]`
    - [ ] All writes via `asyncio.to_thread()` in routes
  - [ ] Store `UserJobStore` instance on `app.state.user_job_store` in lifespan
  - [ ] **Do not** put ingest jobs in `app.state.ingest_jobs` dict — use `UserJobStore` only
  - [ ] **Do not** use a TTL or in-memory cleanup — persisted jobs survive restarts; prune via governance retention if needed
- [ ] Update `src/llm_wiki/api/models.py` with concrete models (AC: 1, 2, 6, 8)
  - [ ] Flesh out `HealthResponse(daemon_running, index_loaded, scheduler_state, llm_extraction_enabled)` — no `vector_search_enabled`, vector search is always on
  - [ ] `DaemonStatusResponse(jobs: list[JobStatus])`
  - [ ] `JobStatus(job_name, last_run, next_run, last_result, status)`
  - [ ] `IngestRequest(source_path: str | None, content: str | None, domain: str | None)`
  - [ ] `IngestStatusResponse(job_id, status, source_path, domain, page_ids, indexed, message)`
  - [ ] `DomainInfo(name, scope, page_count, last_updated)`
  - [ ] `DomainListResponse(domains: list[DomainInfo])`
- [ ] Mount routers in `src/llm_wiki/api/app.py` (all three routers)
- [ ] Write tests

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

### Debug Log References

### Completion Notes List

### File List

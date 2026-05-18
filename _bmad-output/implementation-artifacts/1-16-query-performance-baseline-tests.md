# Story 1.16: Query Performance Baseline Tests

Status: ready-for-dev

## Story

As a developer,
I want automated performance tests covering all three query depths,
So that regressions in query latency are caught before a sprint is declared done.

**Prerequisites:** Stories 1.6 and 1.7 must be complete — the REST API must exist before performance tests can drive it.

## Acceptance Criteria

1. **Given** a seeded test wiki of 100 pages across 3 domains **When** `POST /v1/query` is called with `depth: "quick"` **Then** the response arrives in ≤ 200ms (NFR-P1); test asserts on `time.perf_counter()` delta.

2. **Given** the same seeded wiki **When** `POST /v1/query` is called with `depth: "standard"` **Then** the response arrives in ≤ 2s (NFR-P2).

3. **Given** the same seeded wiki with `llm_extraction: false` **When** `POST /v1/query` is called with `depth: "deep"` and the job completes **Then** the total time from submission to result (including poll) is ≤ 30s (NFR-P3).

4. **Given** the performance tests **When** run in CI **Then** they are tagged `@pytest.mark.performance` and excluded from the default `pytest` run; included via `pytest -m performance`.

## Tasks / Subtasks

- [ ] Create performance test fixture: 100-page seeded wiki (AC: 1, 2, 3)
  - [ ] `tests/performance/conftest.py` — `seeded_wiki_app` fixture
  - [ ] Generate 100 markdown pages across 3 domains with realistic content
  - [ ] Wire up FastAPI `TestClient` for quick/standard tests and `httpx.AsyncClient` for the deep query test
  - [ ] Set `llm_extraction: false` in wiki config (tests must not require an LLM)
- [ ] Create `tests/performance/test_query_latency.py` (AC: 1, 2, 3, 4)
  - [ ] `test_quick_query_under_200ms` — `@pytest.mark.performance`
  - [ ] `test_standard_query_under_2s` — `@pytest.mark.performance`
  - [ ] `test_deep_query_under_30s` — `@pytest.mark.performance @pytest.mark.anyio`; uses `AsyncClient` + `anyio.sleep()` so background tasks actually run
- [ ] Register `performance` mark in `pytest.ini` / `pyproject.toml` (AC: 4)
  - [ ] `filterwarnings` and marker description for `performance`
  - [ ] Verify default `pytest` run excludes `performance` tests
- [ ] Document how to run performance tests in `README` or `CONTRIBUTING` (AC: 4)

## Dev Notes

### Test File Structure

```
tests/
├── performance/
│   ├── __init__.py
│   ├── conftest.py         — seeded_wiki_app fixture
│   └── test_query_latency.py
└── conftest.py             — register performance mark (or in pyproject.toml)
```

### Seeded Wiki Fixture

Generate 100 realistic pages programmatically — do not commit 100 markdown files:

```python
# tests/performance/conftest.py
import pytest
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from llm_wiki.initializer import WikiInitializer
from llm_wiki.api.app import create_app

def _generate_pages(wiki_system: Path, count: int = 100) -> None:
    """Write synthetic pages to 3 domains."""
    domains = ["household", "tech", "personal"]
    for i in range(count):
        domain = domains[i % 3]
        domain_dir = wiki_system / "domains" / domain / "pages"
        domain_dir.mkdir(parents=True, exist_ok=True)
        page = domain_dir / f"page-{i:04d}.md"
        page.write_text(
            f"---\n"
            f"id: page-{i:04d}\n"
            f"title: Test Page {i}\n"
            f"domain: {domain}\n"
            f"updated_at: 2026-05-17T00:00:00Z\n"
            f"confidence: 0.8\n"
            f"---\n\n"
            f"# Test Page {i}\n\n"
            f"This page contains content about topic {i % 20}. "
            f"It describes various aspects of the subject in domain {domain}. "
            f"The content is generated for performance testing purposes only.\n"
        )

@pytest.fixture(scope="session")
def seeded_wiki_path(tmp_path_factory):
    wiki_root = tmp_path_factory.mktemp("perf_wiki")
    WikiInitializer.initialize(wiki_root)
    _generate_pages(wiki_root / "wiki_system")
    return wiki_root

@pytest.fixture(scope="session")
def seeded_wiki_client(seeded_wiki_path):
    """Sync TestClient for quick/standard latency tests."""
    app = create_app(wiki_root=seeded_wiki_path, llm_extraction=False)
    with TestClient(app) as client:
        yield client

@pytest.fixture(scope="session")
def seeded_wiki_app(seeded_wiki_path):
    """Bare app instance for async deep query test."""
    return create_app(wiki_root=seeded_wiki_path, llm_extraction=False)
```

`scope="session"` is critical — building 100 pages and rebuilding the index once per test session, not once per test. Without session scope, the 200ms quick query budget will be blown by fixture setup.

**Test dependency**: `anyio` must be in `[project.optional-dependencies.test]`. Add `pytest-anyio` (or `anyio[trio]`) to `pyproject.toml` test extras and set `anyio_mode = "asyncio"` in `[tool.pytest.ini_options]`.

### Performance Test Pattern

```python
# tests/performance/test_query_latency.py
import time
import pytest

pytestmark = pytest.mark.performance


def test_quick_query_under_200ms(seeded_wiki_client):
    start = time.perf_counter()
    response = seeded_wiki_client.post(
        "/v1/query",
        json={"query": "topic 5", "depth": "quick"},
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert response.status_code == 200
    assert elapsed_ms < 200, f"quick query took {elapsed_ms:.1f}ms (budget: 200ms)"


def test_standard_query_under_2s(seeded_wiki_client):
    start = time.perf_counter()
    response = seeded_wiki_client.post(
        "/v1/query",
        json={"query": "topic 3", "depth": "standard"},
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert response.status_code == 200
    assert elapsed_ms < 2000, f"standard query took {elapsed_ms:.1f}ms (budget: 2000ms)"


@pytest.mark.anyio
async def test_deep_query_under_30s(seeded_wiki_app):
    """Deep query: submit then poll until done. Total must be ≤ 30s.

    Must use AsyncClient + anyio.sleep() — TestClient runs a separate thread
    that starves asyncio.create_task() background jobs; they never complete.
    AsyncClient shares the event loop with the app so background tasks run.
    """
    import anyio
    from httpx import AsyncClient, ASGITransport

    start = time.perf_counter()

    async with AsyncClient(
        transport=ASGITransport(app=seeded_wiki_app), base_url="http://test"
    ) as client:
        # Submit
        response = await client.post(
            "/v1/query",
            json={"query": "topic 7", "depth": "deep"},
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        # Poll — yield to the event loop so background task can run
        while True:
            await anyio.sleep(0.5)  # non-blocking; lets asyncio.create_task() progress
            poll = await client.get(f"/v1/query/{job_id}")
            assert poll.status_code == 200
            data = poll.json()
            if data["status"] in ("done", "error", "timed_out"):
                break
            elapsed = time.perf_counter() - start
            assert elapsed < 30, f"deep query polling exceeded 30s budget"

    total_ms = (time.perf_counter() - start) * 1000
    assert total_ms < 30_000, f"deep query took {total_ms:.0f}ms (budget: 30000ms)"
    assert data["status"] in ("done", "timed_out")  # timed_out is valid, not a failure
```

### pytest.ini / pyproject.toml Registration

```toml
# pyproject.toml — add to [tool.pytest.ini_options]
markers = [
    "performance: marks tests as performance tests (deselect with '-m not performance')",
    "integration: marks tests requiring external services (Docker, etc.)",
]
```

Default run excludes performance:

```toml
addopts = "-m 'not performance and not integration'"
```

This means `pytest` (no args) skips both `performance` and `integration` tests. CI runs them separately:

```yaml
# .github/workflows/ci.yml — extend the scaffold created by Story 1.11
# Add these steps inside the placeholder block:
# "── Performance tests (Story 1.16 adds steps here) ──"
- name: Run performance tests
  run: uv run pytest -m performance
```

**Important:** Story 1.11 owns the creation of `.github/workflows/ci.yml`. If that story is not yet merged, do not create a new file — add a note to the PR that the performance step must land after 1.11's scaffold exists.

### llm_extraction: false Requirement

Deep queries that trigger the synthesis engine must NOT require an LLM during performance tests. The synthesis engine must fall back to heuristic summarization when `llm_extraction: false`:

- Quick depth: full-text search only — no LLM
- Standard depth: full-text + metadata ranking — no LLM
- Deep depth: synthesis engine with heuristic fallback — confirm Story 1.5's heuristic fallback is working

If `synthesis/engine.py` still calls an LLM even when `llm_extraction: false`, the deep query test will hang. Verify the feature flag is properly checked in the synthesis engine.

### Index Rebuild Before Tests

The seeded wiki fixture must trigger an index rebuild after writing pages. Otherwise queries find nothing and the latency measurement is meaningless:

```python
# In seeded_wiki_path fixture, after _generate_pages():
from llm_wiki.daemon.jobs.index_rebuild import IndexRebuildJob
job = IndexRebuildJob(wiki_base=wiki_root / "wiki_system")
job.execute()
```

### Project Structure — Files to Create/Modify

```
tests/
├── performance/
│   ├── __init__.py            NEW
│   ├── conftest.py            NEW — seeded_wiki_app fixture
│   └── test_query_latency.py  NEW — performance tests
└── conftest.py                UPDATE — register performance/integration marks (if not in pyproject.toml)

pyproject.toml                 UPDATE — add markers, addopts to exclude by default
```

### Critical Anti-Patterns to Avoid

- **Never use `pytest.fixture(scope="function")` for the seeded wiki** — rebuilding 100 pages per test will blow all timing budgets; use `scope="session"`
- **Never use `TestClient` for the deep query test** — `TestClient` runs the app in a separate thread; `asyncio.create_task()` background jobs never get CPU time and the poll loop hangs; use `httpx.AsyncClient` with `ASGITransport` instead
- **Never require a real LLM** in performance tests — set `llm_extraction: false`; synthesis must have heuristic fallback
- **Never fail on `timed_out: true`** in deep query test — a timed-out deep query that returns partial results within 30s satisfies NFR-P3
- **Never mix performance and unit tests** in the same run — mark and exclude correctly

### References

- Architecture: "Query Depth Strategy" — quick ≤200ms, standard ≤2s, deep ≤30s
- Architecture: "Feature Flag System" — `llm_extraction` feature flag
- Story 1.7: Deep query REST pattern (job_id + poll)
- Story 1.5: Heuristic fallback when LLM disabled
- NFR-P1, NFR-P2, NFR-P3

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List

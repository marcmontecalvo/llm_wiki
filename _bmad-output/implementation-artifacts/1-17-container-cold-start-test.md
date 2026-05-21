# Story 1.17: Container Cold Start Test

Status: done

## Story

As a developer,
I want an automated test that verifies the full Docker stack starts within the NFR budget,
So that Docker or supervisord configuration regressions are caught before release.

**Prerequisites:** Story 1.3 (Docker container and process management) must be complete — `Dockerfile`, `docker-compose.yml`, and `supervisord.conf` must exist.

## Acceptance Criteria

1. **Given** `docker-compose up --build` against a fresh empty volume **When** the container starts **Then** `GET /v1/health` returns HTTP 200 within 30s of container start (NFR-O1).

2. **Given** the cold start test **When** run **Then** it is tagged `@pytest.mark.integration` and requires Docker; skipped automatically when Docker is not present.

3. **Given** the health response **When** examined **Then** it includes `daemon_running`, `index_loaded`, and `llm_extraction_enabled` fields. There is no `vector_search_enabled` — vector search is always active.

## Tasks / Subtasks

- [x] Create `tests/integration/test_cold_start.py` (AC: 1, 2, 3)
  - [x] `@pytest.mark.integration` on all tests
  - [x] Skip fixture: detect Docker availability via `docker info`; skip if unavailable
  - [x] Start container: `docker-compose up --build -d` against fresh empty temp volume
  - [x] Poll `GET /v1/health` with 1s interval, timeout at 30s
  - [x] Assert HTTP 200 received within budget
  - [x] Assert response body contains required fields (AC: 3)
  - [x] Teardown: `docker-compose down -v` — remove container and volume
- [x] Verify `GET /v1/health` response schema includes all required fields (AC: 3)
  - [x] `daemon_running: bool`
  - [x] `index_loaded: bool`
  - [x] `llm_extraction_enabled: bool`
  - [x] `vector_search_enabled: bool` — absent per AC:3; assertion `not in data` confirms this
  - [x] If any field is missing, update Story 1.6's health endpoint implementation — not needed, all fields present
- [x] Register `integration` mark in `pyproject.toml` (AC: 2)
  - [x] Already added in Story 1.16 if done first; verify `integration` mark is registered — confirmed present
  - [x] Ensure `addopts = "-m 'not performance and not integration'"` excludes integration tests by default — confirmed present

## Dev Notes

### Docker Availability Skip Pattern

```python
# tests/integration/test_cold_start.py
import subprocess
import pytest
import time
import requests

pytestmark = pytest.mark.integration


def _docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


docker_required = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker is not available — skipping container integration tests",
)
```

### Cold Start Test

```python
@docker_required
def test_container_cold_start_within_30s(tmp_path):
    """Container must serve /v1/health within 30s of cold start."""
    wiki_volume = tmp_path / "wiki"
    wiki_volume.mkdir()

    compose_file = Path(__file__).parent.parent.parent / "docker-compose.yml"
    assert compose_file.exists(), f"docker-compose.yml not found at {compose_file}"

    env = {
        **os.environ,
        "WIKI_VOLUME": str(wiki_volume),
    }

    # Start container
    up_result = subprocess.run(
        ["docker-compose", "-f", str(compose_file), "up", "--build", "-d"],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,  # build can be slow in CI
    )
    assert up_result.returncode == 0, f"docker-compose up failed:\n{up_result.stderr}"

    try:
        # Poll health endpoint — port comes from WIKI_PORT env var (default 3050)
        host_port = _get_mapped_port(env)
        health_url = f"http://localhost:{host_port}/v1/health"

        deadline = time.time() + 30
        response = None
        while time.time() < deadline:
            try:
                response = requests.get(health_url, timeout=2)
                if response.status_code == 200:
                    break
            except requests.ConnectionError:
                pass
            time.sleep(1)

        assert response is not None and response.status_code == 200, (
            f"GET /v1/health did not return 200 within 30s"
        )

        # Verify response schema (AC: 3)
        data = response.json()
        assert "daemon_running" in data, "Missing daemon_running field"
        assert "index_loaded" in data, "Missing index_loaded field"
        assert "llm_extraction_enabled" in data, "Missing llm_extraction_enabled field"
        assert "vector_search_enabled" not in data, "vector_search_enabled must not be present — vector search is always on"
        assert isinstance(data["daemon_running"], bool)
        assert isinstance(data["index_loaded"], bool)
        assert isinstance(data["llm_extraction_enabled"], bool)

    finally:
        # Always clean up
        subprocess.run(
            ["docker-compose", "-f", str(compose_file), "down", "-v"],
            env=env,
            capture_output=True,
            timeout=30,
        )
```

### Port Detection Helper

Read `WIKI_PORT` from the environment rather than hardcoding any port number — this stays correct if the default port changes and matches the env var already used throughout the architecture.

```python
def _get_mapped_port(env: dict) -> int:
    """Get the host port from WIKI_PORT env var (default 3050)."""
    return int(env.get("WIKI_PORT", 3050))
```

### docker-compose.yml — Volume Mount Pattern

The test uses a temp directory as the wiki volume. The `docker-compose.yml` should support an env-var override for the volume path:

```yaml
# docker-compose.yml
services:
  llm-wiki:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ${WIKI_VOLUME:-./wiki_data}:/wiki
    environment:
      - WIKI_CONFIG_DIR=/wiki/config
```

If `docker-compose.yml` hardcodes the volume path, the test needs to either:
1. Use a named volume instead of a bind mount, OR
2. Write a temp `docker-compose.override.yml` with the volume substitution

Prefer option 1 (env var substitution) — it's already covered in Story 1.3 dev notes.

### Health Endpoint Required Fields (Story 1.6 Verification)

The `GET /v1/health` response must include these four fields. Check `src/llm_wiki/api/routers/health.py` (created in Story 1.6). If the fields are missing, add them:

```python
# src/llm_wiki/api/routers/health.py
class HealthResponse(BaseModel):
    status: str
    daemon_running: bool
    index_loaded: bool
    llm_extraction_enabled: bool
    version: str | None = None
    # No vector_search_enabled — FAISS is a required dependency, always active
```

**How to populate these fields**:
- `daemon_running`: check if daemon process is alive (pid file or socket check)
- `index_loaded`: check if `WikiQuery` has loaded indexes (`wiki.index_loaded` or similar flag)
- `llm_extraction_enabled`: from `wiki.config.features.llm_extraction`

### CI Integration

```yaml
# .github/workflows/ci.yml — extend the scaffold created by Story 1.11
# Add this step inside the placeholder block:
# "── Integration tests (Story 1.17 adds steps here) ──"
- name: Run integration tests
  if: github.event_name == 'push' && github.ref == 'refs/heads/main'
  run: uv run pytest -m integration --timeout=120
```

Running integration tests only on main pushes (not PRs) avoids slow Docker builds for every PR while still catching regressions before release.

**Important:** Story 1.11 owns the creation of `.github/workflows/ci.yml`. If that story is not yet merged, do not create a new file — add a note to the PR that the integration step must land after 1.11's scaffold exists.

### Project Structure — Files to Create/Modify

```
tests/
└── integration/
    ├── __init__.py            NEW
    └── test_cold_start.py     NEW — Docker cold start test

pyproject.toml                 UPDATE — register integration mark (if not done in Story 1.16)

src/llm_wiki/api/routers/
└── health.py                  VERIFY — all 4 required fields in response
```

### Critical Anti-Patterns to Avoid

- **Never fail the test if Docker is not available** — use `pytest.mark.skipif` to skip gracefully; CI machines without Docker should not fail the test suite
- **Never hardcode a port number** — read `WIKI_PORT` from the environment; the service default is 3050, not 8000
- **Always run `docker-compose down -v` in a `finally` block** — a crashed test must not leave containers running and consuming resources
- **Never set the 30s deadline before `docker-compose up` returns** — start the clock after `up` completes (the container starts, not the build)
- **Never skip the field assertions** — NFR-O1 is about health check responding; AC 3 is about the health response being useful

### References

- Architecture: "Container and Process Architecture" — supervisord, nodaemon=true, startup sequence
- Architecture: "Startup Init Sequence" — _maybe_init_wiki_root() ordering, health endpoint
- Story 1.3: Dockerfile, docker-compose.yml, supervisord.conf
- Story 1.6: `GET /v1/health` endpoint implementation
- NFR-O1: Container health within 30s of start

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None.

### Completion Notes List

- Created `tests/integration/test_cold_start.py` with `@pytest.mark.integration`, Docker skip guard, `docker-compose up --build -d` cold start, 1s-poll / 30s-timeout health check, AC:3 field assertions, and `docker-compose down -v` teardown in `finally`.
- Updated `docker-compose.yml` to use `${WIKI_VOLUME:-./wiki_data}:/wiki` so tests can inject a fresh temp volume without affecting production defaults.
- Added "Run integration tests" step to `.github/workflows/ci.yml` (main-push only, `uv run pytest -m integration --timeout=120`). "Run performance tests" step already existed from Story 1.16.
- Review fix: cold-start test now uses a unique `COMPOSE_PROJECT_NAME`, a free host/container `WIKI_PORT`, and monotonic timing so it does not collide with or tear down a developer's normal compose stack.
- Review fix: `docker-compose.yml` now applies `${WIKI_PORT:-3050}` consistently to the host mapping, container port, and service environment.
- Review fix: CI integration-test timeout now uses a Python subprocess timeout instead of the unavailable `pytest --timeout` option.
- `pyproject.toml`: `integration` mark and `addopts` exclusion were already in place from Story 1.16 — no changes needed.
- `HealthResponse` model already had all three required fields (`daemon_running`, `index_loaded`, `llm_extraction_enabled`); no `vector_search_enabled` — correct per AC:3.
- Full test suite: 1428 passed, 0 failed (excluding cold start which requires Docker).

### File List

- tests/integration/test_cold_start.py (NEW)
- docker-compose.yml (MODIFIED — WIKI_VOLUME env var and consistent WIKI_PORT override)
- .github/workflows/ci.yml (MODIFIED — integration test CI step with portable 120s timeout)

### Senior Developer Review (AI)

Reviewer: Codex on 2026-05-21

Outcome: Approved after automatic fixes.

Findings fixed:

- HIGH: `.github/workflows/ci.yml` used `pytest --timeout=120`, but `pytest-timeout` is not declared and local collection rejected the option. Replaced it with a Python subprocess timeout around `python -m pytest -m integration`.
- HIGH: `docker-compose.yml` mapped `3050:${WIKI_PORT:-3050}` while setting container `WIKI_PORT` to `"3050"`, so any `WIKI_PORT` override broke the health endpoint mapping. Updated the mapping and service environment to use `${WIKI_PORT:-3050}` consistently.
- MEDIUM: `tests/integration/test_cold_start.py` used the default compose project and port, so a review run could collide with or tear down a developer's normal `llm-wiki` compose stack. The test now sets a unique `COMPOSE_PROJECT_NAME` and allocates a free port.
- LOW: The health polling budget used wall-clock time. Switched to `time.monotonic()` for timeout accounting.

Validation:

- `UV_CACHE_DIR=.uv-cache uv run pytest tests/integration/test_cold_start.py -m integration -q` -> skipped because Docker is unavailable in this environment.
- `UV_CACHE_DIR=.uv-cache uv run ruff check tests/integration/test_cold_start.py` -> passed.
- `UV_CACHE_DIR=.uv-cache uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); yaml.safe_load(open('docker-compose.yml')); print('yaml ok')"` -> passed.
- Portable CI timeout snippet verified locally against `tests/integration/test_cold_start.py`.

## Change Log

- 2026-05-21: Implemented Story 1.17 — Docker cold start integration test, WIKI_VOLUME env override in docker-compose.yml, CI integration step (claude-sonnet-4-6)
- 2026-05-21: Review fixes applied — isolated compose project/port in cold-start test, consistent WIKI_PORT compose mapping, portable CI timeout wrapper; story marked done (Codex)

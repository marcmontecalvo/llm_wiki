# Story 1.17: Container Cold Start Test

Status: ready-for-dev

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

- [ ] Create `tests/integration/test_cold_start.py` (AC: 1, 2, 3)
  - [ ] `@pytest.mark.integration` on all tests
  - [ ] Skip fixture: detect Docker availability via `docker info`; skip if unavailable
  - [ ] Start container: `docker-compose up --build -d` against fresh empty temp volume
  - [ ] Poll `GET /v1/health` with 1s interval, timeout at 30s
  - [ ] Assert HTTP 200 received within budget
  - [ ] Assert response body contains required fields (AC: 3)
  - [ ] Teardown: `docker-compose down -v` — remove container and volume
- [ ] Verify `GET /v1/health` response schema includes all required fields (AC: 3)
  - [ ] `daemon_running: bool`
  - [ ] `index_loaded: bool`
  - [ ] `llm_extraction_enabled: bool`
  - [ ] `vector_search_enabled: bool`
  - [ ] If any field is missing, update Story 1.6's health endpoint implementation
- [ ] Register `integration` mark in `pyproject.toml` (AC: 2)
  - [ ] Already added in Story 1.16 if done first; verify `integration` mark is registered
  - [ ] Ensure `addopts = "-m 'not performance and not integration'"` excludes integration tests by default

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

### Completion Notes List

### File List

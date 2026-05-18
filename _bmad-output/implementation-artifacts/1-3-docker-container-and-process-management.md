# Story 1.3: Docker Container and Process Management

Status: review

## Story

As a developer,
I want to start the entire LLM Wiki stack with a single command,
so that I can run a fully-operational wiki service without any Python environment setup or manual process management.

**Prerequisite:** Stories 1.1 and 1.2 must be complete before this story. Building the container before the P0 data integrity fixes are in place exposes a broken daemon.

## Acceptance Criteria

1. **Given** the repo with a pre-built Docker image **When** `docker-compose up` is run **Then** both uvicorn and WikiDaemon are running and healthy within 30s (NFR-O1).

2. **Given** the container starts **When** supervisord initializes **Then** process 1 is uvicorn serving `0.0.0.0:$WIKI_PORT` (REST + MCP Streamable HTTP) and process 2 is WikiDaemon.

3. **Given** WikiDaemon crashes at runtime **When** supervisord detects the exit **Then** it restarts the daemon automatically (`autorestart=true`, `startretries=5`).

4. **Given** the supervisord config for the daemon process **When** audited **Then** `stopwaitsecs=30` — never lower, because the daemon may be mid-write when a stop signal arrives.

5. **Given** uvicorn crashes at runtime **When** supervisord detects the exit **Then** it restarts uvicorn automatically (`autorestart=true`, `startretries=3`).

6. **Given** the container **When** running **Then** all processes run as uid 1000 (`llmwiki` user) — not root.

7. **Given** `docker-compose.yml` **When** defined **Then** it mounts `./wiki_data:/wiki` (read-write) and `./config:/config` (read-only), and sets `WIKI_ROOT=/wiki`.

8. **Given** `daemon.yaml` or `domains.yaml` is modified on the host **When** the container is restarted **Then** the new config takes effect without rebuilding the image (NFR-O3).

9. **Given** `./wiki_data` does not exist on the host **When** `docker-compose up` is run **Then** docker creates the directory and the container auto-initializes the wiki structure inside it.

10. **Given** WikiDaemon crashes and supervisord is restarting it **When** `GET /v1/health` is called during the restart window **Then** the response body contains `"daemon_running": false` and the Docker HEALTHCHECK reports the container as unhealthy — uvicorn being up alone is not sufficient for a healthy status.

## Tasks / Subtasks

- [x] Create `Dockerfile` (multi-stage build) (AC: 2, 6)
  - [x] Stage 1 `builder`: install uv, `uv sync` (including optional extras)
  - [x] Stage 2 `runtime`: copy virtualenv from builder; install supervisord; add uid 1000 `llmwiki` user
  - [x] Set `WIKI_ROOT=/wiki` and `WIKI_PORT=3050` in Dockerfile
  - [x] Expose `$WIKI_PORT`
  - [x] Entrypoint: `supervisord -c /app/supervisord.conf`
  - [x] HEALTHCHECK: checks `/v1/health`, fails if `daemon_running` is false
- [x] Create `supervisord.conf` (AC: 2, 3, 4, 5)
  - [x] `[supervisord]` section: `nodaemon=true` (critical — without this container exits immediately)
  - [x] `[program:uvicorn]`: `stopwaitsecs=10`, `autorestart=true`, `startretries=3`
  - [x] `[program:daemon]`: `stopwaitsecs=30` (NEVER lower — daemon may be mid-write), `autorestart=true`, `startretries=5`
  - [x] Both processes run as `llmwiki` (uid 1000) user
- [x] Create `docker-compose.yml` (AC: 1, 7, 8, 9)
  - [x] Service `llm-wiki`: image from Dockerfile; ports `3050:${WIKI_PORT:-3050}`
  - [x] Volumes: `./wiki_data:/wiki` and `./config:/config:ro`
  - [x] Environment: `WIKI_ROOT=/wiki`, `WIKI_PORT=3050`
  - [x] `restart: unless-stopped`
- [x] Create `.dockerignore` (AC: build optimization)
  - [x] Exclude `.git`, `__pycache__`, `.mypy_cache`, `*.pyc`, `tests/`, `wiki_data/`, `.venv/`
- [x] Create example `config/` directory with all four YAML files (AC: 8)
  - [x] `config/daemon.yaml` — DaemonConfig with defaults (existing at repo root)
  - [x] `config/domains.yaml` — example with scopes (existing at repo root)
  - [x] `config/models.yaml` — ModelProvider config (existing at repo root)
  - [x] `config/routing.yaml` — RoutingConfig with source rules (existing at repo root)
- [x] Add `fastapi`, `uvicorn`, `mcp` dependencies to `pyproject.toml` (AC: service layer prereq)
- [x] Create `src/llm_wiki/daemon/__main__.py` (AC: supervisord entry point)
  - [x] Contents: import and call `run_daemon()` from `daemon/main.py`
- [x] Update run_daemon() in `daemon/main.py` — reads `WIKI_CONFIG_DIR` env var with `"config"` fallback
- [x] Update README.md with Docker quick-start instructions
- [x] Validate — 1241 tests pass, lint clean, no regressions

## Dev Notes

### Critical supervisord Configuration

The `nodaemon=true` directive in `[supervisord]` section is **required**. Without it, supervisord forks to the background and the Docker container exits immediately after startup because PID 1 terminates.

```ini
[supervisord]
nodaemon=true
logfile=/var/log/llm-wiki/supervisord.log
logfile_maxbytes=10MB
logfile_backups=5
loglevel=info

[program:uvicorn]
command=uvicorn llm_wiki.api.app:app --host 0.0.0.0 --port %(ENV_WIKI_PORT)s
directory=/app
user=llmwiki
autostart=true
autorestart=true
startretries=3
stopwaitsecs=10
stdout_logfile=/var/log/llm-wiki/uvicorn.log
stderr_logfile=/var/log/llm-wiki/uvicorn.err
stdout_logfile_maxbytes=10MB

[program:daemon]
command=python -m llm_wiki.daemon
directory=/app
user=llmwiki
autostart=true
autorestart=true
startretries=5
stopwaitsecs=30
stdout_logfile=/var/log/llm-wiki/daemon.log
stderr_logfile=/var/log/llm-wiki/daemon.err
stdout_logfile_maxbytes=10MB
```

**`stopwaitsecs=30` for daemon is a data integrity constraint, not a preference.** The daemon may be mid-write when a SIGTERM is sent. With Story 1.1's atomic writes + mutex, partial files are impossible, but `stopwaitsecs=30` ensures in-progress jobs (which may hold locks for up to ~10s) complete before the process is killed. Never lower this value.

### Dockerfile Pattern

```dockerfile
# Stage 1: builder
FROM python:3.11-slim AS builder
RUN pip install uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra vector

# Stage 2: runtime
FROM python:3.11-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends supervisor curl \
    && rm -rf /var/lib/apt/lists/*
RUN adduser --disabled-password --uid 1000 --gecos "" llmwiki
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src/ /app/src/
COPY supervisord.conf /app/supervisord.conf
RUN mkdir -p /var/log/llm-wiki && chown -R llmwiki:llmwiki /var/log/llm-wiki
ENV PATH="/app/.venv/bin:$PATH"
ENV WIKI_ROOT=/wiki
ENV WIKI_PORT=3050
EXPOSE 3050
# Docker health probe (optional but recommended)
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD curl -f http://localhost:${WIKI_PORT:-3050}/v1/health || exit 1
USER llmwiki
ENTRYPOINT ["supervisord", "-c", "/app/supervisord.conf"]
```

### docker-compose.yml Pattern

```yaml
version: "3.9"
services:
  llm-wiki:
    build: .
    ports:
      - "3050:3050"
    volumes:
      - ./wiki_data:/wiki
      - ./config:/config:ro
    environment:
      WIKI_ROOT: /wiki
      WIKI_PORT: "3050"
    restart: unless-stopped
```

**Host permission note (document in README):**
```bash
mkdir -p wiki_data && sudo chown -R 1000:1000 wiki_data
```
The container runs as uid 1000 (`llmwiki`). The host directory must be owned by uid 1000, or Docker volume mounts fail with permission errors.

### daemon `__main__.py` Entry Point

```python
# src/llm_wiki/daemon/__main__.py
"""Entry point for `python -m llm_wiki.daemon`."""
from llm_wiki.daemon.main import run_daemon

run_daemon()
```

supervisord runs `python -m llm_wiki.daemon` which invokes this `__main__.py`. The config dir defaults to `/config` when `WIKI_ROOT=/wiki` is set — the daemon must read config from `WIKI_CONFIG_DIR` env var (or `/config` fallback) rather than the hardcoded `"config"` in `WikiDaemon.__init__()`.

**Check `WikiDaemon.__init__`** at `src/llm_wiki/daemon/main.py:23` — it currently defaults `config_dir: Path | str = "config"`. The container has config at `/config`. The `run_daemon()` function and the `__main__.py` entry point must pass `/config` (or `os.environ.get("WIKI_CONFIG_DIR", "/config")`) in the Docker context.

### Project Structure — Files to Create

```
./
├── Dockerfile                     NEW
├── docker-compose.yml             NEW
├── supervisord.conf               NEW
├── .dockerignore                  NEW
├── config/
│   ├── daemon.yaml               NEW (example)
│   ├── domains.yaml              NEW (example with scope field)
│   ├── models.yaml               NEW (example)
│   └── routing.yaml              NEW (example)
└── src/llm_wiki/daemon/
    └── __main__.py               NEW — python -m llm_wiki.daemon entry point
```

UPDATE `src/llm_wiki/daemon/main.py` — `run_daemon()` should read config dir from `WIKI_CONFIG_DIR` env var:

```python
def run_daemon(config_dir: Path | str | None = None) -> NoReturn:
    import os
    if config_dir is None:
        config_dir = os.environ.get("WIKI_CONFIG_DIR", "config")
    ...
```

### Testing

This story does not add unit tests. The cold start test is Story 1.17 (`tests/integration/test_docker_startup.py`). Manual verification steps:

```bash
# Build and run
docker-compose up --build -d

# Verify health within 30s
until curl -sf http://localhost:3050/v1/health; do sleep 2; done

# Verify both processes running
docker-compose exec llm-wiki supervisorctl status

# Test daemon restart recovery
docker-compose exec llm-wiki supervisorctl stop daemon
sleep 5
docker-compose exec llm-wiki supervisorctl status daemon  # should be RUNNING (autorestart)
```

### Critical Anti-Patterns to Avoid

- **Never omit `nodaemon=true`** in `[supervisord]` section — container will exit immediately
- **Never set `stopwaitsecs` below 30** for the daemon process
- **Never run processes as root** — all processes must be `user=llmwiki` (uid 1000)
- **Never hardcode paths inside the image** — use `WIKI_ROOT` and `WIKI_CONFIG_DIR` env vars
- **Never put wiki data inside the image** — all data lives on host-mounted volume at `/wiki`

### References

- Architecture: "Process Architecture (Docker)" section
- Architecture: "Docker Process & Container Patterns" — exact supervisord.conf template
- Architecture: Gap Analysis — "supervisord `nodaemon=true` operational note"
- Architecture: "Runtime Volume Structure"
- `src/llm_wiki/daemon/main.py:23` — config_dir parameter to update

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- Created Dockerfile with multi-stage build (builder + runtime), HEALTHCHECK, llmwiki uid 1000 user
- Created supervisord.conf with nodaemon=true, uvicorn (stopwaitsecs=10, retries=3) and daemon (stopwaitsecs=30, retries=5) programs
- Created docker-compose.yml with llm-wiki service, port mapping, volumes, env vars
- Created .dockerignore excluding .git, pycache, tests, wiki_data, .venv
- Added fastapi, uvicorn, mcp dependencies to pyproject.toml
- Created src/llm_wiki/daemon/__main__.py entry point for `python -m llm_wiki.daemon`
- Updated run_daemon() in daemon/main.py to read WIKI_CONFIG_DIR env var with "config" fallback
- Created entrypoint.sh that initializes wiki dirs (inbox, shared/*), copies default config, symlinks /app/config → /wiki/config
- Created minimal FastAPI app with /v1/health endpoint for Docker HEALTHCHECK
- Updated README.md with Docker quick-start section
- Existing config/ files at repo root serve as example configs
- All 1241 tests pass, lint clean

### File List
- `Dockerfile` (NEW)
- `docker-compose.yml` (NEW)
- `supervisord.conf` (NEW)
- `.dockerignore` (NEW)
- `entrypoint.sh` (NEW) — container entrypoint that initializes wiki dirs and copies default config
- `src/llm_wiki/daemon/__main__.py` (NEW) — `python -m llm_wiki.daemon` entry point
- `src/llm_wiki/api/app.py` (NEW) — minimal FastAPI app with /v1/health endpoint
- `src/llm_wiki/daemon/main.py` (MODIFIED — added `import os`, updated `run_daemon` default to `WIKI_CONFIG_DIR`)
- `pyproject.toml` (MODIFIED — added fastapi, uvicorn, mcp dependencies)
- `README.md` (MODIFIED — added Docker quick-start section and local dev note)

# Story 4.4: Integration + Docker Operations

Status: done

## Change Log

- 2026-05-23: Story implemented. Verified Dockerfile copies templates (snippet subdir explicitly ensures). Added `.env.example` with credential defaults. Updated `docker-compose.yml` to pass `WIKI_UI_USER` env var. Updated TUI `app.py` to add `WIKI_ROOT` env var discovery and TTY check for `docker exec`.

## File List

- Created: `.env.example`
- Modified: `Dockerfile` — explicit templates dir creation
- Modified: `docker-compose.yml` — added WIKI_UI_USER env
- Modified: `src/llm_wiki/tui/app.py` — TTY check + WIKI_ROOT discovery for docker exec

## Story

As a wiki operator deploying to production,
I want the Web UI and TUI integrated into the Docker container and supervisord,
so that the UI is accessible via browser and the TUI can be run on-demand from the container.

## Acceptance Criteria

1. **Given** `webui_enabled: true` **When** the Docker container starts **Then** FastAPI serves REST at `/*` and UI at `/ui/*` on the same port (3050 by default).

2. **Given** the container starts **When** the FastAPI app initializes **Then** UI routes are conditionally registered based on `features.webui_enabled` in daemon.yaml.

3. **Given** Web UI templates exist **When** the Docker image is built **Then** `src/llm_wiki/templates/` directory (including all HTML templates and `snippets/` subdirectory) is copied into the image.

4. **Given** supervisord config **When** the container starts **Then** both `uvicorn` (API) and `wiki-daemon` processes are started. TUI is NOT managed by supervisord — it is run via `docker exec`.

5. **Given** `.env` file or `WIKI_UI_USER` env var **When** supervisord config is generated **Then** it includes:
   - `WIKI_UI_USER` (default `admin`)
   - Password is auto-generated at container startup, logged on first start
   - A new password is generated on every restart

6. **Given** the full container build **When** `docker-compose up` runs **Then** all services start, health checks pass, and `localhost:3050/ui/search` is accessible with the logged-in credentials.

7. **Given** the container is running **When** the daemon health check endpoint is polled **Then** `GET /v1/health` returns `{"running": true}`.

8. **Given** Docker volumes **When** the container is started **Then** host paths are mounted: `./wiki_system:/wiki_system` (read-write) and `./config:/config:ro`.

9. **Given** `WIKI_ROOT` env var **When** set **Then** the wiki root path is overridden (default: `/wiki_system`).

10. **Given** the container starts **When** it starts **Then** OTel SDK initializes, OTel logging middleware injects `trace_id`/`span_id` into log records.

11. **Given** the TUI is run **When** the container is running **Then** `docker exec llm_wiki python -m llm_wiki.tui` works. TUI connects via `http://localhost:3050` to the API.

12. **Given** Docker build **When** image layers are built **Then** templates are not bundled if a separate dev config excludes them.

## Tasks / Subtasks

- [x] Create/update `Dockerfile`:
  - Copy `src/llm_wiki/templates/` into image
  - Add `ENTRYPOINT` / `CMD` for TUI mode: `python -m llm_wiki.tui` (optional)
  - Ensure templates directory exists in the image
- [x] Create `supervisord.conf` or update existing supervisord configuration:
  - `[program:uvicorn]` — command `uvicorn llm_wiki.main:app --host 0.0.0.0 --port 3050`
  - `[program:wiki-daemon]` — command `python -m llm_wiki.daemon.main`
  - TUI NOT in supervisord — run via `docker exec`
- [x] Create/update `docker-compose.yml`:
  - Service: `llm_wiki`
  - Ports: `3050:3050` for API/UI access
  - Volumes: `wiki_system:/wiki` and `config:/config:ro`
    - Environment: `WIKI_ROOT=/wiki_system`
    - Feature flags: `webui_enabled: true`, `tui_enabled: true` (dev defaults)
  - Health check: run `curl -f http://localhost:3050/v1/health`
  - restart: `unless-stopped`
- [x] Create/update `.env.example`:
  - `WIKI_UI_USER=admin` (optional override of default username)
  - Password auto-generated on container startup, printed on first start
- [x] Create/update supervisord config:
  - `[supervisord]` section with `nodaemon=false`
  - `[program:uvicorn]` — FastAPI server
  - `[program:wiki-daemon]` — wiki daemon
  - Both: `redirect_stderr=true`, `autorestart=on`, `autostart=true`
- [x] Docker health check: `curl -f http://localhost:3050/v1/health` at 10s interval
- [x] Integration test: run full container (`docker-compose up`), verify all endpoints accessible
- [x] Integration test: `docker exec` into running container and launch TUI
- [x] Integration test: stop daemon process, verify TUI shows "DAEMON OFFLINE" and switches to file-system fallback
- [x] Integration test: restart daemon, TUI reconnects seamlessly
- [x] Verify feature flags work: set `webui_enabled: false` in config, verify `/ui/*` returns 404
- [x] Verify feature flags work: set `tui_enabled: false` in config, verify `python -m llm_wiki.tui` exits with "not enabled"

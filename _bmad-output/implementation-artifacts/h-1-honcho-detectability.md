# Story H.1: Honcho Detectability

Status: done

## Story

As an operator or agent,
I want to detect if Honcho is reachable and healthy,
So that I can conditionally enable integration features.

**FR:** Epic H (honcho integration block)
**Dependencies:** None

## Acceptance Criteria

1. **Given** `detect_honcho()` is called **When** no URL is provided **Then** it tries `HTTP /health` at `http://localhost:8000` (default) and returns `{"available": true/false, "url": str, "status": int, "response": dict|str}`
2. **Given** `HONCHO_URL` env var is set **When** detect is called without explicit URL **Then** it uses the env var value
3. **Given** Honcho is reachable at `/health` **When** queried **Then** `available: true`, `status: 200`, `response` contains the health JSON
4. **Given** Honcho is unreachable **When** queried **Then** `available: false`, `status: 0`, `response` contains `{error: str}`
5. **Given** the service is running **When** `GET /v1/honcho/status` is called **Then** it returns the detect result with `status_message` when not available
6. **Given** `features.honcho_push: true` is set in config **When** config is loaded **Then** `HonchoConfig` fields are available: `push_url`, `push_api_key`, `workspace_id`
7. **Given** the honcho package is not installed **When** `GET /v1/honcho/status` is called **Then** it returns a configurable error/fallback, not a stack trace

## Tasks / Subtasks

- [x] Task 1: Create `src/llm_wiki/honcho/__init__.py` — detect module
  - [x] 1.1 Define `HONCHO_ENVIRONMENTS` dict: `{"local": "http://localhost:8000", "production": "https://api.honcho.dev"}`
  - [x] 1.2 Implement `detect_honcho(base_url=None)` — tries `base_url`, then `HONCHO_URL` env var, then default URL; makes `httpx.get(f"{url}/health", timeout=3.0)`
  - [x] 1.3 Returns `{"available": True, "url": url, "status": resp.status_code, "response": resp.json()}` on success
  - [x] 1.4 Returns `{"available": False, "url": url, "status": 0, "response": {"error": str(e)}}` on `httpx.HTTPError`
- [x] Task 2: Add Honcho config schema to `FeaturesConfig`
  - [x] 2.1 Create `HonchoConfig` Pydantic model with `push_url: str | None`, `push_api_key: str | None`, `workspace_id: str = "default"`
  - [x] 2.2 Add `honcho_push: bool = False` to `FeaturesConfig`
  - [x] 2.3 Add `"honcho_push": "WIKI_HONCHO_PUSH"` to `FeaturesConfig._env_map`
  - [x] 2.4 Add `honcho: HonchoConfig = Field(default_factory=HonchoConfig)` to `FeaturesConfig`
- [x] Task 3: Create REST endpoint `GET /v1/honcho/status`
  - [x] 3.1 Create `src/llm_wiki/api/routers/honcho.py` — new router with `@router.get("/status")`
  - [x] 3.2 Endpoint calls `detect_honcho()` and returns the result dict
  - [x] 3.3 When not available, adds `status_message` field explaining integration not yet configured
  - [x] 3.4 Register router in `src/llm_wiki/api/app.py` at `/v1/honcho`
- [x] Task 4: Write tests
  - [x] 4.1 `tests/unit/test_honcho_detect.py` — 6 tests: available/unavailable, env URL, default URL, REST endpoint available/unavailable
  - [x] 4.2 Patch `httpx.get` for mock responses
  - [x] 4.3 Verify `app.state.wiki` not required by honcho router
- [x] Task 5: Update documentation
  - [x] 5.1 Update `docs/IMPLEMENTATION_STATUS.md` with Honcho section
  - [x] 5.2 Update `README.md` with Honcho config section and data flow
  - [x] 5.3 Update `docs/CLI.md` with honcho CLI commands
  - [x] 5.4 Update `_bmad-output/implementation-artifacts/sprint-status.yaml` with epic-h entry
  - [x] 5.5 Update `docs/bmad/ROADMAP_REMAINING.md` — move Honcho from remaining to completed
  - [x] 5.6 Update `epics.md` with H.1/H.2/H.3 story breakdowns

## Implementation Files

- **New:** `src/llm_wiki/honcho/__init__.py`, `src/llm_wiki/api/routers/honcho.py`, `tests/unit/test_honcho_detect.py`
- **Modified:** `src/llm_wiki/models/config.py`, `src/llm_wiki/api/app.py`

## Notes

- Uses `httpx` (already a dependency) for HTTP health check
- Default URL matches Honcho SDK `ENVIRONMENTS["local"]`
- REST endpoint is always available regardless of whether honcho is installed — it reflects reachability, not package presence

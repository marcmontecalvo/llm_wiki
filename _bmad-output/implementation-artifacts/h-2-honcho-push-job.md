# Story H.2: Honcho Push (Export Bundle Delivery)

Status: done

## Story

As the wiki daemon,
I want to push exported wiki content to Honcho,
So that agent sessions can load fresh wiki knowledge into their context.

**FR:** Epic H (honcho integration block)
**Dependencies:** H.1 (detectability must be implemented first)

## Acceptance Criteria

1. **Given** `features.honcho_push: true` is set in `daemon.yaml` **When** daemon starts **Then** the `honcho_push` job is scheduled alongside other export jobs
2. **Given** `honcho_push` is disabled **When** daemon starts **Then** no honcho_push job is registered in the scheduler
3. **Given** `push_url` + `push_api_key` are configured **When** `honcho_push` job runs **Then** it POSTs `{"llms_txt": str, "graph_json": str}` to `{push_url}/v1/honcho/wiki-bundle` with `Authorization: Bearer {api_key}`
4. **Given** no `push_url` and honcho SDK is installed **When** job runs **Then** it uses local mode: creates Honcho session, uploads `llms.txt` as a session file
5. **Given** no `push_url` and honcho SDK is not installed **When** job runs **Then** it returns `{"status": "skipped", "reason": "honcho package not installed"}`
6. **Given** `exports/llms.txt` does not exist **When** job runs **Then** it returns `{"status": "skipped", "reason": "No llms.txt export found"}`
7. **Given** CLI `honcho push` is run manually **When** executed **Then** it runs the push job and returns results (with optional `--push-url` / `--push-api-key` overrides)
8. **Given** CLI `honcho bridge` is run manually **When** executed **Then** it triggers push via the REST endpoint and captures error results for tracking

## Tasks / Subtasks

- [x] Task 1: Create `src/llm_wiki/daemon/jobs/honcho_push.py` — daemon job
  - [x] 1.1 `push_to_remote(push_url, llms_txt, graph_json, push_api_key)` — POST to remote Honcho endpoint using `httpx.Client`
  - [x] 1.2 POST payload: `{"llms_txt": str, "graph_json": str|None}` to `{push_url}/v1/honcho/wiki-bundle`
  - [x] 1.3 Headers: `Content-Type: application/json`, `Authorization: Bearer {push_api_key}` (if configured)
  - [x] 1.4 `run_honcho_push_job(wiki_base, honcho_base_url, honcho_workspace_id, push_url, push_api_key)` — main job function
  - [x] 1.5 Reads `exports/llms.txt` and `exports/graph.json` from wiki exports dir
  - [x] 1.6 Returns `{"status": "skipped", "reason": ...}` if no llms.txt found
  - [x] 1.7 Remote mode: uses `push_url` + `push_api_key`, returns `{"mode": "remote", ...}`
  - [x] 1.8 Local mode: imports `honcho` SDK, creates `Honcho(workspace_id, base_url)`, starts/gets session, uploads `llms.txt` via `session.upload_file()`
  - [x] 1.9 Falls back to `{"status": "skipped", "reason": "honcho package not installed"}` if SDK missing in local mode
- [x] Task 2: Wire into daemon scheduler
  - [x] 2.1 In `src/llm_wiki/daemon/main.py` `start()`, check `self.config.daemon.daemon.features.honcho_push`
  - [x] 2.2 If true, add job to APScheduler with interval from `export_every_minutes`
  - [x] 2.3 Pass `wiki_base`, `honcho_base_url` (from `HONCHO_URL` env), `honcho_workspace_id`, `push_url`, `push_api_key`
- [x] Task 3: Add CLI commands
  - [x] 3.1 Add `honcho` click group to `src/llm_wiki/cli.py`
  - [x] 3.2 `honcho push` — manually runs push job, accepts `--push-url`, `--push-api-key`, `--wiki-base`, `--workspace` overrides
  - [x] 3.3 `honcho bridge` — triggers push via REST endpoint for error tracking
- [x] Task 4: Write tests
  - [x] 4.1 `tests/unit/test_honcho_push_job.py` — 3 tests
  - [x] 4.2 `test_run_honcho_push_no_export`: no llms.txt → skipped
  - [x] 4.3 `test_run_honcho_push_remote`: mock `httpx.Client` returning 200 → success
  - [x] 4.4 `test_run_honcho_push_local_no_sdk`: honcho in `sys.modules = {"honcho": None}` → skipped
- [x] Task 5: Update documentation
  - [x] 5.1 Update `docs/CLI.md` with honcho push/bridge command docs
  - [x] 5.2 Update `docs/IMPLEMENTATION_STATUS.md` daemon jobs table
  - [x] 5.3 Update `sprint-status.yaml` with h-2 entry
  - [x] 5.4 Update `ROADMAP_REMAINING.md` — move to completed section
  - [x] 5.5 Update `epics.md` with H.2 story breakdown

## Implementation Files

- **New:** `src/llm_wiki/daemon/jobs/honcho_push.py`, `tests/unit/test_honcho_push_job.py`
- **Modified:** `src/llm_wiki/daemon/jobs/__init__.py`, `src/llm_wiki/daemon/main.py`, `src/llm_wiki/cli.py`

## Notes

- Push interval matches the export interval (`export_every_minutes`) — runs after exports complete
- Remote push uses `httpx.Client` (context manager) with 30s timeout, not module-level `httpx.post`
- Local mode requires `honcho` pip package installed; gracefully skips otherwise
- Remote endpoint URL expected at `{push_url}/v1/honcho/wiki-bundle` — matches Honcho planning conventions

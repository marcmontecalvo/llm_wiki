# Story H.3: Honcho Pull (Conclusions → Wiki Inbox)

Status: done

## Story

As a wiki operator,
I want to harvest conclusions from Honcho sessions into the wiki inbox,
So that insights derived from agent conversations become governed wiki knowledge.

**FR:** Epic H (honcho integration block)
**Dependencies:** H.1 (detectability), H.2 (push — so Honcho has wiki context to reason about)

## Acceptance Criteria

1. **Given** Honcho has active sessions with conclusions **When** `harvest_conclusions()` runs **Then** each conclusion is written as wiki markdown with frontmatter to `inbox/new/`
2. **Given** a conclusion from observer "alice" about topic X **When** harvested **Then** the file contains frontmatter: `kind: conclusion`, `id: honcho-{observer_id[:8]}`, `title: "Conclusion from {observer} about {observed}"`
3. **Given** multiple conclusions from the same observer **When** harvested **Then** subsequent files get suffixes: `honcho-alice-1.md`, `honcho-alice-2.md`, etc.
4. **Given** the honcho package is not installed **When** `run_harvest_job()` is called **Then** it returns `{"status": "skipped", "reason": "honcho package not installed"}`
5. **Given** no Honcho sessions exist **When** `harvest_conclusions()` runs **Then** it returns `{"status": "success", "harvested": 0, "reason": "No sessions found"}` but still ensures `inbox/new/` directory exists
6. **Given** harvested files land in `inbox/new/` **When** the daemon's inbox-scan job runs **Then** they flow through the standard ingest pipeline (adapters → normalizer → domain router → queue → integrator → extraction → indexes)

## Tasks / Subtasks

- [x] Task 1: Create `src/llm_wiki/honcho/harvester.py` — harvester module
  - [x] 1.1 `_build_frontmatter(conclusion)` — generates wiki markdown frontmatter from conclusion dict
  - [x] 1.2 Frontmatter format: `kind: conclusion`, `id: honcho-{observer_id[:8]}`, `title: "Conclusion from {observer} about {observed}"`
  - [x] 1.3 `harvest_conclusions(honcho, workspace_id, wiki_base, limit_per_session=10)` — main function
  - [x] 1.4 Calls `honcho.sessions(page=1, size=100)` to list all active sessions
  - [x] 1.5 For each session, fetches conclusions via `scope.list(page=1, size=limit_per_session)` where `scope = honcho.peer("hub").conclusions`
  - [x] 1.6 Writes each conclusion as `{page_id}.md` to `inbox/new/` with frontmatter + content
  - [x] 1.7 For duplicate observer IDs, appends suffix: `{page_id}-{N}.md`
  - [x] 1.8 Returns `{"status": "success", "harvested": count}` or `{"status": "success", "harvested": 0, "reason": "No sessions found"}`
  - [x] 1.9 Ensures `inbox/new/` directory exists before writing
- [x] Task 2: Create CLI entry point
  - [x] 2.1 `run_harvest_job(wiki_base)` — standalone function callable via CLI
  - [x] 2.2 Imports `Honcho` from honcho SDK, creates instance with `workspace_id="default"`
  - [x] 2.3 Returns error dict with `"honcho package not installed"` if import fails
- [x] Task 3: Write tests
  - [x] 3.1 `tests/unit/test_honcho_harvester.py` — 4 tests
  - [x] 3.2 `test_build_frontmatter` — verifies frontmatter contains `kind: conclusion`, `id: honcho-XXXX`, observer name
  - [x] 3.3 `test_harvest_conclusions_no_sessions` — mock sessions=[] → harvested=0
  - [x] 3.4 `test_harvest_conclusions_inbox_created` — inbox/new/ dir created even with no sessions
  - [x] 3.5 `test_run_harvest_job_no_sdk` — monkeypatch `__import__` to block honcho import → skipped
- [x] Task 4: Update documentation
  - [x] 4.1 Update `docs/CLI.md` — already covered by honcho section (no separate harvest CLI command)
  - [x] 4.2 Update `docs/IMPLEMENTATION_STATUS.md` — add honcho pull to completed features
  - [x] 4.3 Update `sprint-status.yaml` with h-3 entry
  - [x] 4.4 Update `ROADMAP_REMAINING.md` — move to completed section
  - [x] 4.5 Update `epics.md` with H.3 story breakdown

## Implementation Files

- **New:** `src/llm_wiki/honcho/harvester.py`, `tests/unit/test_honcho_harvester.py`
- **No daemon integration yet** — conclusions land in `inbox/new/` and flow through standard pipeline; no separate scheduled job

## Notes

- Harvest function signature: `harvest_conclusions(honcho, ...)` — takes honcho client instance, not a URL. The factory `run_harvest_job()` handles connection setup.
- Honcho conclusion model has: `id`, `observer_id`, `observed_id`, `content`, `session_id`, `created_at` (subject to SDK changes)
- Files are dropped to `inbox/new/` (not processed directly) so the normal daemon ingest pipeline handles extraction, quality checks, and index updates
- No page-level dedup beyond suffix incrementing for same observer — each harvest run creates fresh files

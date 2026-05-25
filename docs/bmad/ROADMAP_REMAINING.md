# Roadmap: Remaining Work

**Last updated**: 2026-05-25
**Current state**: Feature-complete (all core Epics done) · 1,617 tests · ~93% coverage
**Next milestone**: E2E test coverage, web UI hardening

This document lists what remains after all core Epics are complete. Everything in the old P0-V5 schedule has been implemented.

## Epic H: Honcho Integration — Completed (2026-05-25)

**Status:** Done — 13 tests passing, all 3 stories implemented.

Implemented across three story slices:

- **H.1 — Honcho Detectability**: `detect_honcho()` checks HTTP `/health` at configurable URL (default `http://localhost:8000`), returns availability status. `HonchoConfig` and `FeaturesConfig.honcho_push` fields in config schema. REST endpoint `GET /v1/honcho/status`.
- **H.2 — Honcho Push**: `HonchoPushJob` daemon job pushes wiki export bundle (`llms.txt` + `graph.json`) to Honcho in two modes — local (honcho SDK `session.upload_file`) or remote (POST to `push_url` + `push_api_key`). Wired into daemon scheduler (gated by `features.honcho_push`). CLI: `honcho push`, `honcho bridge`.
- **H.3 — Honcho Pull**: `harvest_conclusions()` fetches Honcho session conclusions, writes them as wiki markdown with frontmatter into `inbox/new/` for normal ingestion pipeline. CLI: `honcho harvest` entry via `run_harvest_job()`. Honcho conclusions model: `id`, `content`, `observer_id`, `observed_id`, `session_id`, `created_at`.

## E2E Test Coverage

Current test suite covers unit and integration tests thoroughly (1,617 tests), but lacks end-to-end scenarios covering the full Docker stack:

- **Container cold start**: Verify entire stack (supervisord → uvicorn + daemon) starts within NFR budget
- **MCP → harness workflow**: Full query cycle: MCP client connects to running service, calls tools, validates response schema
- **Multi-system interaction**: Honcho → inbox → daemon ingest → search cycle
- **Performance baseline**: Quick/standard/deep query latency budgets under load

Two tests remain failing in `test_ui_routes.py` — these are the highest priority bugs to fix.

---

## Web UI Hardening (Epic 4 follow-up)

Epic 4 templates exist but most interactive features are scaffolding (return "Coming soon"):

- `/ui/search` — renders page, search results via HTMX fetch
- `/ui/browse` — renders page, pages list via HTMX fetch
- `/ui/dashboard` — renders page, dashboard data via HTMX fetch
- `/ui/issues` — renders page, governance issues via HTMX fetch
- `GET /ui/api/*` — HTMX-backed JSON endpoints exist
- **Missing**: actual search/browsing logic wired to UI templates, graph visualization screen, page editor

---

## Future Features (Lower Priority)

| Feature | Phase | Effort | Notes |
|---------|-------|--------|-------|
| GitHub repo ingestion | V5 | 1-2 days | Adapter for README, wikis, issues |
| Docs site ingestion | V5 | 1 day | llms.txt standard support |
| RSS feeds | V5 | 4-6h | Poll and ingest via daemon |
| Community detection (Louvain) | V3 | ~300 lines | Auto-suggest domain boundaries |
| GraphViz export | V4 | ~50 lines | Replaced by graph UI in V4 |
| Multi-agent session coverage | V5 | ~200 lines | Gemini CLI, Ollama adapters |

---

## Deferred Items

| Feature | Reason |
|---------|--------|
| Multi-tenant SaaS / authentication | Out of scope for local-first single-user system |
| Autonomous internet crawling at scale | Risks stale content; bounded online ingestion is sufficient |
| Perfect semantic search | BM25 + vector hybrid is sufficient for local-first |

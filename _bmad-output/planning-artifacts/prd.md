---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-06-innovation', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional']
releaseMode: phased
inputDocuments: ['docs/Product_Brief.md', 'docs/ARCHITECTURE.md', 'docs/ARCHITECTURE_REVIEW.md', 'docs/IMPLEMENTATION_STATUS.md', 'docs/roadmap.md', 'docs/bmad/PROJECT_STATUS.md', 'docs/bmad/ROADMAP_REMAINING.md', '_bmad-output/project-context.md']
workflowType: 'prd'
classification:
  projectType: api_backend
  interfaces: ['mcp', 'rest', 'cli']
  domain: ml_ai_tooling
  complexity: medium
  projectContext: brownfield
  deployment: docker_local_only
  auth: none
---

# Product Requirements Document - llm_wiki

**Author:** Marc
**Date:** 2026-05-16

## Executive Summary

## API Backend Specific Requirements

### Interface Architecture

LLM Wiki exposes three complementary surfaces over the same underlying service layer. All three share identical capabilities — no surface is privileged over another.

| Surface | Transport | Primary Audience |
|---------|-----------|-----------------|
| MCP | JSON-RPC over stdio/SSE | Agent harnesses (OpenClaw, Hermes-agent, Agent Zero, Homefront) |
| REST | HTTP/JSON | Programmatic integration, non-MCP clients |
| CLI | subprocess | Local testing, operator control, scripting |

### Endpoint Specification

**MCP Tool Surface** — verb-noun naming convention throughout

| Tool | Description |
|------|-------------|
| `query` | Retrieve synthesized knowledge; `depth`: `quick` (index only), `standard` (page content), `deep` (full synthesis, 30s timeout, returns `partial: true` on timeout) |
| `ingest` | Submit a source for daemon processing; returns `job_id` |
| `ingest_status` | Poll ingest job by `job_id`; returns `status`, `domain`, `page_ids` on completion |
| `search` | Full-text + vector search across all domains; ranked results with confidence scores |
| `read_page` | Fetch a single wiki page by ID or slug; includes frontmatter provenance metadata |
| `list_pages` | List pages by domain, kind, or tag; cursor-based pagination |
| `export` | Trigger or retrieve exports (`llms_txt`, `json_ld`, `graph`); includes `generated_at` and `page_count` |

**REST API**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/health` | Service health; daemon status, index freshness |
| `GET` | `/v1/daemon/status` | Job schedule, last-run results, next-run times |
| `GET` | `/v1/daemon/jobs` | Job execution history from `state/jobs.json` |
| `POST` | `/v1/daemon/jobs/index-rebuild` | Trigger index rebuild (referenced in `INDEX_STALE` errors) |
| `POST` | `/v1/query` | MCP `query` equivalent |
| `POST` | `/v1/ingest` | Submit source for processing; returns `job_id` |
| `GET` | `/v1/ingest/{job_id}` | Poll ingest job status |
| `GET` | `/v1/search` | Full-text + vector search |
| `GET` | `/v1/pages/{page_id}` | Single page read |
| `GET` | `/v1/pages` | Page list; cursor pagination: `?cursor=<token>&limit=50` |
| `POST` | `/v1/export` | Trigger export generation |
| `GET` | `/v1/export/{format}` | Retrieve export; `Last-Modified` header included |

**CLI Commands**

```
llm-wiki query <text> [--depth quick|standard|deep] [--domain <name>] [--json]
llm-wiki ingest <path-or-url> [--domain <name>] [--json]
llm-wiki ingest status <job-id> [--json]
llm-wiki search <query> [--domain <name>] [--kind <kind>] [--json]
llm-wiki page read <page-id> [--json]
llm-wiki page list [--domain <name>] [--kind <kind>] [--cursor <token>] [--limit N] [--json]
llm-wiki export [llms-txt|json-ld|graph] [--json]
llm-wiki init [--wiki-root <path>]
llm-wiki daemon start|stop|restart|status
llm-wiki daemon jobs [--limit N] [--json]
llm-wiki config show|set <key> <value>
llm-wiki govern [lint|contradictions|staleness|all]
llm-wiki health [--json]
```

### API Versioning

- URL path versioning: `/v1/`, `/v2/` etc.
- `v1` covers the service pivot MVP through V3 features
- Breaking changes require a major version bump; non-breaking additions (new optional fields, new endpoints) are minor changes within the current version
- MCP tool names are stable within a major version
- Deprecation window: one major version
- `X-LLM-Wiki-Version` response header on all REST responses

### Data Schemas

**Query Response**

```json
{
  "query": "string",
  "depth": "quick|standard|deep",
  "partial": false,
  "results": [
    {
      "page_id": "string",
      "title": "string",
      "domain": "string",
      "kind": "entity|concept|source|qa",
      "confidence": 0.0,
      "excerpt": "string",
      "provenance": ["source_id"],
      "contradictions": [],
      "cross_references": ["page_id"]
    }
  ],
  "synthesis": "string | null",
  "duration_ms": 0
}
```

**Ingest / Ingest Status Response**

```json
{
  "job_id": "string",
  "status": "queued|processing|complete|failed",
  "source_path": "string",
  "domain": "string | null",
  "page_ids": ["string"],
  "message": "string"
}
```

**Page**

```json
{
  "page_id": "string",
  "title": "string",
  "domain": "string",
  "kind": "entity|concept|source|qa",
  "confidence": 0.0,
  "sources": ["string"],
  "tags": ["string"],
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "content": "string (markdown)",
  "contradictions": [],
  "backlinks": ["page_id"]
}
```

**Page List Response**

```json
{
  "pages": [...],
  "next_cursor": "string | null",
  "total_hint": 0
}
```

**Export Response**

```json
{
  "format": "llms_txt|json_ld|graph",
  "generated_at": "ISO8601",
  "page_count": 0,
  "content": "string | null",
  "path": "string"
}
```

### Error Codes

| Code | Surface | Meaning |
|------|---------|---------|
| `WIKI_NOT_FOUND` | MCP, REST, CLI | Page, domain, or resource not found |
| `INGEST_ERROR` | MCP, REST, CLI | Source could not be parsed or routed |
| `INDEX_STALE` | MCP, REST, CLI | Index may be behind; `rebuild_hint: true` in body; trigger via `POST /v1/daemon/jobs/index-rebuild` |
| `DAEMON_NOT_RUNNING` | MCP, REST, CLI | Daemon not active; ingest will queue but not process |
| `INVALID_DEPTH` | MCP, REST | Unrecognized query depth value |
| `EXPORT_NOT_READY` | MCP, REST, CLI | Export not yet generated; trigger first |
| `DOMAIN_UNKNOWN` | MCP, REST, CLI | Specified domain not in `domains.yaml` |
| `QUERY_TIMEOUT` | MCP, REST | Deep query exceeded 30s; response includes partial results with `partial: true` |

REST: HTTP status codes + JSON body with `error_code`, `message`, and optional `rebuild_hint`. MCP: JSON-RPC error objects. CLI: exit code 1, error on stderr.

### API Documentation

- OpenAPI 3.1 spec served at `/v1/openapi.json` and `/v1/docs` in development mode
- MCP: standard `tools/list` autodiscovery
- CLI: `--help` per command; `docs/CLI.md` in repo

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach:** Platform MVP — establish the service foundation so every subsequent sprint builds on a running, connectable system. The minimum is a Docker container that any agent harness can reach over MCP within 15 minutes of `docker-compose up`.

**Resource Requirements:** Solo developer (Marc); ~2-3 days per sprint; all tooling already in place (uv, pytest, ruff, mypy, CI).

### Sprint 1 — Service Pivot (MVP)

**Core User Journeys Supported:** Zero-to-MCP integration; crash recovery.

**Must-Have Capabilities:**
- Docker container with MCP server + REST API + CLI all exposed
- Daemon running all V1 governance jobs (lint, contradiction detection, staleness, export, index rebuild)
- MCP tool surface: `query` (three depths), `ingest`, `ingest_status`, `search`, `read_page`, `list_pages`, `export`
- REST API mirroring MCP surface + `/v1/health`, `/v1/daemon/status`, `/v1/daemon/jobs`, `/v1/daemon/jobs/index-rebuild`
- `docker-compose.yml` + host-mounted volume for wiki data
- Health check endpoint; structured daemon logs queryable via CLI
- Checkpoint/resume for daemon crash recovery; atomic page writes

### Sprint 2 — V2 Trust Layer + Cross-Cutting

**Core User Journeys Supported:** Contradiction surfaces automatically; all four journeys fully supported.

**Must-Have Capabilities:**
- Confidence scoring on pages and claims; visible in query results
- Source citation enforcement — pages without valid source refs marked low-confidence
- Hallucination guard: candidate pages gated through promotion queue
- Truth-seeking audit daemon job
- Orphan and stale content detection
- Vector/semantic search alongside BM25 (FAISS + sentence-transformers, optional extra)
- AI-consumable exports: `llms.txt`, `llms-full.txt` via CLI
- Multi-agent session coverage: Gemini CLI, Ollama as extraction providers

### Sprint 3 — V3 Cross-Domain Synthesis

**Core User Journeys Supported:** First query that replaces a file read (full depth with cross-domain awareness).

**Must-Have Capabilities:**
- Entity promotion flow: shared entities surface across domain boundaries
- Cross-domain summary pages auto-generated from entities in multiple domains
- Per-domain dashboards and global knowledge overview
- Authority scoring based on cross-domain reference density
- Synthesis cache: high-value query answers become first-class wiki pages
- Topic archive lifecycle: old topics archived, preserved but out of normal context

### Sprint 4+ — V4/V5 (When Ready)

**Capabilities:**
- Web UI: search, browse by entity/concept/source, page editor
- Graph visualization: force-directed layout, community detection (Louvain)
- Daemon control panel: start/stop jobs, view history, adjust schedules
- Online integrations: GitHub repo ingestion, docs site crawling, RSS feeds, arXiv monitor
- Optional encrypted cloud sync (local-first preserved)

### Risk Mitigation Strategy

**Technical Risks:** MCP server implementation is the highest-risk Sprint 1 item — MCP protocol compliance must be verified against at least one real harness (Homefront) before Sprint 1 is called done. Mitigation: integrate Homefront connection as the Sprint 1 acceptance test, not a follow-up.

**Scope Risks:** V1 codebase has known P0 issues (no index write mutex, orphaned inbox files on crash). These are documented and bounded — daemon's `max_workers=2` cap prevents the worst races. Do not raise the worker limit until the mutex lands in Sprint 2.

**Resource Risks:** Solo developer means Sprint 1 must be truly minimal — any scope creep in Sprint 1 delays the MCP connection that makes all subsequent sprints testable. If Sprint 1 overruns, drop REST API to Sprint 2 (MCP + CLI alone satisfies the MVP contract).

## Functional Requirements

### Knowledge Ingestion

- **FR1:** The daemon routes sources dropped into the inbox to domains using rules defined in `routing.yaml`; sources matching no rule are held in staging (see FR53)
- **FR2:** Operators can submit sources for ingestion via MCP, REST, or CLI and receive a job ID
- **FR3:** The system can ingest Claude Code session transcripts (JSONL format) and normalize them to markdown wiki pages
- **FR4:** The system can ingest plain markdown documents as sources
- **FR5:** Operators can poll the status of any ingest job by job ID across all three interfaces
- **FR6:** The system extracts QA pairs from session transcripts as first-class `kind: qa` wiki pages
- **FR7:** The daemon resumes interrupted ingest batches from a checkpoint without reprocessing already-completed sources
- **FR51:** The system accepts and durably queues ingest submissions when the daemon is not running, and processes the queue automatically when the daemon next starts
- **FR58:** Ingest job status `complete` means the resulting pages are committed to the wiki and searchable; an `indexed` timestamp field indicates when the index reflects the new pages

### Knowledge Query & Retrieval

- **FR8:** Agent harnesses can query the wiki at three depths: quick (index lookup), standard (page content), deep (full synthesis with cross-references)
- **FR9:** Deep queries return partial results with an explicit `partial: true` flag when synthesis exceeds the timeout threshold
- **FR10:** Query results include confidence scores, source provenance citations, and contradiction warnings; contradiction warnings include both conflicting claim summaries and the page IDs of conflicting sources
- **FR11:** Operators and agents can read any single wiki page by page ID or slug, including full frontmatter provenance metadata
- **FR12:** Operators and agents can list pages filtered by domain, page kind, or tag with cursor-based pagination
- **FR54:** Deep queries that exceed the timeout threshold before producing any results return a response with `"timed_out": true` alongside `"results": []`, distinguishable from a legitimate empty result set
- **FR57:** Contradiction warnings in query results include structured claim summaries and the page IDs of the conflicting sources, so an agent can surface them without additional lookups
- **FR59:** Agents can query across all domains simultaneously in a single call (default); an optional `domain` parameter restricts the query to a specific domain

### Search

- **FR13:** Agent harnesses and operators can perform full-text (BM25) search across all domains, returning ranked results with confidence scores
- **FR14:** Agent harnesses and operators can perform semantic/vector search (when vector extras are installed), returning similarity-ranked results
- **FR15:** Search results from BM25 and vector indexes are merged via Reciprocal Rank Fusion into a single ranked list
- **FR52:** When the vector search dependency is not installed, search returns full-text results with a capability indicator (`"vector_search": false`) rather than an error

### Daemon & Governance

- **FR16:** The daemon runs all governance jobs on schedule without manual intervention: lint, contradiction detection, staleness detection, export generation, index rebuild
- **FR17:** The daemon generates structured governance reports readable via CLI
- **FR18:** Operators can view daemon job schedule, last-run results, and next-run times via MCP, REST, or CLI
- **FR19:** Operators can trigger an index rebuild manually via MCP, REST, or CLI
- **FR20:** The daemon flags a contradiction when a new claim directly negates a claim on an existing page — where "directly negates" means the same subject-predicate pair has conflicting object values — and routes conflicts to the review queue before committing to the wiki
- **FR21:** The daemon detects orphaned and stale pages and surfaces them in governance reports
- **FR22:** The daemon detects sources routed to the wrong domain and flags them for correction
- **FR23:** The daemon periodically scans pages for claims lacking a source citation or backlink, and flags them in the governance report

### Knowledge Management

- **FR24:** The system maintains an append-only changelog of all page mutations with diff tracking
- **FR25:** Operators can view and action items in the review queue: approve, reject, or defer via CLI
- **FR26:** The system applies deterministic merge strategies when new content overlaps existing pages; strategy is determined per-field by the domain's schema configuration in `domains.yaml`; fields without explicit configuration default to `union`
- **FR27:** Operators can manage domain configuration: add domains, set routing rules, define ingestion policies
- **FR28:** Pages and claims carry confidence scores; low-confidence content is visible and filterable in query results
- **FR29:** New candidate pages are gated through a promotion queue before being committed to the wiki
- **FR53:** When a source cannot be routed to any configured domain, it is held in a staging area with a routing-failed status and surfaced in governance reports for manual domain assignment
- **FR63:** The system logs all queries with their results and query depth; this log is the basis for synthesis cache population and can be queried by operators

### Export & Integration

- **FR30:** Operators can trigger and retrieve AI-consumable exports: `llms.txt`, `llms-full.txt`, JSON-LD graph
- **FR31:** Exports include freshness metadata (`generated_at`, `page_count`) so consumers can assess staleness
- **FR32:** Agent harnesses can connect via MCP over SSE/HTTP transport (host:port) or stdio transport (process spawn), with no adapter layer required for either
- **FR33:** The Claude Code integration can automatically capture session transcripts via hooks (SessionEnd, PreCompact) into the inbox
- **FR34:** Operators can install and uninstall Claude Code session capture hooks via CLI

### Service Operations

- **FR35:** The full service stack (MCP server + REST API + daemon) starts with a single `docker-compose up` command
- **FR36:** Operators can check service health (daemon status, index freshness) via MCP, REST, or CLI
- **FR37:** The service exposes an OpenAPI 3.1 spec at `/v1/openapi.json` for REST API autodiscovery
- **FR38:** MCP clients can autodiscover available tools via standard `tools/list`
- **FR39:** Operators can configure the service via host-mounted YAML files without rebuilding the container
- **FR40:** The daemon recovers from crashes automatically on restart: the scheduler resumes from its last checkpoint, in-progress ingest jobs resume from their saved position, and index integrity is verified before serving queries
- **FR41:** All index files are written atomically so a crash mid-write never leaves indexes in a partially-written state
- **FR55:** The service automatically initializes the wiki directory structure on first start if the mounted volume is empty, requiring no manual `init` command
- **FR60:** Operators and agents can retrieve the list of configured domains and their metadata (page count, last updated) at runtime via MCP, REST, or CLI
- **FR61:** `list_pages` supports an `updated_since` filter so agents can efficiently poll for changed pages without fetching the full page list

### Trust & Provenance (Sprint 2)

- **FR42:** Every wiki page claim is tagged as extracted, inferred, or ambiguous at ingest time
- **FR43:** Pages without valid source citations are automatically marked low-confidence and flagged in governance reports
- **FR44:** The system scores candidate pages against configurable confidence thresholds before promotion to the wiki

### Cross-Domain Synthesis (Sprint 3)

- **FR45:** The system maintains authority scores for pages and entities based on cross-domain reference density
- **FR46:** Shared entities are promoted to cross-domain status automatically when they appear in multiple domains and meet the configured confidence threshold
- **FR47:** The system auto-generates cross-domain summary pages for entities appearing in multiple domains, contingent on entity promotion (FR46) being operational
- **FR48:** The system caches high-value repeated query answers as first-class wiki pages, using query logs (FR63) to identify candidate queries
- **FR49:** Per-domain dashboards summarize domain health, page count, confidence distribution, and recent changes
- **FR50a:** The daemon automatically archives topics that exceed the staleness threshold configured in `domains.yaml`, preserving them for historical access but excluding them from normal query context
- **FR50b:** Operators can manually archive any topic via CLI regardless of staleness threshold
- **FR62:** Pages generated by the synthesis cache are tagged with `kind: synthesis` and include a `source_query` field, distinguishing them from primary source pages in all query and list results

## Non-Functional Requirements

### Performance

- **NFR-P1**: Quick-depth queries (BM25 fulltext index lookup) complete in ≤ 200 ms under normal load (single user, ≤ 1,000 pages).
- **NFR-P2**: Standard-depth queries (page content retrieval + RRF ranking) complete in ≤ 2 s under normal load.
- **NFR-P3**: Deep-depth queries return a response with `partial: true` and whatever synthesis is available within the 30 s timeout; they never hang the caller indefinitely.
- **NFR-P4**: Ingest throughput: daemon processes at least 10 inbox items per minute under sustained load.
- **NFR-P5**: Full index rebuild completes within 60 s for a wiki of up to 1,000 pages.

### Reliability

- **NFR-R1**: After a daemon crash and restart, the scheduler, ingest queue, and index integrity are all operational within 60 s — no manual intervention required.
- **NFR-R2**: All index file writes use the atomic `tmp → os.replace` pattern; a crash mid-write never leaves a partially-written index on disk.
- **NFR-R3**: Inbox items submitted before a daemon crash are preserved in the durable queue and processed on next start — zero item loss.
- **NFR-R4**: On startup, the daemon performs an index integrity check; if corruption is detected, it triggers an automatic rebuild before serving any queries.

### Integration

- **NFR-I1**: MCP tool names follow the `verb_noun` convention (e.g., `read_page`, `ingest_document`); all tools are discoverable via `tools/list` per MCP protocol with no adapter required.
- **NFR-I2**: REST API conforms to OpenAPI 3.1, published at `/v1/openapi.json`; breaking changes require a new URL path version (`/v2/`).
- **NFR-I3**: Every query and status CLI command supports a `--json` flag that emits machine-parseable JSON for scripting and harness integration.
- **NFR-I4**: MCP transport supports both SSE/HTTP (host:port) and stdio (process spawn); the harness selects transport per its connection config.

### Operability

- **NFR-O1**: `docker-compose up` brings the full stack to operational in ≤ 30 s on a cold start with a pre-warmed image.
- **NFR-O2**: The `/health` endpoint responds within 1 s and accurately reflects daemon liveness, index load status, and scheduler state.
- **NFR-O3**: Domain and daemon config changes (domains.yaml, daemon.yaml) take effect on daemon restart with no data loss.
- **NFR-O4**: On first run against an empty volume, the daemon auto-initializes the full `wiki_system/` directory structure without manual intervention.

### Data Integrity

- **NFR-D1**: Page IDs are deterministic slugs (`{domain}-{title-slug}`); identical `(domain, title)` inputs always produce the same ID across restarts and rebuilds.
- **NFR-D2**: `changelog.jsonl` is append-only; any code path that opens it for write (truncate) is a critical bug, caught by the integration test suite.
- **NFR-D3**: Merge strategy application is idempotent — ingesting the same source document twice produces no net change to the page content or index.

### Security

- **NFR-S1**: The service binds to `127.0.0.1` by default; external network exposure requires an explicit `bind_host` override in `daemon.yaml`.

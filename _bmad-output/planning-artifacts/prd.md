---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-06-innovation', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish']
releaseMode: phased
inputDocuments: ['docs/Product_Brief.md', 'docs/ARCHITECTURE.md', 'docs/ARCHITECTURE_REVIEW.md', 'docs/IMPLEMENTATION_STATUS.md', 'docs/roadmap.md', 'docs/bmad/PROJECT_STATUS.md', 'docs/bmad/ROADMAP_REMAINING.md', '_bmad-output/project-context.md']
workflowType: 'prd'
classification:
  projectType: api_backend
  interfaces: ['mcp', 'rest', 'cli']
  domain: ml_ai_tooling
  complexity: medium
  projectContext: brownfield
  deployment: docker_cloud_per_household
  auth: none
---

# Product Requirements Document — LLM Wiki

**Author:** Marc
**Date:** 2026-05-16

## Executive Summary

LLM Wiki is a self-maintaining, daemon-governed knowledge service for agentic AI systems. It runs as a Docker container and exposes MCP, REST, and CLI interfaces — making it as easy to integrate as a database. Any agent harness connects over MCP; initial targets include OpenClaw, Hermes-agent, Agent Zero, and Homefront (custom). Knowledge is authored, maintained, and governed automatically by a background daemon, not by humans.

**Stack positioning:** LLM Wiki is a structured knowledge store, not a memory system. It operates alongside session-memory systems like Honcho, not instead of them. Honcho manages session context and conversational continuity; LLM Wiki manages compiled, governed domain knowledge that compounds over time. An agent harness uses both simultaneously for different purposes.

The core shift from traditional RAG: knowledge is compiled once, maintained continuously, and queried with provenance. Agents receive pre-synthesized answers with confidence scores, source citations, and contradiction warnings instead of raw chunks. Every new source makes the wiki richer through cross-referencing, entity integration, and synthesis caching — knowledge compounds; it does not evaporate between sessions.

This is a brownfield expansion of a working V1 codebase. The pivot from importable Python library to standalone Docker service removes all embedding overhead — no language lock-in, no version conflicts, no harness-specific integration work. Each workspace runs its own isolated instance on a dedicated cloud VM alongside Homefront and Honcho. The service is auth-free (VM-level isolation is the security boundary), and plain-text on disk (Obsidian-compatible markdown); the knowledge is always yours and always readable without the service running.

### Homefront Integration — Workspace Facts

LLM-Wiki serves Homefront as a deterministic structured facts service and governed wiki knowledge service. This is a complementary layer to the existing page/wiki/search/query/export capability — facts and pages are distinct surfaces.

**Architecture roles:**
- **Homefront**: household operating runtime — policies, routines, context assembly, approvals, scheduling. Asks LLM-Wiki for facts and knowledge.
- **Honcho**: conversational/profile memory — sessions, messages, peer cards, conclusions. Asks/Lookups by Homefront for memory.
- **LLM-Wiki**: deterministic structured facts + governed wiki knowledge — exact facts with provenance, confidence, versioning, conflict/review; plus governed markdown pages with search and synthesis.

**Object model alignment:**
- `Workspace` = top-level isolated cell (replaces `household_id` in technical contracts, with `household.*` category aliases preserved for backward compatibility)
- `Peer` = person/assistant/support/system actor referenced in provenance
- `Session` = source interaction context (Honcho-owned)
- `Fact` = deterministic structured key/value knowledge item (LLM-Wiki-owned)
- `Page` = governed markdown/wiki artifact (LLM-Wiki-owned)
- `Domain` = organizational/search/routing label, NOT a security boundary

**Workspace Facts API:**

```
GET    /v1/workspaces/{workspace_id}/facts
GET    /v1/workspaces/{workspace_id}/facts/{fact_key}
PUT    /v1/workspaces/{workspace_id}/facts/{fact_key}
DELETE /v1/workspaces/{workspace_id}/facts/{fact_key}
GET    /v1/workspaces/{workspace_id}/facts/{fact_key}/history
POST   /v1/workspaces/{workspace_id}/facts:batch
```

**Fact schema (Python Pydantic):**

```python
class KnowledgeFact(BaseModel):
    id: UUID
    workspace_id: str
    category: str
    key: str
    value: dict[str, Any]
    source: KnowledgeSource
    provenance: list[ProvenanceRef] = []
    confidence: float | None = None
    authority_score: float | None = None
    status: Literal["active", "pending_review", "conflicted", "archived", "deleted"]
    visibility: Literal["workspace", "adults_only", "profile_private", "support_redacted", "system_internal"] = "workspace"
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    created_at: datetime
    updated_at: datetime
    version: int
```

**Category registry (canonical `workspace.*` with legacy `household.*` aliases):**

| Canonical | Legacy Alias |
|-----------|-------------|
| workspace.roster | household.roster |
| workspace.assignments | household.assignments |
| workspace.pets | household.pets |
| workspace.appliances | household.appliances |
| workspace.preferences | household.preferences |
| workspace.schedule | household.schedule |
| workspace.vehicles | household.vehicles |
| workspace.presence | household.presence |
| workspace.recurring_responsibilities | household.recurring_responsibilities |

**Storage model:** Facts stored as machine-readable files alongside wiki pages, not in a database:

```
wiki_system/
  workspaces/
    {workspace_id}/
      facts/
        index.json
        categories/
          workspace.pets.jsonl
          workspace.schedule.jsonl
        history/
          {fact_key_hash}.jsonl
      pages/          (existing wiki pages, workspace-scoped)
      inbox/
      exports/
```

Rules:
- Current fact state is machine-readable without markdown parsing
- Fact history is append-only
- Writes use temp file + `os.replace` (atomic)
- Per-workspace/per-fact locks prevent concurrent write races
- Pages may reference facts but are not the canonical fact state

LLM-assisted extraction is optional and off by default — the system runs fully on heuristics and sentence-transformers with no LLM dependency. Enable `llm_extraction: true` in `daemon.yaml` to unlock richer tag extraction, claim confidence scoring, and LLM-quality summaries. Provider config (Anthropic, OpenAI, OpenRouter, or local vLLM/Llama) lives in `models.yaml`.

### What Makes This Special

No other project in the LLM Wiki ecosystem combines all of:

- **MCP-native service** — connects to any agent harness without per-harness adapters
- **Algorithmic governance daemon** — Auditor, Librarian, Compliance, and Adversary maintenance jobs run on schedule; no LLM runs inside the system
- **Provenance transparency** — every claim tagged as extracted, inferred, or ambiguous; contradictions flagged before they corrupt downstream reasoning
- **Synthesis cache** — high-value query answers become first-class wiki pages, compounding value over time
- **Graph intelligence** — community detection, authority scoring, and cross-domain cross-referencing surface unexpected connections automatically
- **Three-depth query model** — quick (index), standard (pages), deep (full synthesis with 30s timeout)
- **AI-consumable exports** — `llms.txt`, JSON-LD, per-page sidecar files so other agents can query the wiki directly

The competitive moat is completeness: every peer project has one or two of these. LLM Wiki has all of them in a single local service.

## Project Classification

- **Type:** API backend service (MCP + REST + CLI)
- **Domain:** ML/AI tooling — knowledge graph, algorithmic governance, daemon orchestration
- **Complexity:** Medium
- **Context:** Brownfield — V1 Python library exists as foundation; no legacy compatibility constraints
- **Deployment:** Docker, cloud per-household (dedicated VM), no auth (VM-level isolation), plain-text data files

## Success Criteria

### User Success

- A developer goes from `docker pull` to a working MCP connection in under 15 minutes, with no Python environment setup required
- Agent harnesses (OpenClaw, Hermes-agent, Agent Zero, Homefront) query LLM Wiki over MCP and receive pre-synthesized answers with provenance — not raw chunks
- The daemon runs unattended; governance issues surface as structured reports, not silent failures
- Marc (primary user) reaches for LLM Wiki before asking his harness to read files directly — because the answer is already there, already cross-referenced, already validated
- Honcho and LLM Wiki coexist in the same harness session without friction; the boundary between "session memory" and "compiled knowledge" is clear to both agent and operator

### Business Success

- **Office Pilot (~2-3 days per phase):** Docker service live with MCP + REST + CLI, daemon running V1 jobs, Homefront connected and querying, workspace facts API core operational
- **Family Production Rollout (~2-3 days per phase):** Trust layer complete, cross-domain intelligence, full confidence/citation pipeline, workspace facts with conflict/review, Homefront context snapshot assembler ready
- **Sprint 4+ (when ready):** V4 web UI + graph, V5 online integrations

### Technical Success

- MCP query response: ≤ 2 s for standard-depth queries on a local machine
- Daemon stability: all job outcomes logged and queryable via CLI; no silent failures
- Docker image: single `docker-compose up` starts the full stack (daemon + MCP server + REST API)
- Plain-text integrity: all wiki data readable without the service running (Obsidian-compatible markdown)
- Test coverage: ≥ 90% on core pipeline (ingest → integrate → query → govern)
- Zero data loss: daemon crashes do not corrupt the wiki; recovery is automatic on restart

### Measurable Outcomes

- Inbox → wiki page pipeline completes without manual intervention for all supported source types
- Contradiction detection flags conflicts before they enter the wiki (not after)
- Synthesis cache hit rate grows over time — repeat query patterns produce instant answers
- Graph cross-references increase per new source ingested (compounding signal)

## Product Scope

### Office Pilot Foundation — Service Pivot (Sprint 1)

The minimum that makes LLM Wiki useful as a service rather than a library:

- Docker container: MCP server + REST API + CLI all exposed
- Daemon running all V1 governance jobs (lint, contradiction detection, staleness, export, index rebuild)
- MCP tool surface: `query` (three depths), `ingest`, `ingest_status`, `search`, `read_page`, `list_pages`, `export`
- REST API mirroring MCP surface
- Workspace Facts API: CRUD endpoints under `/v1/workspaces/{workspace_id}/facts`
- `docker-compose.yml` + host-mounted volume for wiki data (includes facts storage layout)
- Health check endpoint; structured daemon logs queryable via CLI

### Growth Features — V2 through V4 (Family Production Rollout Phase)

Built on the service foundation and Office Pilot validation, in delivery order:

- **V2 Trust Layer:** Confidence scoring, citation enforcement, hallucination guard, truth-seeking audits, orphan/stale detection
- **V2 Cross-cutting:** Vector/semantic search, AI-consumable exports (`llms.txt`, JSON-LD), multi-agent session coverage (Gemini CLI, Ollama)
- **V3 Cross-Domain Synthesis:** Entity promotion, cross-domain summary pages, per-domain dashboards, authority scoring, topic archive lifecycle, synthesis cache
- **V4 UX Layer:** Web UI (search + browse + editor), graph visualization, community detection, daemon control panel, richer exports

### Vision — V5 and Beyond

- Online integrations: GitHub repo ingestion, docs site crawling, RSS feeds, arXiv monitor, plugin architecture for custom sources
- Optional encrypted cloud sync (local-first preserved; sync is additive)
- LLM Wiki as a recognized standard for LLM-readable knowledge infrastructure — `llms.txt` and JSON-LD exports adopted by other tools in the ecosystem

## User Journeys

### Journey 1 — Marc (Primary): First Query That Replaces a File Read

Marc is building a Homefront session. His agent needs context about his homelab network. Old way: the agent reads through a directory of markdown files, guessing what's relevant. New way: the agent calls LLM Wiki's MCP `query` tool with "homelab network topology" — it gets back a pre-synthesized page with provenance, cross-references to related pages, and a contradiction flag on one claim that hasn't been resolved yet. The agent didn't do the work. The wiki already did. Marc notices he hasn't opened those raw files in three days.

### Journey 2 — Developer Integration: Zero to MCP in One Session

A developer building on Hermes-agent wants persistent knowledge. They clone, run `docker-compose up`, point their MCP config at `{host}:{port}` (default `localhost:3050`), and make their first query. No Python setup, no virtualenv, no dependency hell. They drop a markdown doc in the inbox via REST, watch the daemon process it, and query it back over MCP five minutes later. The "aha" is that it just works — like adding a database.

### Journey 3 — Daemon Operator: Contradiction Surfaces Automatically

Marc ingests a new Claude Code session transcript overnight. The next morning, he checks the daemon report via CLI (`llm-wiki daemon status`). The Auditor flagged a contradiction: a new claim about a config value conflicts with an existing page. The wiki didn't silently pick one — it flagged it, cited both sources, and put it in the review queue. Marc resolves it in 30 seconds. Without governance, this would have been a silent corruption.

### Journey 4 — Recovery: Daemon Crash, Zero Data Loss

The daemon crashes mid-ingest during a large batch. Marc restarts it with `docker-compose restart`. The daemon reads its checkpoint state, skips already-processed sources, and resumes from where it stopped. The wiki files are plain markdown and were never in an inconsistent state — the crash only affected the in-progress extraction, not committed pages.

### Journey Requirements Summary

| Journey | Capabilities Required |
|---------|----------------------|
| First query replaces file read | MCP query tool (3 depths), cross-reference traversal, contradiction surfacing in results |
| Zero to MCP | Docker image, `docker-compose.yml`, REST ingest endpoint, MCP server, daemon auto-start |
| Contradiction surfaces | Daemon auditor job, structured reports, CLI status command, review queue |
| Crash recovery | Checkpoint/resume, atomic page writes, daemon restart logic |

## Domain-Specific Requirements

### Technical Constraints

- **Deterministic core:** All governance jobs are algorithmic — contradiction detection, index updates, staleness, routing. These never require an LLM.
- **Optional LLM extraction:** Tag extraction, summarization, and claim extraction can run with or without an LLM. Controlled by `llm_extraction` feature flag in `daemon.yaml`. When disabled, heuristics and sentence-transformers handle all processing. When enabled, LLM provider config (Anthropic, OpenAI, OpenRouter, or local vLLM/Llama) is read from `models.yaml`.
- **Model-agnostic queries:** The service has no model dependency for queries. Any agent using any LLM can query it — the wiki doesn't care what's on the other end of the MCP connection.
- **Cloud per-household:** Each household runs on a dedicated VM. No external API calls required for core operation when `llm_extraction: false`.
- **Docker volume mounts:** Wiki data lives on a host-mounted volume; no data inside the image. Config via mounted YAML files.

### Feature Flags

Controlled via `daemon.yaml` `features:` block:

| Flag | Default | Description |
|------|---------|-------------|
| `llm_extraction` | `false` | LLM-assisted tag/summary/claim extraction |
| `synthesis_cache` | `false` | Cache repeated query answers as wiki pages (Sprint 3) |
| `cross_domain_promotion` | `false` | Auto-promote shared entities across domains (Sprint 3) |

FR42–44 (claim trust tagging, citation enforcement, confidence gating) require `llm_extraction: true`. The heuristic path provides citation-presence-based confidence scoring without an LLM.

### Integration Requirements

- MCP protocol compliance: standard tool definitions, proper error responses, well-typed inputs/outputs
- REST API: JSON, predictable HTTP status codes, mirrors MCP tool surface
- Docker: single `docker-compose up` start, host-mounted volume for wiki data, no secrets baked into image

### Domain Risks and Mitigations

- **Knowledge drift:** Pages diverge from source truth as conflicting sources arrive → contradiction detection + human review queue
- **Index/wiki desync:** Search index drifts from wiki files after crashes → atomic page writes + scheduled index rebuild job
- **Routing mistakes:** Sources land in wrong domain → routing mistake detection governance job (V1)

## Innovation & Novel Patterns

### Detected Innovation Areas

1. **Algorithmic knowledge service, not RAG** — The wiki is pre-compiled and governed by a deterministic daemon. Query results are pre-synthesized with provenance, not assembled at query time from raw chunks. This is Karpathy's compounding wiki insight operationalized as a production service — no LLM runs inside the system; it serves LLMs.

2. **MCP-native knowledge store** — Most MCP tools are thin wrappers around APIs or file systems. LLM Wiki exposes a governed knowledge graph over MCP — with confidence scores, contradiction awareness, and synthesis depth — purpose-built for how agents actually reason across sessions.

3. **Completeness as moat** — The competitive landscape has partial implementations: nashsu has graph intelligence but is a desktop app; lucasastorian has MCP but no governance; Labhund has multi-agent maintenance but no service layer. LLM Wiki is the only project combining all of them in a single local Docker service.

### Market Context

No peer project combines: daemon governance + domain federation + MCP server + REST API + CLI + algorithmic contradiction detection + synthesis cache + provenance tracking + graph intelligence in a single deployable service. Each peer implements 1-3 of these; LLM Wiki implements all of them.

### Validation Approach

- **Primary signal:** Marc stops reading raw files and reaches for the wiki first — organic adoption by the primary user
- **Secondary signal:** A second developer connects a harness in under 15 minutes with no guidance beyond the README
- **Tertiary signal:** Synthesis cache hit rate grows week-over-week — knowledge is compounding, not stagnating

### Risk Mitigation

- If MCP adoption stalls: REST API ensures full functionality without MCP; CLI covers all local operations
- If algorithmic extraction misses nuance: human review queue catches errors before they compound; source files always intact for re-processing

## API Backend Specific Requirements

### Interface Architecture

LLM Wiki exposes three complementary surfaces over the same underlying service layer. All three share identical capabilities — no surface is privileged over another.

| Surface | Transport | Primary Audience |
|---------|-----------|-----------------|
| MCP | Streamable HTTP or stdio | Agent harnesses |
| REST | HTTP/JSON | Programmatic integration, non-MCP clients |
| CLI | subprocess | Local testing, operator control, scripting |

### Endpoint Specification

**MCP Tool Surface** — verb-noun naming convention throughout

| Tool | Description |
|------|-------------|
| `query` | Retrieve synthesized knowledge; `depth`: `quick` (index only), `standard` (page content), `deep` (async — returns `job_id`; poll `ingest_status` equivalent; 30s timeout, returns `partial: true` on timeout) |
| `ingest` | Submit a source for daemon processing; returns `job_id` |
| `ingest_status` | Poll ingest job by `job_id`; returns `status`, `domain`, `page_ids` on completion |
| `search` | Full-text + vector search across all domains; ranked results with confidence scores |
| `read_page` | Fetch a single wiki page by ID or slug; includes frontmatter provenance metadata |
| `list_pages` | List pages by domain, kind, or tag; cursor-based pagination |
| `export` | Trigger or retrieve exports (`llms_txt`, `llms_full_txt`, `json_ld`, `graph`); includes `generated_at` and `page_count` |
| `fact_get` | Get a single fact by key in a workspace |
| `fact_list` | List facts in a workspace with category filter |
| `fact_put` | Create or update a fact in a workspace |
| `fact_delete` | Delete a fact |
| `fact_history` | Get fact version history |
| `fact_batch_put` | Batch create/update facts |

**REST API**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/health` | Service health; daemon status, index freshness |
| `GET` | `/v1/daemon/status` | Job schedule, last-run results, next-run times |
| `GET` | `/v1/daemon/jobs` | Job execution history from `state/jobs.json` |
| `POST` | `/v1/daemon/jobs/index-rebuild` | Trigger index rebuild (referenced in `INDEX_STALE` errors) |
| `POST` | `/v1/query` | Submit query; quick/standard return results synchronously; deep returns `job_id` |
| `GET` | `/v1/query/{job_id}` | Poll deep query job status; returns result when complete |
| `POST` | `/v1/ingest` | Submit source for processing; returns `job_id` |
| `GET` | `/v1/ingest/{job_id}` | Poll ingest job status |
| `GET` | `/v1/search` | Full-text + vector search |
| `GET` | `/v1/pages/{page_id}` | Single page read |
| `GET` | `/v1/pages` | Page list; cursor pagination: `?cursor=<token>&limit=50` |
| `POST` | `/v1/export` | Trigger export generation |
| `GET` | `/v1/export/{format}` | Retrieve export; `Last-Modified` header included |
| `GET` | `/v1/domains/{domain}/dashboard` | Per-domain health summary: page count, confidence distribution, staleness, contradictions (Epic 3) |

**Workspace Facts API**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/workspaces/{workspace_id}/facts` | List facts for workspace with category filter |
| `GET` | `/v1/workspaces/{workspace_id}/facts/{fact_key}` | Get single fact by key |
| `PUT` | `/v1/workspaces/{workspace_id}/facts/{fact_key}` | Create or update fact |
| `DELETE` | `/v1/workspaces/{workspace_id}/facts/{fact_key}` | Delete fact |
| `GET` | `/v1/workspaces/{workspace_id}/facts/{fact_key}/history` | Get fact version history |
| `POST` | `/v1/workspaces/{workspace_id}/facts:batch` | Batch create/update facts |

**Workspace-Scoped Knowledge API**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/workspaces/{workspace_id}/knowledge/inbox` | Submit source for workspace |
| `POST` | `/v1/workspaces/{workspace_id}/knowledge/search` | Search within workspace |
| `POST` | `/v1/workspaces/{workspace_id}/knowledge/query` | Query within workspace |
| `GET` | `/v1/workspaces/{workspace_id}/knowledge/pages/{page_id}` | Read page in workspace scope |
| `GET` | `/v1/workspaces/{workspace_id}/knowledge/review` | Review queue for workspace |
| `GET` | `/v1/workspaces/{workspace_id}/knowledge/conflicts` | Fact conflicts for workspace |
| `GET` | `/v1/workspaces/{workspace_id}/knowledge/stale` | Stale content for workspace |
| `POST` | `/v1/workspaces/{workspace_id}/knowledge/export` | Export for workspace |

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
- `v1` covers the service pivot Office Pilot through V3 features
- Breaking changes require a major version bump; non-breaking additions (new optional fields, new endpoints) do not
- MCP tool names are stable within a major version; deprecation window is one major version
- `X-LLM-Wiki-Version` response header on all REST responses

### Data Schemas

**Query Response**

```json
{
  "query": "string",
  "depth": "quick|standard|deep",
  "partial": false,
  "timed_out": false,
  "results": [
    {
      "page_id": "string",
      "title": "string",
      "domain": "string",
      "kind": "entity|concept|source|qa|synthesis",
      "confidence": 0.0,
      "excerpt": "string",
      "provenance": ["source_id"],
      "contradictions": [
        { "claim": "string", "conflicting_page_id": "string" }
      ],
      "cross_references": ["page_id"]
    }
  ],
  "synthesis": "string | null",
  "vector_search": true,  // always enabled — FAISS + sentence-transformers are core deps
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
  "indexed": "ISO8601 | null",
  "message": "string"
}
```

**Page**

```json
{
  "page_id": "string",
  "title": "string",
  "domain": "string",
  "kind": "entity|concept|source|qa|synthesis",
  "confidence": 0.0,
  "sources": ["string"],
  "tags": ["string"],
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "content": "string (markdown)",
  "contradictions": [],
  "backlinks": ["page_id"],
  "source_query": "string | null"
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
  "format": "llms_txt|llms_full_txt|json_ld|graph",
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
| `UNKNOWN_FACT_CATEGORY` | MCP, REST, CLI | Specified fact category not in the category registry |
REST: HTTP status codes + JSON body with `error_code`, `message`, and optional `rebuild_hint`. MCP: JSON-RPC error objects. CLI: exit code 1, error on stderr.

**Note:** Deep query timeout is a *normal response variant*, not an error. A deep query that exceeds 30s returns HTTP 200 with `{"partial": true, "timed_out": true, "results": [...]}` — it does not return an error code. `QUERY_TIMEOUT` is therefore absent from the error table; it does not appear in `ERROR_MAP` and does not trigger an HTTP 4xx/5xx.

### API Documentation

- OpenAPI 3.1 spec served at `/v1/openapi.json` and `/v1/docs` in development mode
- MCP: standard `tools/list` autodiscovery
- CLI: `--help` per command; `docs/CLI.md` in repo

## Project Scoping & Phased Development

### Office Pilot Strategy & Philosophy

**Office Pilot Approach:** Platform foundation — establish the service and facts API foundation so every subsequent sprint builds on a running, connectable system. The minimum is a Docker container that any agent harness can reach over MCP within 15 minutes of `docker-compose up`, plus workspace facts CRUD.

**Resource Requirements:** Solo developer (Marc); ~2-3 days per sprint; all tooling already in place (uv, pytest, ruff, mypy, CI).

### Sprint 1 — Service Pivot (Office Pilot)

**Core User Journeys Supported:** Zero-to-MCP integration; crash recovery.

**Must-Have Capabilities:**
- Docker container with MCP server + REST API + CLI all exposed
- Daemon running all V1 governance jobs (lint, contradiction detection, staleness, export, index rebuild)
- MCP tool surface: `query` (three depths), `ingest`, `ingest_status`, `search`, `read_page`, `list_pages`, `export`
- REST API mirroring MCP surface + `/v1/health`, `/v1/daemon/status`, `/v1/daemon/jobs`, `/v1/daemon/jobs/index-rebuild`
- Workspace Facts API: CRUD endpoints under `/v1/workspaces/{workspace_id}/facts` with atomic writes
- Workspace-Scoped Knowledge API endpoints
- `docker-compose.yml` + host-mounted volume for wiki data (includes facts storage layout)
- Health check endpoint; structured daemon logs queryable via CLI
- Checkpoint/resume for daemon crash recovery; atomic page writes

### Sprint 2 — V2 Trust Layer + Cross-Cutting

**Core User Journeys Supported:** Contradiction surfaces automatically; all four journeys fully supported; trust pipeline operational for both facts and pages.

**Must-Have Capabilities:**
- Confidence scoring on pages and claims; visible in query results
- Source citation enforcement — pages without valid source refs marked low-confidence
- Hallucination guard: candidate pages gated through promotion queue
- Truth-seeking audit daemon job
- Orphan and stale content detection
- Vector/semantic search alongside BM25 (FAISS + sentence-transformers already in V1; wire into service layer)
- AI-consumable exports: `llms.txt`, `llms-full.txt` via CLI
- Multi-agent session coverage: additional capture hook adapters (e.g. Gemini CLI, Ollama) — scope to be confirmed during Sprint 2 planning; not currently tracked in epics or FRs

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

**Scope Risks:** V1 codebase has known P0 issues (no index write mutex, orphaned inbox files on crash). These are documented and bounded — daemon's `max_workers=2` cap prevents the worst races. Do not raise the worker limit until the mutex lands in Sprint 1 (Story 1.1).

**Resource Risks:** Solo developer means Sprint 1 must be truly minimal — any scope creep delays the MCP connection that makes all subsequent sprints testable. If Sprint 1 overruns, drop REST API to Sprint 2 (MCP + CLI alone satisfies the MVP contract).

## Functional Requirements

### Knowledge Ingestion

- **FR1:** The daemon routes sources dropped into the inbox to domains using rules defined in `routing.yaml`; sources matching no rule are held in staging (see FR53)
- **FR2:** Operators can submit sources for ingestion via MCP, REST, or CLI and receive a job ID
- **FR3:** The system ingests Claude Code session transcripts (JSONL format) and normalizes them to markdown wiki pages
- **FR4:** The system ingests plain markdown documents as sources
- **FR5:** Operators can poll the status of any ingest job by job ID across all three interfaces
- **FR6:** The system extracts QA pairs from session transcripts as first-class `kind: qa` wiki pages
- **FR7:** The daemon resumes interrupted ingest batches from a checkpoint without reprocessing already-completed sources
- **FR51:** The system accepts and durably queues ingest submissions when the daemon is not running, and processes the queue automatically when the daemon next starts
- **FR58:** Ingest job status `complete` means the resulting pages are committed to the wiki and searchable; an `indexed` timestamp field indicates when the index reflects the new pages

### Knowledge Query & Retrieval

- **FR8:** Agent harnesses can query the wiki at three depths: quick (index lookup, synchronous), standard (page content, synchronous), deep (synthesis with cross-references, async — returns `job_id` immediately; client polls for result)
- **FR9:** Deep queries return partial results with an explicit `partial: true` flag when synthesis exceeds the timeout threshold
- **FR10:** Query results include confidence scores, source provenance citations, and contradiction warnings; contradiction warnings include both conflicting claim summaries and the page IDs of conflicting sources
- **FR11:** Operators and agents can read any single wiki page by page ID or slug, including full frontmatter provenance metadata
- **FR12:** Operators and agents can list pages filtered by domain, page kind, or tag with cursor-based pagination
- **FR54:** Deep queries that exceed the timeout threshold before producing any results return a response with `"timed_out": true` alongside `"results": []`, distinguishable from a legitimate empty result set
- **FR57:** Contradiction warnings in query results include structured claim summaries and the page IDs of the conflicting sources, so an agent can surface them without additional lookups
- **FR59:** Agents can query across all domains simultaneously in a single call (default); an optional `domain` parameter restricts the query to a specific domain

### Search

- **FR13:** Agent harnesses and operators perform full-text search across all domains, returning ranked results with confidence scores
- **FR14:** Agent harnesses and operators perform semantic/vector search, returning similarity-ranked results
- **FR15:** Search results from fulltext and vector indexes are merged into a single ranked list
- **FR52:** Vector search is always enabled (FAISS + sentence-transformers are core dependencies). Search always returns `"vector_search": true`. Note: response field retained for protocol compatibility but always derives `true`.

### Daemon & Governance

- **FR16:** The daemon runs all governance jobs on schedule without manual intervention: lint, contradiction detection, staleness detection, export generation, index rebuild
- **FR17:** The daemon generates structured governance reports readable via CLI
- **FR18:** Operators can view daemon job schedule, last-run results, and next-run times via MCP, REST, or CLI
- **FR19:** Operators can trigger an index rebuild manually via MCP, REST, or CLI
- **FR20:** The daemon flags a contradiction when a new claim directly conflicts with a claim on an existing page — where "directly conflicts" means two pages assert incompatible values for the same subject — and routes conflicts to the review queue before committing to the wiki
- **FR21:** The daemon detects orphaned and stale pages and surfaces them in governance reports
- **FR22:** The daemon detects sources routed to the wrong domain and flags them for correction
- **FR23:** The daemon periodically scans pages for claims lacking a source citation or backlink and flags them in the governance report

### Knowledge Management

- **FR24:** The system maintains an append-only changelog of all page mutations with diff tracking
- **FR25:** Operators can view and action items in the review queue: approve, reject, or defer via CLI
- **FR26:** The system applies deterministic merge strategies when new content overlaps existing pages; strategy is determined per-field by the domain's schema configuration in `domains.yaml`; fields without explicit configuration use the default merge behavior
- **FR27:** Operators can manage domain configuration: add domains, set routing rules, define ingestion policies
- **FR28:** Pages carry confidence scores computed from a configurable weighted model (inputs: citation presence, trust tag when available, source count, page age, backlink count); weights are configurable per-domain in `domains.yaml`; low-confidence content is visible and filterable in query results
- **FR29:** New candidate pages are gated through a promotion queue before being committed to the wiki
- **FR53:** When a source cannot be routed to any configured domain, it is held in a staging area with a routing-failed status and surfaced in governance reports for manual domain assignment
- **FR63:** The system logs all queries with their results and query depth; this log is the basis for synthesis cache population and can be queried by operators

### Export & Integration

- **FR30:** Operators can trigger and retrieve AI-consumable exports: `llms.txt`, `llms-full.txt`, JSON-LD graph
- **FR31:** Exports include freshness metadata (`generated_at`, `page_count`) so consumers can assess staleness
- **FR32:** Agent harnesses connect via MCP over Streamable HTTP transport (`/mcp` endpoint) or stdio transport (process spawn), with no adapter layer required for either
- **FR33:** The Claude Code integration automatically captures session transcripts via hooks (SessionEnd, PreCompact) into the inbox
- **FR34:** Operators can install and uninstall Claude Code session capture hooks via CLI

### Service Operations

- **FR35:** The full service stack (MCP server + REST API + daemon) starts with a single `docker-compose up` command
- **FR36:** Operators can check service health (daemon status, index freshness) via MCP, REST, or CLI
- **FR37:** The service exposes an OpenAPI 3.1 spec at `/v1/openapi.json` for REST API autodiscovery
- **FR38:** MCP clients autodiscover available tools via standard `tools/list`
- **FR39:** Operators configure the service via host-mounted YAML files without rebuilding the container
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
- **FR48:** The system caches high-value repeated query answers as first-class wiki pages, using query logs (FR63) to identify candidates; "high-value" is defined as the same normalized query appearing at least `synthesis_cache_min_hits` times (configurable in `daemon.yaml`, default: 5) within a rolling 30-day window; requires `synthesis_cache: true` feature flag
- **FR49:** Per-domain dashboards summarize domain health, page count, confidence distribution, and recent changes
- **FR50a:** The daemon automatically archives topics that exceed the staleness threshold configured in `domains.yaml`, preserving them for historical access but excluding them from normal query context
- **FR50b:** Operators can manually archive any topic via CLI regardless of staleness threshold
- **FR62:** Pages generated by the synthesis cache are tagged with `kind: synthesis` and include a `source_query` field, distinguishing them from primary source pages in all query and list results

## Non-Functional Requirements

### Performance

- **NFR-P1:** Quick-depth queries (index lookup) complete in ≤ 200 ms under normal load (single user, ≤ 1,000 pages)
- **NFR-P2:** Standard-depth queries (page content retrieval + ranking) complete in ≤ 2 s under normal load
- **NFR-P3:** Deep-depth queries return a response with `partial: true` and whatever synthesis is available within the 30 s timeout; they never hang the caller indefinitely
- **NFR-P4:** Ingest throughput: daemon processes at least 10 inbox items per minute under sustained load
- **NFR-P5:** Full index rebuild completes within 60 s for a wiki of up to 1,000 pages

### Reliability

- **NFR-R1:** After a daemon crash and restart, the scheduler, ingest queue, and index integrity are all operational within 60 s — no manual intervention required
- **NFR-R2:** All index file writes are crash-safe atomic operations; a crash mid-write never leaves a partially-written index on disk
- **NFR-R3:** Inbox items submitted before a daemon crash are preserved in the durable queue and processed on next start — zero item loss
- **NFR-R4:** On startup, the daemon performs an index integrity check; if corruption is detected, it triggers an automatic rebuild before serving any queries

### Integration

- **NFR-I1:** MCP tool names follow the `verb_noun` convention (e.g., `read_page`, `ingest_document`); all tools are discoverable via `tools/list` per MCP protocol with no adapter required
- **NFR-I2:** REST API conforms to OpenAPI 3.1, published at `/v1/openapi.json`; breaking changes require a new URL path version (`/v2/`)
- **NFR-I3:** Every query and status CLI command supports a `--json` flag that emits machine-parseable JSON for scripting and harness integration
- **NFR-I4:** MCP transport supports both Streamable HTTP (`/mcp` endpoint) and stdio (process spawn); the harness selects transport per its connection config

### Operability

- **NFR-O1:** `docker-compose up` brings the full stack to operational in ≤ 30 s on a cold start with a pre-warmed image
- **NFR-O2:** The `/health` endpoint responds within 1 s and accurately reflects daemon liveness, index load status, and scheduler state
- **NFR-O3:** Domain and daemon config changes (domains.yaml, daemon.yaml) take effect on daemon restart with no data loss
- **NFR-O4:** On first run against an empty volume, the daemon auto-initializes the full `wiki_system/` directory structure without manual intervention

### Data Integrity

- **NFR-D1:** Page IDs are deterministic slugs (`{domain}-{title-slug}`); identical `(domain, title)` inputs always produce the same ID across restarts and rebuilds
- **NFR-D2:** `changelog.jsonl` is append-only; any code path that opens it for write (truncate) is a critical bug
- **NFR-D3:** Merge strategy application is idempotent — ingesting the same source document twice produces no net change to the page content or index

### Security

- **NFR-S1:** The service binds to `0.0.0.0` inside the container; port exposure is controlled by `docker-compose.yml` port mapping. Each workspace runs on a dedicated VM — VM-level isolation is the security boundary. No in-service auth is required.
- **NFR-S2:** Domain is a categorization/routing label, NOT a security boundary. workspace_id is the isolation object. Personal domains cannot leak across workspace boundaries via workspace-scoped API endpoints.

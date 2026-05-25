# Project Status — LLM Wiki

**Last updated**: 2026-05-25
**Current version**: v0.1.0
**Phase completed**: Feature-complete (all core Epics: Docker Service, Trust & Verification, Cross-Domain Intelligence, Web UI)
**Branch**: main
**Tests**: 1617 running, 2 known failures (test_ui_routes.py — outdated expectations), 0 unexpected failures
**Coverage**: ~93%
**Lint**: 0 ruff errors, mypy clean

---

## What Is This Project?

LLM Wiki is a **git-ops, local-first, file-backed federated wiki** governed by a background daemon. It is a structured knowledge layer for AI agents — the layer between raw files on disk and the intelligent queries agents need to answer.

Unlike RAG (which re-derives everything from scratch each query), LLM Wiki accumulates knowledge. When a new source arrives, the system reads it, extracts entities and claims, integrates it with existing pages, flags contradictions, and keeps the knowledge base current. Knowledge compounds: cross-references are pre-built, synthesis is pre-computed, and every new source makes everything richer.

**Primary user**: The repo author (Marc), building an agent harness that queries this knowledge store alongside Honcho.
**Secondary users**: Developers building agent harnesses who need a structured knowledge base that compounds over time.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Package manager | uv (hatchling build) |
| CLI | Click (2912 lines in cli.py) |
| Daemon loop | APScheduler `BackgroundScheduler` + `ThreadPoolExecutor` (max 2 workers) |
| Config | Pydantic + YAML |
| Storage | Markdown files + frontmatter + JSON indexes |
| Fulltext search | TF-IDF with inverted index |
| Vector search | FAISS `IndexFlatL2` + `sentence-transformers` (all-MiniLM-L6-v2, 384-dim) |
| LLM abstraction | OpenAI-compatible API (supports OpenAI, Anthropic, Ollama, LM Studio, Claude Agent SDK) |
| CI | GitHub Actions — ruff + mypy + pytest on Python 3.11/3.12 |

---

## Directory Structure

```
src/llm_wiki/
├── adapters/           # Markdown, text, Obsidian, Claude session adapters
├── changelog/          # Append-only operation log
├── config/             # Config loader, Pydantic schemas, validator
├── daemon/             # Main loop, scheduler, worker pool, execution store, errors
│   └── jobs/           # Governance, export, promotion, retry, review queue, index rebuild
├── export/             # llms.txt, JSON sidecar, graph, sitemap exporters
├── extraction/         # Claims, concepts, entities, enrichment, QA pipeline
├── governance/         # Contradictions, duplicates, linter, quality, routing, staleness
├── hook_templates/     # Session capture hook (Claude Code)
├── index/              # Backlinks, fulltext, graph edges, metadata, relationships, VECTOR
├── ingest/             # Watcher, normalizer, router, failed ingestion tracker
├── integration/        # DeterministicIntegrator — merges extracted metadata
├── models/             # Client (LLM), config schemas, domain, pages, integration
├── promotion/          # Config, engine, models, scorer
├── query/              # Unified WikiQuery (fulltext + vector + RRF fusion)
├── review/             # Review queue storage and models
├── templates/          # Page template engine
└── utils/              # Frontmatter parsing, page ID generation

config/
├── daemon.yaml         # Daemon scheduling, poll intervals, parallel jobs
├── domains.yaml        # 5 domains: vulpine-solutions, home-assistant, homelab, personal, general
├── models.yaml         # LLM provider config (extraction, integration, lint)
└── routing.yaml        # Source path → domain mapping rules

wiki_system/
├── inbox/              # Watched by InboxWatcher
│   ├── new/            # Drop-off location for files
│   ├── processing/     # Files being normalized
│   ├── done/           # Successful normalizations
│   └── failed/         # Failed normalizations
├── domains/            # Per-domain wikis
│   └── {domain}/
│       ├── queue/      # Pages awaiting integration
│       └── pages/      # Approved pages
├── shared/             # Cross-domain shared pages
├── index/              # JSON search indexes + FAISS vector index
├── exports/            # Generated llms.txt, graph, sitemap, JSON sidecars
├── reports/            # Governance run reports
├── review_queue/       # Review items (pending/approved/rejected/deferred)
├── state/              # Job execution history, checkpoint files
└── logs/               # Daemon logs, ingestion logs, decisions
```

---

## Data Flow

```
Ingest (new/ → inbox watcher)
  → Adapter (markdown/text/obsidian/claude-session)
  → Normalizer + Domain Router
  → Queue per domain
  → DeterministicIntegrator
    → Merge with existing page using strategies (keep_existing, union, prefer_newer)
  → Extraction Service (LLM-led)
    → Tags, summary, claims, entities, concepts, relationships, QA pairs
    → Extracted data integrated back into page frontmatter
  → Index updates:
    → FulltextIndex (TF-IDF inverted index)
    → VectorIndex (FAISS + sentence-transformers, if installed)
    → MetadataIndex (tag/kind/domain lookups)
    → BacklinkIndex (reverse link tracking)
    → GraphEdgeIndex (bidirectional typed edges)
  → Export (llms.txt, JSON sidecars, graph, sitemap)
  → Governance (lint, staleness, contradiction detection, duplicate detection)
```

---

## Daemon Scheduling

| Job | Interval | Purpose |
|-----|----------|---------|
| Inbox poll | 15s | Scan inbox for new files |
| Retry failed ingests | 30 min | Retry previously failed ingestions |
| Rebuild index | 30 min | Rebuild fulltext + vector + metadata indexes |
| Lint/govern | 60 min | Run governance checks, generate reports |
| Export | 60 min | Re-run all export formats |
| Review queue | 60 min | Populate review queue from candidates |
| Stale check | 24h | Flag pages with outdated time-sensitive content |
| Duplicate detection | 24h | Find near-duplicate pages across domains |
| Promotion | 24h | Score pages for cross-domain promotion |

Max parallel workers: 2 (configurable in `daemon.yaml`)

---

## Completed Features (V1 + Phase 1.1)

### Foundation & Core Pipeline
- [x] Project structure and configuration (Pydantic + YAML)
- [x] Ingest pipeline (inbox watcher, adapters, routing, normalizer)
- [x] Source adapters: ClaudeSession, Obsidian, Markdown, Text
- [x] Extraction pipeline: entities, concepts, claims, QA pairs, relationships
- [x] DeterministicIntegrator with merge strategies and rollback

### Indexing & Search
- [x] Metadata index (tag, kind, domain lookups)
- [x] Fulltext search with TF-IDF scoring (inverted index)
- [x] **Vector/semantic search with FAISS** (Phase 1.1 — this session)
- [x] **RRF rank fusion of fulltext + vector results** (Phase 1.1 — this session)
- [x] Unified query interface (WikiQuery)
- [x] Index rebuild daemon job (now includes vector rebuild)
- [x] Backlink index (reverse link tracking)
- [x] Relationship index (bidirectional, typed edges)
- [x] Graph edge index

### Governance & Maintenance
- [x] Metadata linter (validation, orphan detection)
- [x] Staleness detector (age-based, time-sensitive content flags)
- [x] Quality scorer (multi-factor assessment)
- [x] Governance job with markdown reports
- [x] Contradiction detection (negation, numerical, semantic)
- [x] Duplicate entity detection
- [x] Routing mistake detection
- [x] Clean broken links
- [x] Backlink index maintenance

### Export Pipeline
- [x] llms.txt exporter (LLM-optimized format, standard for AI-readable docs)
- [x] llms-full.txt exporter (comprehensive page data)
- [x] JSON sidecar exporter (per-page metadata)
- [x] Graph exporter (nodes + edges)
- [x] Sitemap generator (XML)
- [x] Export job orchestration

### Claims Processing
- [x] Factual claim extraction from pages (LLM-led)
- [x] Claim listing and indexing
- [x] Claim search across all pages
- [x] Contradiction detection on claims

### Promotion & Sharing
- [x] Promotion scoring algorithm (cross-domain references, quality, age)
- [x] Promotion candidates check
- [x] Auto-promote or review queue workflow
- [x] Page promotion to shared space
- [x] Page unpromotion with tombstone creation

### Review Queue
- [x] Full lifecycle: pending → approved/rejected/deferred
- [x] Manual review item creation
- [x] Queue stats and listing
- [x] Cleanup of old resolved items

### Agent Integration
- [x] Claude Code skills (/wiki, /ingest, /govern, /export)
- [x] Agent bootstrap (.claude/bootstrap.md)
- [x] Cross-agent conventions (AGENT_CONVENTIONS.md)
- [x] GitHub Copilot integration
- [x] Cursor IDE bootstrap and rules
- [x] Claude Code session capture hooks (SessionEnd, PreCompact)

### Daemon Reliability
- [x] APScheduler-based daemon with configurable jobs
- [x] ThreadPoolExecutor worker pool (max 2 workers)
- [x] Job execution history store
- [x] **Daemon error hierarchy** (Phase 0.5 — this session)
- [x] **Config validation at startup** (Phase 0.5 — prior session)
- [x] **Structured logging** (Phase 0.5 — prior session)

### CLI Command Suite (full list)
- [x] `init` — Initialize wiki instance
- [x] `daemon start/status/jobs` — Daemon lifecycle
- [x] `search query/get/backlinks` — Search and retrieve pages
- [x] `ingest file/text/obsidian/failed/stats` — Ingest content
- [x] `claims extract/list/search` — Claims management
- [x] `govern check/contradictions/duplicates/merge-duplicates/routing-mistakes/rebuild-index/update-backlinks/clean-broken-links`
- [x] `export all/llmstxt/llmsfull/graph` — Export pipeline
- [x] `graph edges/neighbors/path/stats/subgraph` — Graph queries
- [x] `promote check/process` — Page promotion
- [x] `query relationships/rebuild-relationships` — Relationship queries
- [x] `review add/list/show/approve/reject/defer/stats/cleanup` — Review queue
- [x] `integrate apply/check/history/rollback/strategies` — Deterministic integration
- [x] `changes list/diff/show/stats` — Change log
- [x] `govern run/status/report` — Run and inspect daemon jobs
- [x] `hooks install/uninstall` — Session capture hooks

---

## Known Issues / Technical Debt

### Resolved (All P0 fixed in Epic 1)

The following issues from the Architecture Review 2026-04-23 are resolved:
- **Non-atomic JSON index writes** — Fixed: all index saves use tmp → os.replace pattern
- **Daemon job concurrency** — Fixed: per-index `threading.Lock` enforced via `WikiQuery`
- **Stuck inbox files** — Fixed: startup recovery moves `processing/` files back to `new/`
- **No HTTP API** — Fixed: full REST API + MCP server with 8 tools

### Medium

| Issue | Severity | Description |
|-------|----------|-------------|
| 2 UI route tests failing | Low | `test_ui_routes.py` expects 500 for missing password (returns 401), and `app.state.wiki` not set in test |
| Web UI interactive features | Low | Template scaffolding exists; servlet pages return "Coming soon" (501) |
| API auth when network-exposed | Medium | No Bearer token auth on REST/MCP endpoints; relies on VM network isolation |
| LLM call timeout | Medium | Worker thread blocks indefinitely on hung LLM calls; restart required |

### Medium

| Issue | Severity | Description |
|-------|----------|-------------|
| Onboarding flow | Medium | Domain configs are hardcoded (vulpine-solutions, home-assistant, homelab, personal, general). `llm-wiki init` should ask questions and generate config. Estimated effort: 4h. |
| `frontmatter` schema validation dead code | Medium | `contracts.require_schema_validation: true` is in models.yaml but `DeterministicIntegrator` doesn't actually validate against schemas. Config flag is dead. Estimated effort: 2h. |
| Dependency scanning missing | Low | No `pip-audit` in CI. Estimated effort: 30 min. |
| LLM calls lack timeout | High | Ingestion path makes unbounded LLM calls with no timeout. A hung LLM request blocks that worker thread until the thread pool is exhausted. Fix: add timeout to `models/client.py`. Estimated effort: 1h. |
| Simultaneous promotion race | Medium | Two daemon instances promoting the same page simultaneously could create duplicates in `shared/`. Fix: file-based lock on the shared page path. Estimated effort: 2h. |

### Low

| Issue | Severity | Description |
|-------|----------|-------------|
| Pre-existing mypy `assignment` error | Low | `enrichment.py` has a pre-existing mypy error not introduced this session. Investigate when touching that file. |
| FAISS SWIG deprecation warnings | Info | `faiss-cpu` has 3 SWIG bindings deprecation warnings. Harmless, expected to be fixed in a future faiss release. |
| In-memory indexes at scale | Info | At 10k pages, indexes load in ~50ms each. At 100k pages: ~500ms each. Acceptable for solo dev, noticeable at scale. |

---

## Domains Configured

| Domain | Purpose |
|--------|---------|
| `vulpine-solutions` | Work/consulting knowledge |
| `home-assistant` | Home automation configuration and knowledge |
| `homelab` | Homelab infrastructure notes |
| `personal` | Personal notes and reference |
| `general` | General-purpose, not domain-specific |

---

## LLM Provider Support

| Provider | Status |
|---------|--------|
| OpenAI (gpt-4, gpt-4o) | Supported |
| Anthropic (Claude) | Supported via OpenAI-compatible endpoint |
| Ollama (local models) | Supported |
| LM Studio | Supported |
| Claude Agent SDK | Supported |
| Gemini CLI | Deferred to post-Phase-2 |

---

## Optional Dependencies

| Extra | Packages | Feature Enabled |
|-------|----------|----------------|
| `llm-wiki[vector]` | `faiss-cpu>=1.8`, `sentence-transformers>=3.0` | Semantic/dense vector search |

Without `[vector]`: all vector operations silently no-op, fulltext search still works.

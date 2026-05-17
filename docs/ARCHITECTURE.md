# LLM Wiki — Architecture

## System Overview

LLM Wiki is a monolithic Python application with a single process daemon that owns all background work. The architecture is deliberately simple: files on disk are the source of truth, a daemon maintains derived state (indexes, exports, reports), and a CLI provides the user interface.

```
┌─────────────────────────────────────────────────────────────────┐
│                          CLI (Click)                            │
│   llm-wiki init / daemon / search / ingest / govern / export   │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                     WikiDaemon                                   │
│   APScheduler BackgroundScheduler + ThreadPoolExecutor (max 2)  │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐ │
│  │ Inbox Poll  │  │ Index Rebuild│  │ Governance + Export     │ │
│  │ (15s)       │  │ (30min)      │  │ (60min each)            │ │
│  └──────┬──────┘  └──────┬───────┘  └───────────┬─────────────┘ │
│         │                │                       │               │
└─────────┼────────────────┼───────────────────────┼───────────────┘
          │                │                       │
┌─────────▼────────────────▼───────────────────────▼───────────────┐
│                     File System (wiki_system/)                    │
│                                                                   │
│  inbox/          domains/           index/        exports/        │
│  ├── new/        ├── {domain}/      ├── fulltext  ├── llms.txt    │
│  ├── processing/ │   ├── queue/     ├── vector    ├── graph.json  │
│  ├── done/       │   └── pages/     ├── metadata  └── sitemap.xml │
│  └── failed/     └── shared/       └── backlinks                 │
│                                                                   │
│  reports/        review_queue/     state/         logs/           │
└───────────────────────────────────────────────────────────────────┘
```

## Component Architecture

### 1. Entry Points

**CLI** (`src/llm_wiki/cli.py`, ~2,912 lines)
- Single Click group with 15 command subgroups
- All commands are thin wrappers: load config, instantiate the relevant service/index, call it, format output
- No business logic in cli.py itself

**Daemon** (`src/llm_wiki/daemon/main.py`)
- `WikiDaemon` class: validates config on init, registers 9 APScheduler jobs on start
- `run()` blocks on SIGINT/SIGTERM
- `health()` returns a dict describing scheduler state and job last-run times

### 2. Ingestion Pipeline

```
new/ file
  ↓
InboxWatcher (watchdog FileSystemEventHandler)
  ↓
Adapter selection (by file extension / content heuristic)
  ├── MarkdownAdapter
  ├── TextAdapter
  ├── ObsidianAdapter
  └── ClaudeSessionAdapter
  ↓
Normalizer → produces NormalizedDocument
  ↓
DomainRouter → selects target domain from routing.yaml rules
  ↓
{domain}/queue/ (staging area)
  ↓
DeterministicIntegrator → merges with existing page if present
  ├── merge strategies: keep_existing, union, prefer_newer
  └── rollback on failure
  ↓
Extraction Service (LLM-led, parallel)
  ├── claims.py       → factual claim extraction
  ├── entities.py     → named entity extraction
  ├── concepts.py     → concept/topic extraction
  ├── relationships.py → entity relationship extraction
  └── qa.py           → QA pair generation
  ↓
Index updates (FulltextIndex + VectorIndex + MetadataIndex + BacklinkIndex + GraphEdgeIndex)
  ↓
{domain}/pages/ (approved page)
```

**FailedIngestionTracker**: Tracks files that failed normalization/routing. Retry job runs every 30min.

### 3. Index Subsystem

Four live indexes, all JSON-backed (except FAISS binary):

| Index | File | Purpose |
|-------|------|---------|
| `FulltextIndex` | `fulltext.json` | TF-IDF inverted index, BM25-style scoring |
| `VectorIndex` | `vector_index.faiss` + `vector_meta.json` | FAISS IndexFlatL2, 384-dim sentence-transformers |
| `MetadataIndex` | `metadata.json` | Tag, kind, domain, status lookups |
| `BacklinkIndex` | `backlinks.json` | Reverse link tracking (page_id → pages linking to it) |
| `GraphEdgeIndex` | `graph_edges.json` | Bidirectional typed edges for graph queries |
| `RelationshipIndex` | `relationships.json` | Extracted entity relationships |

**WikiQuery** (`src/llm_wiki/query/search.py`) — unified search interface:
1. Fulltext search (BM25-style TF-IDF, limit × 2 candidates)
2. Vector search (FAISS cosine similarity, limit × 2 candidates)
3. RRF fusion: `score += 1 / (60 + rank + 1)` per result from each ranker
4. Metadata post-filter by domain / kind / tags

**Rebuild strategy**: `IndexRebuildJob` (30min interval) does a full scan of `domains/*/pages/*.md` and rebuilds all indexes from scratch. Incremental updates happen at ingest time; the rebuild job is a safety net.

### 4. Search Query Flow

```
WikiQuery.search(query, domain=None, kind=None, tags=None, limit=10)
  ├── FulltextIndex.search(query, limit=20)   → [{page_id, title, score}, ...]
  ├── VectorIndex.search(query, limit=20)     → [{page_id, title, domain, score}, ...]
  ├── RRF fusion                              → sorted candidate_ids
  ├── MetadataIndex filter (domain/kind/tags)
  └── Page content load for top N hits       → [{page_id, title, content, ...}, ...]
```

### 5. Governance Pipeline

Runs every 60min via `GovernanceJob`. Produces a markdown report in `reports/`.

| Checker | Purpose |
|---------|---------|
| `linter.py` | Validates frontmatter: required fields, valid kind/status, orphan detection |
| `staleness.py` | Flags pages not updated within threshold; detects time-sensitive content |
| `quality.py` | Multi-factor quality score (completeness, link density, claim density) |
| `contradictions.py` | Detects negation, numerical, and semantic contradictions between claims |
| `duplicates.py` | Near-duplicate detection using TF-IDF cosine similarity |
| `routing_mistakes.py` | Detects pages in wrong domain based on content signals |

### 6. Export Pipeline

Runs every 60min via `ExportJob`.

| Exporter | Output | Format |
|----------|--------|--------|
| `LlmsTextExporter` | `exports/llms.txt` | LLM-optimized format (llms.txt standard) |
| `LlmsFullExporter` | `exports/llms-full.txt` | Full page data, all metadata |
| `JsonSidecarExporter` | `exports/{page_id}.json` | Per-page JSON metadata |
| `GraphExporter` | `exports/graph.json` | Nodes + edges for visualization |
| `SitemapExporter` | `exports/sitemap.xml` | XML sitemap |

### 7. Promotion System

Pages that accumulate cross-domain references above a threshold are candidates for promotion to `shared/`.

```
PromotionScorer.score(page) → float
  ├── cross_domain_refs: how many other domains link to this page
  ├── quality_score: from QualityChecker
  ├── age: pages older than 30 days get a bonus
  └── weighted sum → promotion_score

PromotionEngine.process()
  ├── score >= auto_promote_threshold (10.0) → auto-promote to shared/
  ├── score >= suggest_threshold (5.0)       → add to review queue
  └── else                                   → no action
```

### 8. Review Queue

Full lifecycle state machine: `pending → approved / rejected / deferred`

- Items enter via: governance findings, promotion suggestions, or manual `llm-wiki review add`
- Items resolve via: `review approve/reject/defer`
- `ReviewQueueJob` (60min) runs `PromotionEngine.process()` to populate the queue automatically

### 9. Config System

Four YAML files, all validated by Pydantic on daemon startup:

```
config/
├── daemon.yaml   → DaemonConfig (intervals, worker count)
├── domains.yaml  → DomainsYAML (list of DomainConfig)
├── models.yaml   → ModelsYAML (LLM provider settings per task)
└── routing.yaml  → RoutingYAML (source path → domain rules)
```

`WikiConfig` aggregates all four. `ConfigValidator` validates the merged config at startup, raising `ConfigError` for invalid state.

## Daemon Scheduling

| Job | Class | Interval | Workers |
|-----|-------|----------|---------|
| Inbox scan | `InboxScanJob` | 15s | Shared pool |
| Queue-to-pages | `QueueToPagesJob` | 15min | Shared pool |
| Retry failed ingests | `RetryFailedIngestsJob` | 30min | Shared pool |
| Index rebuild | `IndexRebuildJob` | 30min | Shared pool |
| Export | `ExportJob` | 60min | Shared pool |
| Governance/lint | `GovernanceJob` | 60min | Shared pool |
| Review queue | `ReviewQueueJob` | 60min | Shared pool |
| Staleness check | `StalenessJob` | 24h | Shared pool |
| Duplicate detection | `DuplicatesJob` | 24h | Shared pool |

`ThreadPoolExecutor(max_workers=2)` — all jobs compete for the same 2 worker slots. This is intentional: prevents resource exhaustion, but means governance + index rebuild cannot run simultaneously without queuing.

**Known concurrency risk**: Two workers can both write to the same JSON index file. Fix planned (P0-2): add `threading.Lock` per index file.

## Data Flow Summary

```
External input (files/text/session)
  └─► Inbox (new/) → Adapter → Normalize → Route → Queue
                                                      │
                                           DeterministicIntegrator
                                            (merge strategies)
                                                      │
                                           Extraction (LLM async)
                                            claims / entities / concepts
                                                      │
                                           Index writes (5 indexes)
                                                      │
                             ┌────────────────────────┤
                             │                        │
                        GovernanceJob            ExportJob
                        (lint/stale/dup)        (llms.txt/graph)
                             │                        │
                        reports/             exports/
```

## Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| No external database | Local-first; files are version-controllable; JSON is readable |
| APScheduler not Celery | Single-process, no broker needed; simpler ops |
| TF-IDF not Elasticsearch | Local-first; no external service; good enough for <100k pages |
| FAISS IndexFlatL2 not HNSW | Exact search correctness for small corpora; HNSW saves <50ms at scale |
| OpenAI-compatible API | Works with OpenAI, Anthropic, Ollama, LM Studio — same interface |
| Optional vector deps | Users without GPU/large disk still get fulltext search |
| Pydantic for config | Validation at startup catches config errors before the daemon runs |

## Known Architectural Issues (P0)

1. **Non-atomic JSON writes** — index saves write directly to file; crash mid-write corrupts index. Fix: `tmp → os.replace()` pattern (exists in `JobExecutionStore`).
2. **No write mutex** — concurrent daemon workers can corrupt JSON indexes. Fix: `threading.Lock` per index.
3. **Stuck inbox files** — crash during processing orphans files in `inbox/processing/`. Fix: on startup, move to `new/` or `failed/`.
4. **No HTTP API** — CLI-only; agent harness uses subprocess. Fix: FastAPI optional dep (Priority 1 roadmap item).

See `docs/bmad/ROADMAP_REMAINING.md` for full remediation plan.

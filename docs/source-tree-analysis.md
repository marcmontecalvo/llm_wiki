# LLM Wiki — Source Tree Analysis

Complete module-by-module breakdown of the codebase. 80 source files across 15 modules.

## Top-Level Layout

```
src/llm_wiki/
├── cli.py                  # Main CLI entry point (Click, ~2912 lines)
├── __init__.py             # Package exports (daemon error classes)
├── adapters/               # Input format adapters
├── changelog/              # Append-only operation log
├── config/                 # Config loading and validation
├── daemon/                 # Background scheduler + job implementations
│   └── jobs/               # One file per scheduled job
├── export/                 # Export format generators
├── extraction/             # LLM-led content extraction pipeline
├── governance/             # Quality, lint, contradiction, staleness checks
├── hook_templates/         # Claude Code session capture hooks
├── index/                  # Search index implementations
├── ingest/                 # Inbox watcher, normalizer, router
├── integration/            # DeterministicIntegrator (merge engine)
├── models/                 # Pydantic schemas + LLM client
├── promotion/              # Promotion scoring and engine
├── query/                  # Unified search interface
├── review/                 # Review queue storage and lifecycle
├── templates/              # Page template engine
└── utils/                  # Frontmatter parsing, page ID generation
```

## Module Walkthroughs

### `adapters/` — Input Format Adapters (5 files)

Adapters normalize diverse input formats into a common `NormalizedDocument` structure that the ingestion pipeline can process.

| File | Class | Input |
|------|-------|-------|
| `markdown.py` | `MarkdownAdapter` | `.md` files — passes through with frontmatter extraction |
| `text.py` | `TextAdapter` | `.txt` files — wraps in minimal frontmatter |
| `obsidian.py` | `ObsidianAdapter` | Obsidian-flavored markdown (wikilinks, tags as `#tag`) |
| `claude_session.py` | `ClaudeSessionAdapter` | Claude Code session transcripts (JSONL) |
| `__init__.py` | — | `get_adapter(path)` factory function |

**Key pattern**: Every adapter implements `adapt(path: Path) -> NormalizedDocument`. The factory chooses by file extension and content sniff.

**Claude session adapter**: Reads JSONL conversation exports from Claude Code, extracts human/assistant turns, strips tool calls, produces a clean narrative markdown summary.

### `changelog/` — Operation Log (2 files)

Append-only log of all wiki operations (ingest, integration, governance, promotion).

| File | Class | Purpose |
|------|-------|---------|
| `log.py` | `ChangeLog` | Append entries, list, diff, stats |
| `models.py` | `ChangeEntry` | Pydantic schema for a changelog entry |

Entries stored in `wiki_system/logs/changelog.jsonl`. Each entry has: timestamp, operation, page_id, domain, before/after summary, and actor (daemon job or CLI user).

CLI: `llm-wiki changes list/diff/show/stats`

### `config/` — Configuration (3 files)

| File | Class | Purpose |
|------|-------|---------|
| `loader.py` | `load_config()` | Load + merge 4 YAML files into `WikiConfig` |
| `schemas.py` | `WikiConfig`, `DomainConfig`, etc. | Pydantic schemas (also in `models/config.py`) |
| `validator.py` | `ConfigValidator` | Validates merged config at daemon startup |

`ConfigValidator` checks:
- All domain IDs are unique and lowercase-hyphenated
- Routing rules reference existing domains
- Model provider configs have required fields
- `max_parallel_jobs` is reasonable (1-8)

Raises `ConfigError` (from `daemon/errors.py`) if invalid.

### `daemon/` — Daemon Core (12 files)

| File | Class | Purpose |
|------|-------|---------|
| `main.py` | `WikiDaemon` | Start/stop/health; registers all jobs |
| `scheduler.py` | `JobScheduler` | Wraps APScheduler; start/stop/trigger/status |
| `workers.py` | `WorkerPool` | Wraps ThreadPoolExecutor; submit/shutdown |
| `execution_store.py` | `JobExecutionStore` | Persists job run history to `state/jobs.json` (uses atomic writes) |
| `errors.py` | Hierarchy | `DaemonError` → `ConfigError`, `SchedulerError`, `WorkerPoolError`, `ExecutionError`, `GovernanceError`, `IngestionError` |
| `logging_config.py` | `setup_logging()` | Structured JSON logging for daemon output |

**`daemon/jobs/`** — one file per scheduled job:

| File | Class | Interval |
|------|-------|----------|
| `inbox_scan.py` | `InboxScanJob` | 15s |
| `queue_to_pages.py` | `QueueToPagesJob` | 15min |
| `retry_ingests.py` | `RetryFailedIngestsJob` | 30min |
| `index_rebuild.py` | `IndexRebuildJob` | 30min |
| `export.py` | `ExportJob` | 60min |
| `governance.py` | `GovernanceJob` | 60min |
| `review_queue.py` | `ReviewQueueJob` | 60min |

All job classes implement `execute() -> dict` which returns a result dict logged to `JobExecutionStore`. Jobs catch all exceptions and return error state rather than crashing the daemon.

### `export/` — Export Generators (5 files)

| File | Class | Output |
|------|-------|--------|
| `llmstxt.py` | `LlmsTextExporter` | `exports/llms.txt` |
| `llmsfull.py` | `LlmsFullExporter` | `exports/llms-full.txt` |
| `graph.py` | `GraphExporter` | `exports/graph.json` |
| `sitemap.py` | `SitemapExporter` | `exports/sitemap.xml` |
| `json_sidecar.py` | `JsonSidecarExporter` | `exports/{page_id}.json` (one per page) |

All exporters read from `wiki_system/domains/*/pages/` and produce output in `wiki_system/exports/`. They're idempotent — running twice produces the same output.

**llms.txt format**: Follows the emerging `llms.txt` standard for AI-readable documentation. One entry per page with title, domain, tags, and a clean prose summary (no raw markdown syntax).

### `extraction/` — LLM Extraction Pipeline (7 files)

| File | Class | Extracts |
|------|-------|---------|
| `claims.py` | `ClaimsExtractor` | Factual claims as `(subject, predicate, object)` triples |
| `entities.py` | `EntityExtractor` | Named entities (people, orgs, products, concepts) |
| `concepts.py` | `ConceptExtractor` | Abstract concepts and topics |
| `relationships.py` | `RelationshipExtractor` | Typed relationships between entities |
| `qa.py` | `QAExtractor` | Question-answer pairs for retrieval |
| `enrichment.py` | `EnrichmentPipeline` | Orchestrates all extractors on a page |
| `service.py` | `ExtractionService` | Entry point; manages LLM calls with retries |

All extractors use the same `ModelProviderConfig` (`models.yaml`) and the `openai` client with a configurable timeout (currently unbounded — see P0-4 roadmap item).

**Extraction result format**: Each extractor returns a Pydantic model that's merged into the page's frontmatter. Extracted data is stored in the page's YAML frontmatter under keys like `claims:`, `entities:`, `qa_pairs:`.

### `governance/` — Quality & Correctness (6 files)

| File | Class | Checks |
|------|-------|--------|
| `linter.py` | `MetadataLinter` | Required frontmatter fields, valid enum values, orphan pages |
| `staleness.py` | `StalenessDetector` | Age-based staleness, time-sensitive content flags |
| `quality.py` | `QualityChecker` | Multi-factor score: completeness, link density, claim density |
| `contradictions.py` | `ContradictionDetector` | Negation, numerical, semantic contradictions between claims |
| `duplicates.py` | `DuplicateDetector` | Near-duplicate detection via TF-IDF cosine similarity |
| `routing_mistakes.py` | `RoutingMistakeDetector` | Pages whose content signals a different domain |

All checkers produce `Finding` objects. `GovernanceJob` aggregates all findings into a markdown report saved to `wiki_system/reports/governance_{timestamp}.md`.

**Contradiction detection**: Three strategies:
1. **Negation**: same subject/predicate pair with opposite polarity (`X is fast` vs `X is not fast`)
2. **Numerical**: same subject/predicate with different numeric objects (`X costs $100` vs `X costs $200`)
3. **Semantic**: embedding similarity between claim pairs (requires vector deps)

### `index/` — Search Indexes (6 files)

| File | Class | Storage |
|------|-------|---------|
| `fulltext.py` | `FulltextIndex` | `fulltext.json` — inverted index |
| `vector.py` | `VectorIndex` | `vector_index.faiss` + `vector_meta.json` |
| `metadata.py` | `MetadataIndex` | `metadata.json` — tag/kind/domain maps |
| `backlinks.py` | `BacklinkIndex` | `backlinks.json` — reverse link map |
| `graph_edges.py` | `GraphEdgeIndex` | `graph_edges.json` — typed edge list |
| `relationships.py` | `RelationshipIndex` | `relationships.json` — extracted relationships |

**FulltextIndex**: TF-IDF scoring. On `add_document`, tokenizes and updates the inverted index in-memory. `save()` writes to JSON. `search(query)` computes TF-IDF scores across matching tokens.

**VectorIndex** (Phase 1.1):
- `_ensure_model()` — lazy-loads `SentenceTransformer('all-MiniLM-L6-v2')` on first use
- `_clean_for_embedding(text)` — strips markdown syntax before embedding
- `add_document()` — embeds inline via sentence-transformers, appends to FAISS index
- `remove_document()` — rebuilds FAISS from scratch (FAISS IndexFlatL2 has no deletion API)
- `search(query, domain=None)` — embed query, L2 nearest neighbor search, post-filter by domain
- `save()` / `load()` — `faiss.write_index` / `faiss.read_index` + JSON metadata

**Known issue**: All index saves are non-atomic (P0-1). Fix: apply `tmp → os.replace()` pattern from `JobExecutionStore`.

### `ingest/` — Inbox Pipeline (4 files)

| File | Class | Purpose |
|------|-------|---------|
| `watcher.py` | `InboxWatcher` | `watchdog` FileSystemEventHandler; watches `inbox/new/` |
| `normalizer.py` | `Normalizer` | Selects adapter, produces `NormalizedDocument` |
| `router.py` | `DomainRouter` | Matches path/content against `routing.yaml` rules to pick domain |
| `failed_tracker.py` | `FailedIngestionTracker` | Logs failures to `inbox/failed/`, tracks retry count |

**File state machine**: `new/` → `processing/` → `done/` or `failed/`

**Known issue**: Files in `processing/` are orphaned if daemon crashes (P0-3). Fix: on startup, scan `processing/` and move files back to `new/`.

### `integration/` — Merge Engine (2 files)

| File | Class | Purpose |
|------|-------|---------|
| `integrator.py` | `DeterministicIntegrator` | Merge new content into existing page |
| `models.py` | `IntegrationResult` | Merge result: success/failure, before/after diff |

**Merge strategies** (per-field, configured in `models.yaml`):
- `keep_existing` — don't overwrite if field already has a value
- `union` — combine lists (for tags, links, etc.)
- `prefer_newer` — always take the incoming value

`DeterministicIntegrator.apply()` uses a checkpoint file to enable rollback if integration fails partway through.

### `models/` — Pydantic Schemas + LLM Client (6 files)

| File | Contents |
|------|---------|
| `page.py` | `PageFrontmatter` + 4 subtypes (`EntityFrontmatter`, `ConceptFrontmatter`, `SourceFrontmatter`, `QAFrontmatter`) |
| `config.py` | `WikiConfig`, `DomainConfig`, `DaemonConfig`, `ModelProviderConfig`, etc. |
| `domain.py` | `Domain` runtime model (wraps `DomainConfig` with live path info) |
| `integration.py` | `NormalizedDocument`, integration schemas |
| `client.py` | `LLMClient` — OpenAI-compatible HTTP client with tenacity retry logic |
| `__init__.py` | Package exports |

**`LLMClient`**: Wraps `openai.OpenAI(base_url=..., api_key=...)`. Supports any OpenAI-compatible endpoint. Uses `tenacity` for retries with exponential backoff. **Known issue**: No timeout configured (P0-4).

### `promotion/` — Promotion Engine (4 files)

| File | Class | Purpose |
|------|-------|---------|
| `scorer.py` | `PromotionScorer` | Scores pages for cross-domain promotion |
| `engine.py` | `PromotionEngine` | Runs scorer, decides promote/suggest/skip |
| `models.py` | `PromotionCandidate` | Pydantic model for a promotion candidate |
| `config.py` | `PromotionConfig` | Thresholds (in `models/config.py`) |

**Scoring factors**:
- `cross_domain_refs` (weight: 0.4) — how many other domains link to this page
- `quality_score` (weight: 0.3) — from `QualityChecker`
- `age_bonus` (weight: 0.3) — pages >30 days old get a bonus

### `query/` — Unified Search (2 files)

| File | Class | Purpose |
|------|-------|---------|
| `search.py` | `WikiQuery` | Unified fulltext + vector + metadata search with RRF fusion |
| `__init__.py` | — | Package exports |

`WikiQuery` is the single entry point for all searches. It loads all three primary indexes, fuses fulltext + vector results via RRF, then applies metadata filters.

### `review/` — Review Queue (2 files)

| File | Class | Purpose |
|------|-------|---------|
| `queue.py` | `ReviewQueue` | Full lifecycle: add/approve/reject/defer/stats/cleanup |
| `models.py` | `ReviewItem` | Pydantic model: id, kind, page_id, reason, status, timestamps |

Items stored as JSON in `wiki_system/review_queue/{status}/{id}.json`.

### `templates/` — Page Templates (1 file)

`engine.py` — `TemplateEngine` generates new page markdown from a `PageFrontmatter` model. Used by `llm-wiki integrate apply` to create pages that don't yet exist.

### `utils/` — Shared Utilities (2 files)

| File | Purpose |
|------|---------|
| `frontmatter.py` | `parse_frontmatter(path)` / `write_frontmatter(path, data)` — YAML frontmatter parsing wrapper |
| `page_id.py` | `generate_page_id(title, domain)` — deterministic ID generation (slug from title + domain prefix) |

## Test Coverage

```
tests/
├── unit/               # One test file per module (80+ test files)
│   ├── test_vector_index.py     (252 lines, 19 tests)
│   ├── test_fulltext_index.py
│   ├── test_wiki_query.py
│   ├── test_daemon_scheduler.py
│   └── ...
├── integration/        # End-to-end flow tests
│   └── test_ingest_pipeline.py
└── conftest.py         # Shared fixtures: temp_dir, wiki_root, etc.
```

Total: 1,106 tests, ~93% coverage.

## Line Count Summary

| Module | Approx Lines |
|--------|-------------|
| `cli.py` | 2,912 |
| `index/vector.py` | 407 |
| `daemon/main.py` | ~250 |
| `extraction/` (total) | ~800 |
| `governance/` (total) | ~700 |
| `index/fulltext.py` | ~350 |
| `query/search.py` | ~200 |
| `models/page.py` | ~180 |
| `integration/integrator.py` | ~300 |

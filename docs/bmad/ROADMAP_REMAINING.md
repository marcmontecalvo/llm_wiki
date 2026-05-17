# Roadmap: Remaining Work

**Last updated**: 2026-05-16
**Current state**: V1 complete + Phase 1.1 (Vector Search) complete
**Next milestone**: Fix critical reliability issues, then V2 (Trust Layer)

This document details everything that needs to happen, prioritized by impact and blocking relationships. Read alongside `PROJECT_STATUS.md` (current state) and `SESSION_REPORT_2026-05-16.md` (what changed this session).

---

## Priority 0 — Critical Reliability Fixes (Do Before V2)

These are bugs that will cause data loss or corruption under normal operation. They should be fixed before building anything else on top of the system.

### P0-1: Atomic index writes

**Problem**: `FulltextIndex.save()` and `MetadataIndex.save()` write directly to their JSON files. If the process crashes (OOM, SIGKILL, power loss) mid-write, the file is left in a partially-written state. On next startup, the index fails to load and all search results are empty until a rebuild.

**Pattern already exists**: `JobExecutionStore._save()` uses `json.dumps → tmp file → os.replace()`. Atomic on POSIX. Apply this everywhere.

**Files to change**:
- `src/llm_wiki/index/fulltext.py` — `save()` method
- `src/llm_wiki/index/metadata.py` — `save()` method
- `src/llm_wiki/index/backlinks.py` — `save()` method
- `src/llm_wiki/index/graph_edges.py` — `save()` method
- `src/llm_wiki/index/relationships.py` — `save()` method

**Estimated effort**: 30-60 minutes. Pure mechanical fix.

**Pattern to apply**:
```python
import tempfile, os

def save(self) -> None:
    data = self._serialize()
    with tempfile.NamedTemporaryFile('w', dir=self.index_dir, delete=False, suffix='.tmp') as f:
        json.dump(data, f, indent=2)
        tmp_path = f.name
    os.replace(tmp_path, self.index_path)
```

---

### P0-2: Index write mutex for concurrent daemon workers

**Problem**: The daemon's `ThreadPoolExecutor` (max 2 workers) can run the governance job and index rebuild job simultaneously. Both touch the same JSON index files. Without a lock, concurrent writes interleave and produce corrupt JSON.

**Fix**: A module-level `threading.Lock` for each index file, acquired before any write.

**Files to change**:
- `src/llm_wiki/index/fulltext.py`
- `src/llm_wiki/index/metadata.py`
- `src/llm_wiki/index/backlinks.py`
- (and other index files that are written by multiple jobs)

**Alternative**: Reduce `max_workers` to 1. This is the simplest fix but serializes all jobs. Probably acceptable given the current job frequency (30-60 min intervals). Consider as a temporary mitigation.

**Estimated effort**: 1-2 hours.

---

### P0-3: Recover stuck `inbox/processing/` files on startup

**Problem**: If the daemon crashes while normalizing a file (it moves it to `processing/` before starting work), the file is orphaned. On next startup, the inbox watcher sees an empty `new/` and misses the stuck file entirely.

**Fix**: On daemon startup, scan `processing/` and move any files back to `new/` (or `failed/` if they've failed >N times).

**Files to change**:
- `src/llm_wiki/ingest/watcher.py` — add recovery logic in `__init__` or `start()`
- `src/llm_wiki/daemon/main.py` — call recovery on daemon start

**Estimated effort**: 2 hours.

---

### P0-4: LLM call timeout in ingestion path

**Problem**: The extraction service makes unbounded LLM API calls. If the LLM provider hangs (rate limit, network issue, model overload), the worker thread blocks indefinitely. With max 2 workers, two stuck LLM calls make the entire daemon unresponsive.

**Fix**: Add `timeout` parameter to `models/client.py` calls. Use `httpx` timeout (already the underlying transport). Default: 60s for extraction, 120s for integration.

**Files to change**:
- `src/llm_wiki/models/client.py`
- `src/llm_wiki/extraction/service.py`

**Estimated effort**: 1-2 hours.

---

## Priority 1 — HTTP API (Blocker for Agent Harness Integration)

**Problem**: Everything is CLI-only. The agent harness currently calls CLI commands via subprocess. For proper integration (webhooks, bidirectional signaling, health checks), a programmatic HTTP interface is needed.

**Recommendation (from Architecture Review ADR-001)**: FastAPI as an optional dependency. The daemon, when started, optionally launches a FastAPI server on a configurable port. CLI routes become HTTP endpoints. Same `WikiConfig` and data reads — no new code paths, just new entry points.

**Key endpoints needed**:
```
GET  /health                    # Daemon health check
GET  /jobs                      # Job schedule and last-run status
POST /jobs/{job_name}/trigger   # Manually trigger a job
GET  /search?q=...&domain=...  # Search (fulltext + vector + RRF)
GET  /pages/{page_id}          # Get a single page
POST /ingest                    # Ingest a new document
GET  /domains                   # List configured domains
GET  /exports/{type}           # Get latest export content
```

**Implementation approach**:
1. Add `[api]` optional dependency: `fastapi>=0.100`, `uvicorn>=0.20`
2. New file: `src/llm_wiki/api/server.py` — FastAPI app with route handlers
3. New file: `src/llm_wiki/api/routes/` — One file per resource group
4. Modify `src/llm_wiki/daemon/main.py` — Optionally start uvicorn alongside APScheduler
5. Add `llm-wiki serve` CLI command as an alternative to `daemon start`

**Auth**: Bearer token via `API_TOKEN` env var (optional for local use, recommended for Tailscale deployments).

**Estimated effort**: 2-3 days.

**Related GitHub issue**: #86

---

## Priority 2 — V2: Trust and Review Layer

V2 makes the wiki safer to trust by adding confidence scoring, source citation enforcement, and better hallucination containment.

### V2-1: Source citation enforcement

**Problem**: Pages can claim facts without source references. Hallucinated content looks identical to well-sourced content.

**Implementation**:
- Add `required_citations: bool` field to domain config
- Modify governance linter to flag pages missing `sources:` frontmatter field
- Confidence scoring: pages without sources get lower quality score

**Files**:
- `src/llm_wiki/governance/linter.py`
- `src/llm_wiki/models/config.py` (domain config schema)

**Estimated effort**: 4-6 hours.

---

### V2-2: Confidence fields on claims

**Problem**: Claims extracted from pages have no confidence score. A hallucinated claim looks the same as a directly-quoted fact.

**Implementation**:
- Add `confidence: float` and `evidence_type: Literal["direct_quote", "paraphrase", "inferred", "unknown"]` to claim model
- Modify LLM extraction prompt to output confidence
- Surface confidence in claim search results and governance reports

**Files**:
- `src/llm_wiki/models/page.py` (claim schema)
- `src/llm_wiki/extraction/claims.py`
- `src/llm_wiki/governance/contradictions.py`

**Estimated effort**: 1 day.

---

### V2-3: Stale-page detector improvements

**Status**: Basic staleness detection exists (`governance/staleness.py`). Current detection is age-based. V2 adds content-based staleness.

**Missing**:
- LLM-powered staleness review: "Is this claim still accurate as of {date}?"
- Integration with claim timestamps: if a claim's source was ingested >6 months ago and the claim is time-sensitive, flag it
- Per-domain staleness thresholds (configurable)

**Estimated effort**: 1 day.

---

### V2-4: Orphan page checks

**Problem**: Pages with no inbound links (orphan pages) are invisible to navigation and likely stale or misrouted.

**Status**: `MetadataIndex` tracks backlinks. Orphan detection is partially implemented in the linter.

**Implementation**: Governance report listing orphan pages with suggested actions (promote to shared, merge with another page, delete).

**Estimated effort**: 4 hours.

---

### V2-5: Candidate page approval flow

**Problem**: The review queue exists but lacks a clear end-to-end flow for AI-suggested pages pending human review.

**Implementation**:
- Tighten the `queue/` → review queue → `pages/` promotion path
- Add `candidate` as a distinct page kind
- Daemon job: move high-confidence queue pages directly to pages/; low-confidence → review queue
- Governance report: pages in review queue aging beyond threshold

**Estimated effort**: 1 day.

---

## Priority 3 — V3: Cross-Domain Synthesis

V3 allows shared knowledge to surface without collapsing all domains into one flat namespace.

### V3-1: Shared concept/entity promotion flow (deferred — Community Detection)

**Status**: Deferred per `roadmap-deferred.md`. Graph edges already exist. Foundation is in place.

**What's needed**: Louvain community detection on the graph edge index to auto-suggest domain boundaries for cross-domain entities. Then auto-generate shared pages for entities appearing in N+ domains.

**File**: `src/llm_wiki/governance/community.py` (to create)
**Estimated effort**: ~300 lines.

---

### V3-2: Cross-domain summary pages (deferred)

**Status**: Deferred per `roadmap-deferred.md`. Requires cross-domain edges to be populated first (V3-1).

**What's needed**: Auto-generated pages for entities appearing in multiple domains. Summary page aggregates the entity's mentions, claims, and relationships across all domains.

**File**: `src/llm_wiki/cross_domain.py` (to create)
**Estimated effort**: ~200 lines.

---

### V3-3: Per-domain and global dashboards

**What's needed**:
- Per-domain summary: page count, claim count, last activity, top entities, staleness stats
- Global dashboard: cross-domain entity network, promotion queue status, contradiction count
- CLI: `llm-wiki dashboard` command
- Export: HTML dashboard generation in the export job

**Estimated effort**: 1-2 days.

---

### V3-4: Synthesis Cache (deferred)

**Status**: Deferred to post-Phase-3 per `roadmap-deferred.md`. Only useful at scale (>10k pages, >100 queries/day).

**What's needed**: Cache high-value queries. When a query repeatedly returns the same synthesized answer, record it as a cached page. Auto-expand the wiki where gaps are found.

**Pre-requisite**: Unified search (BM25 + vector — now complete).
**File**: `src/llm_wiki/cache.py` (to create)
**Estimated effort**: ~400 lines.

---

## Priority 4 — V4: UX + Product Layer

V4 makes the system useful to humans, not just agents.

### V4-1: Graph visualization UI

**Status**: Graph exporter already exists. Need a browser-based visualization.

**Implementation**:
- FastAPI serves a static HTML page with a JavaScript graph viewer (D3.js or Cytoscape.js)
- Nodes = pages, edges = relationships, node size = quality score, color = domain
- Filter by domain, entity, relationship type

**Pre-requisite**: HTTP API (Priority 1)
**Estimated effort**: 2-3 days.

---

### V4-2: Browse by entity/concept/source

**What's needed**: Navigation interface beyond search. Browse all pages tagged with an entity, all claims from a source, all pages in a concept cluster.

**Implementation**: FastAPI routes + minimal HTML templates. Not a full SPA — server-rendered pages are fine.

**Estimated effort**: 1-2 days.

---

### V4-3: Daemon control panel

**What's needed**: Web interface showing job schedule, last run status, next run, job output logs. Trigger jobs manually from the UI.

**Pre-requisite**: HTTP API (Priority 1)
**Estimated effort**: 1 day.

---

### V4-4: GraphViz export (deferred)

**Status**: Deferred per `roadmap-deferred.md`. The graph UI (V4-1) will handle this natively. Only implement if CLI tooling outside the UI is needed.

**File**: `src/llm_wiki/export/graphviz.py`
**Estimated effort**: ~50 lines.

---

## Priority 5 — V5: Optional Online Integrations

V5 adds bounded remote inputs without breaking local-first guarantees.

### V5-1: GitHub repo ingestion

**What's needed**: Adapter to ingest GitHub repositories (README, wikis, issue discussions). Pull on schedule, route to appropriate domain.

**Files**: `src/llm_wiki/adapters/github.py`, integration with InboxWatcher

**Estimated effort**: 1-2 days.

---

### V5-2: Docs site ingestion

**What's needed**: Adapter to scrape documentation sites (via `llms.txt` standard if available, otherwise HTML → markdown conversion). Rate-limited, bounded to configured URLs.

**Files**: `src/llm_wiki/adapters/docs_site.py`
**Estimated effort**: 1 day.

---

### V5-3: RSS feeds

**What's needed**: RSS/Atom feed adapter. Polls on schedule, ingests new articles into appropriate domain.

**Files**: `src/llm_wiki/adapters/rss.py`
**Estimated effort**: 4-6 hours.

---

### V5-4: Multi-agent session coverage (deferred)

**Status**: Deferred per `roadmap-deferred.md`.

**What's needed**: Adapters for Gemini CLI sessions and Ollama sessions, following the pattern of `ClaudeSessionAdapter`.

**Files**: `src/llm_wiki/adapters/gemini.py`, `src/llm_wiki/adapters/ollama.py`
**Estimated effort**: ~200 lines.

---

## Explicitly Dropped Features

These were considered and dropped — see `roadmap-deferred.md` for rationale.

| Feature | Reason dropped |
|---------|---------------|
| Multi-tenant SaaS / authentication | Out of scope for local-first single-user system |
| Autonomous internet crawling at scale | Risks stale content and resource waste; bounded online ingestion is sufficient |
| Perfect semantic search | BM25 + vector hybrid is sufficient; heavy NLU models are not local-first |

---

## Recommended Phase Sequencing

```
NOW: Fix P0 reliability issues (1-2 days)
  → Atomic writes (P0-1)
  → Index write mutex (P0-2)
  → Recover stuck files (P0-3)
  → LLM timeout (P0-4)

NEXT: HTTP API (3-5 days)
  → FastAPI + uvicorn optional dep
  → Core routes: health, search, ingest, jobs
  → Bearer token auth

THEN: V2 Trust Layer (1-2 weeks)
  → Confidence fields on claims
  → Source citation enforcement
  → Stale-page improvements
  → Orphan page checks
  → Candidate approval flow

THEN: V3 Cross-Domain Synthesis (1-2 weeks)
  → Community detection (Louvain)
  → Cross-domain summary pages
  → Per-domain dashboards

LATER: V4 UX (2-3 weeks)
  → Graph visualization
  → Browse by entity/concept
  → Daemon control panel

OPTIONAL: V5 Online Integrations
  → GitHub, docs sites, RSS (as needed)
```

---

## Deferred Items Summary

From `roadmap-deferred.md` — items with concrete pre-requisites and effort estimates:

| Item | Phase | Effort | Pre-requisite |
|------|-------|--------|--------------|
| Community Detection (Louvain) | post-Phase-2 | ~300 lines | graph edges (exists) |
| Synthesis Cache | post-Phase-3 | ~400 lines | unified search (done) |
| Talk Pages | post-Phase-2 | ~100 lines | wiki indexer companion pages |
| Cross-Domain Summary Pages | post-Phase-2 | ~200 lines | cross-domain edges |
| Per-Domain Schemas | post-Phase-2 | ~150 lines | config-driven loading |
| Topic Archive Lifecycle | post-Phase-2 | ~200 lines | page lifecycle states |
| GraphViz Export | post-Phase-2 | ~50 lines | graph UI covers this |
| Multi-Agent Session Coverage | post-Phase-2 | ~200 lines | adapter pattern (exists) |
| Volume/Journal Management | post-Phase-2 | ~200 lines | page model |
| Plugin Architecture | post-Phase-3 | ~150 lines | community existence |

None of these are needed for 100% readiness. All can be implemented independently once Phase 0-2 foundation is in place.

# Roadmap: Deferred & Dropped Items

Decision log for items explicitly deferred or dropped from the LLM Wiki roadmap. Each entry includes the rationale so future contributors can reconsider without re-deriving the analysis.

## Dropped Items

### Autonomous Internet Crawling
- **Scope**: Crawling the open internet at scale for knowledge ingestion
- **Decision**: Dropped
- **Reason**: Out of scope for a local-first knowledge store. Bounded, configurable online ingestion (GitHub, RSS, docs sites) is sufficient. Unbounded crawling risks stale content, hallucination feedback loops, and resource waste
- **Slashes out of Product Brief**: "Autonomous internet crawling at scale" is explicitly out

### Multi-tenant SaaS
- **Scope**: Authentication, multi-user access, remote hosting
- **Decision**: Dropped
- **Reason**: The system is designed as a local-first, single-user knowledge store. Multi-tenancy is orthogonal to the core value proposition

### Perfect Semantic Search
- **Scope**:追求与自然语言理解等额的语义搜索
- **Decision**: Dropped
- **Reason**: BM25 + vector hybrid approach is sufficient for the domain. Natural language understanding requires heavy models not suited to a local-first knowledge store

## Deferred Items

### Community Detection (Louvain) — Job 16
- **Phase**: Deferred to post-Phase-2
- **Reason**: Nice-to-have for auto-suggesting domain boundaries, but not needed for 100% readiness. Graph edges already exist and provide the foundation
- **Pre-requisite**: `index/graph_edges.py` already exists with edge data
- **Effort**: ~300 lines
- **File**: `src/llm_wiki/governance/community.py`

### Synthesis Cache (Gap 28)
- **Phase**: Deferred to post-Phase-3
- **Reason**: Useful at scale (>10k pages, >100 queries/day). Adds a service layer where records high-value queries and auto-expands wiki where gaps are found.
- **Pre-requisite**: Requires unified search (BM25 + vector)
- **Effort**: ~400 lines
- **File**: Would need `src/llm_wiki/cache.py`

### Talk Pages (Gap 29)
- **Phase**: Deferred to post-Phase-2
- **Reason**: Companion discussion files for each page, useful for human-in-the-loop review
- **Pre-requisite**: Wiki indexer supports companion pages
- **Effort**: ~100 lines
- **File**: `src/llm_wiki/talk.py`

### Cross-Domain Summary Pages (Job 9)
- **Phase**: Deferred to post-Phase-2
- **Reason**: Auto-generated from entities appearing in multiple domains. Useful for cross-domain reasoning but requires cross-domain edges to be populated first
- **Pre-requisite**: `index/relationships.py` for entity-crossing edges
- **Effort**: ~200 lines
- **File**: `src/llm_wiki/cross_domain.py`

### Per-Domain Schemas (Job 12)
- **Phase**: Deferred to post-Phase-2
- **Reason**: Policies, tags, ingestion rules per domain. Useful for enterprise deployments but not needed for single-user local-first mode
- **Pre-requisite**: Config-driven loading of per-domain schemas
- **Effort**: ~150 lines
- **File**: `src/llm_wiki/config/schemas.py`

### Topic Archive Lifecycle (Job 13)
- **Phase**: Deferred to post-Phase-2
- **Reason**: Old topics amortize, preserve but out of normal context
- **Pre-requisite**: Page lifecycle states (active, archived, dormant)
- **Effort**: ~200 lines
- **File**: `src/llm_wiki/archive.py`
- **Effort**: ~200 lines
- **File**: `src/llm_wiki/archive.py`

### GraphViz Export (Gap 31)
- **Phase**: Deferred post-Phase-2
- **Reason**: DOT format export for graph visualization. Nice for static sharing but the Web UI Job 15 will handle this natively. Worth implementing only if GraphViz CLI tooling is needed outside the UI
- **Pre-requisite**: `export/graph.py` already exports viz in the UI
- **Effort**: ~50 lines
- **File**: `src/llm_wiki/export/graphviz.py`

### Multi-Agent Session Coverage (Gap 30) — Gemini CLI & Ollama
- **Phase**: Deferred to post-Phase-2
- **Reason**: Gemini CLI session adapter and Ollama session adapter. Useful for expanding ingest sources
- **Pre-requisite**: `adapters/base.py` and `adapters/obsidian.py` for pattern reference
- **Effort**: ~200 lines
- **File**: `src/llm_wiki/adapters/gemini.py`, `src/llm_wiki/adapters/ollama.py`

### Volume (V) / Journal (J) Management
- **Phase**: Deferred to post-Phase-2
- **Reason**: Named collections of related pages for "tracking goals over time" and "research deep-dives" use cases. Useful but non-critical
- **Pre-requisite**: Page model in `models/page.py`
- **Effort**: ~200 lines
- **File**: `src/llm_wiki/volume.py`

### Plugin Architecture (Gap 31)
- **Phase**: Deferred to post-Phase-3
- **Reason**: Plugin loader/discovery mechanism for community extensions. Only needed once the system has a community. Simple adapter hooks are sufficient for first release
- **Pre-requisite**: `adapters/base.py` the plugin discovery mechanism
- **Effort**: ~150 lines
- **File**: Could be a separate package `llm-wiki-plugins`

## Summary

| Category | Dropped | Deferred |
|----------|---------|----------|
| Count  | 3  | 9 |
| Items  | Auth/SaaS, Auto-c rawling, Perfect semantic search | Community detection, Synthesis cache, Talk pages, Cross-domain summaries, Per-domain schemas, Topic archive, GraphViz export, Multi-agent coverage, Volume/Journal, Plugin architecture |

The deferred items represent genuine value-adds but none are needed for 100% readiness. They can each be implemented independently once the Phase 0-2 foundation is in place.

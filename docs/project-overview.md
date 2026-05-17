# LLM Wiki — Project Overview

## What Is LLM Wiki?

LLM Wiki is a **git-ops, local-first, file-backed federated wiki** governed by a background daemon. It is a structured knowledge layer for AI agents — the layer between raw files on disk and the intelligent queries agents need to answer.

Unlike RAG (which re-derives answers from scratch each query), LLM Wiki **accumulates knowledge**. When a new source arrives, the daemon reads it, extracts entities and claims, integrates it with existing pages, flags contradictions, and keeps the knowledge base current. Knowledge compounds over time: cross-references are pre-built, synthesis is pre-computed, and every new source makes everything richer.

## Core Design Principles

| Principle | Description |
|-----------|-------------|
| **Local-first** | All storage is files on disk. No external database required. The wiki works offline. |
| **Git-ops** | Every change is a file edit. The wiki is fully versionable, diffable, and auditable via `git`. |
| **Federated domains** | One daemon, one index loop, one governance pipeline — but many bounded domain namespaces. Knowledge stays scoped; cross-domain synthesis is explicit. |
| **Daemon-driven** | A background `APScheduler` daemon handles ingestion, governance, export, and promotion on a schedule. Agents interact through CLI commands or (soon) HTTP API. |
| **Agent-native** | Designed primarily as a knowledge store for AI agent harnesses. Exports in `llms.txt` format (the AI-readable standard). |
| **Accumulative, not reactive** | Unlike RAG, LLM Wiki builds a persistent, growing knowledge graph that becomes more valuable over time. |

## Primary Use Cases

1. **Agent knowledge store**: An AI agent harness (e.g., an Anthropic agent using Honcho) queries the wiki for structured facts, claims, and relationships rather than re-deriving from raw documents each time.
2. **Personal knowledge management**: Ingest notes, sessions, and documents; the daemon organizes and cross-references them automatically.
3. **Multi-source synthesis**: Combine knowledge from Claude Code sessions, Obsidian vaults, markdown documents, and plain text into a single queryable knowledge graph.

## Who Uses This?

- **Primary**: Marc Montecalvo — building an agent harness that queries this knowledge store alongside Honcho.
- **Secondary**: Developers building agent harnesses who need a structured knowledge base that compounds over time.

## Current State (v0.1.0)

- **Phase completed**: V1 (core system) + Phase 1.1 (Vector/Semantic Search)
- **Tests**: 1,106 passing, 0 failures
- **Coverage**: ~93%
- **Lint**: 0 ruff errors, mypy clean
- **CLI commands**: 50+ commands across 15 command groups
- **Daemon jobs**: 9 scheduled jobs (inbox poll, governance, export, index rebuild, promotion, review queue, etc.)

## Tech Stack Summary

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Package manager | uv (hatchling build) |
| CLI | Click |
| Daemon loop | APScheduler `BackgroundScheduler` + `ThreadPoolExecutor` |
| Config | Pydantic + YAML |
| Storage | Markdown + frontmatter + JSON indexes |
| Fulltext search | TF-IDF inverted index |
| Vector search | FAISS `IndexFlatL2` + `sentence-transformers` |
| LLM abstraction | OpenAI-compatible API |
| CI | GitHub Actions (ruff, mypy, pytest) |

## Key Subsystems

```
Ingest ──► Adapters ──► Normalizer ──► Router ──► Queue
                                                    │
                                          DeterministicIntegrator
                                                    │
                                         Extraction (LLM-led)
                                                    │
                                          Index Updates ──► Search
                                                    │
                                         Export + Governance
```

### Adapters
Normalize diverse input formats: Markdown, plain text, Obsidian vaults, Claude Code session transcripts.

### Extraction
LLM-powered extraction of tags, summaries, claims, entities, concepts, relationships, and QA pairs from ingested content.

### Indexing
Four live indexes maintained by the daemon: TF-IDF fulltext, FAISS vector (semantic), metadata (tag/kind/domain), backlinks (reverse link tracking).

### Governance
Automated lint, staleness detection, contradiction detection, duplicate detection, routing mistake detection, and quality scoring.

### Export
Generates LLM-optimized formats: `llms.txt`, `llms-full.txt`, JSON sidecars, graph (nodes+edges), and XML sitemap.

## Configured Domains

| Domain | Purpose |
|--------|---------|
| `vulpine-solutions` | Work/consulting knowledge |
| `home-assistant` | Home automation configuration |
| `homelab` | Homelab infrastructure notes |
| `personal` | Personal notes and reference |
| `general` | General-purpose fallback |

## What's Next

See `ROADMAP_REMAINING.md` (in `docs/bmad/`) for the full prioritized roadmap. Key next steps:

1. **P0 reliability**: Atomic index writes, concurrency mutex, stuck-file recovery, LLM call timeouts
2. **HTTP API**: FastAPI optional dep, daemon serves routes for health/search/ingest/jobs
3. **V2 Trust Layer**: Confidence scoring, source citation enforcement, stale-page improvements
4. **V3 Cross-Domain**: Community detection, cross-domain summary pages, per-domain dashboards

## Related Documents

- [`architecture.md`](architecture.md) — System architecture and component relationships
- [`data-models.md`](data-models.md) — Pydantic schemas, storage formats, index structures
- [`development-guide.md`](development-guide.md) — Setup, workflow, testing, contributing
- [`deployment-guide.md`](deployment-guide.md) — Daemon operation, config, production setup
- [`source-tree-analysis.md`](source-tree-analysis.md) — Module-by-module code walkthrough
- [`docs/bmad/PROJECT_STATUS.md`](bmad/PROJECT_STATUS.md) — Full status, known issues, tech debt
- [`docs/bmad/ROADMAP_REMAINING.md`](bmad/ROADMAP_REMAINING.md) — Prioritized remaining work

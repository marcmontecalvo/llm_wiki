# LLM Wiki — Documentation Index

**Project**: LLM Wiki v0.1.0 · Python 3.11+ · CLI + Library
**Generated**: 2026-05-16 (exhaustive scan, 80 source files)
**Status**: V1 + Phase 1.1 (Vector Search) complete · 1,106 tests · ~93% coverage

---

## Start Here

| Document | What it answers |
|----------|----------------|
| [project-overview.md](project-overview.md) | What is this? Who is it for? What can it do? |
| [ARCHITECTURE.md](ARCHITECTURE.md) | How do the pieces fit together? Data flow diagrams, component breakdown |
| [development-guide.md](development-guide.md) | How do I set up, run tests, add features? |
| [deployment-guide.md](deployment-guide.md) | How do I run the daemon in production? systemd, launchd, config |
| [data-models.md](data-models.md) | What are the Pydantic schemas and JSON storage formats? |
| [source-tree-analysis.md](source-tree-analysis.md) | Module-by-module walkthrough of 80 source files |

---

## Reference Documentation

### Existing Docs (pre-scan)

| Document | Contents |
|----------|---------|
| [CLI.md](CLI.md) | Complete CLI command reference for all 50+ commands |
| [CONFIG.md](CONFIG.md) | Configuration YAML schemas and all options |
| [GOVERNANCE.md](GOVERNANCE.md) | Governance pipeline: lint, staleness, quality, contradictions |
| [EXPORTS.md](EXPORTS.md) | Export formats: llms.txt, graph, sitemap, JSON sidecars |
| [PROMOTION.md](PROMOTION.md) | Promotion scoring algorithm and workflow |
| [CONTRADICTION_DETECTION.md](CONTRADICTION_DETECTION.md) | Contradiction detection strategies and examples |
| [CONTRADICTION_QUICK_START.md](CONTRADICTION_QUICK_START.md) | Quick start guide for contradiction detection |
| [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) | 2026-04-23 architecture review; ADR-001 (HTTP API); known issues |
| [SETUP.md](SETUP.md) | Quick setup guide (uv sync, init, provider config) |
| [AGENT_CONVENTIONS.md](AGENT_CONVENTIONS.md) | Cross-agent conventions for agent harness integration |
| [AGENT_SUPPORT_MATRIX.md](AGENT_SUPPORT_MATRIX.md) | Which agents/providers are supported and how |
| [COPILOT_SETUP.md](COPILOT_SETUP.md) | GitHub Copilot integration setup |
| [CURSOR_SETUP.md](CURSOR_SETUP.md) | Cursor IDE integration and rules |
| [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) | Implementation status checklist |

---

## Project Status and Roadmap

| Document | Contents |
|----------|---------|
| [bmad/PROJECT_STATUS.md](bmad/PROJECT_STATUS.md) | Full V1+Phase 1.1 status; tech stack; known issues; completed features |
| [bmad/ROADMAP_REMAINING.md](bmad/ROADMAP_REMAINING.md) | P0-P5 prioritized work: atomic writes → HTTP API → V2-V5 |
| [bmad/SESSION_REPORT_2026-05-16.md](bmad/SESSION_REPORT_2026-05-16.md) | Session report for Phase 1.1 (vector search, error hierarchy, lint) |
| [Product_Brief.md](Product_Brief.md) | Full product brief with V2-V5 roadmap vision |
| [roadmap.md](roadmap.md) | Roadmap overview |
| [roadmap-deferred.md](roadmap-deferred.md) | Deferred/dropped features with rationale |

---

## Architecture Details

### System Architecture
- **Runtime**: Python 3.11+, APScheduler + ThreadPoolExecutor (max 2 workers)
- **Storage**: Files on disk — markdown + YAML frontmatter + JSON indexes
- **Search**: TF-IDF fulltext + FAISS vector (384-dim, all-MiniLM-L6-v2) + RRF fusion
- **LLM**: OpenAI-compatible API (OpenAI, Anthropic, Ollama, LM Studio, Claude Agent SDK)

### Key Modules

```
src/llm_wiki/
├── cli.py            → 50+ CLI commands (Click)
├── adapters/         → Markdown, Text, Obsidian, Claude session adapters
├── daemon/           → APScheduler daemon + 9 scheduled jobs
├── extraction/       → LLM-led claims/entities/concepts/relationships/QA
├── governance/       → Lint, staleness, quality, contradictions, duplicates
├── index/            → Fulltext (TF-IDF), Vector (FAISS), Metadata, Backlinks, Graph
├── ingest/           → Inbox watcher, normalizer, domain router
├── integration/      → DeterministicIntegrator (merge strategies + rollback)
├── models/           → Pydantic schemas + LLM client
├── promotion/        → Scoring + engine for cross-domain promotion
├── query/            → WikiQuery: unified search with RRF fusion
└── review/           → Review queue lifecycle
```

### Data Flow
```
new file → Adapter → Normalizer → Router → Queue
                                             ↓
                                  DeterministicIntegrator
                                             ↓
                                  LLM Extraction pipeline
                                             ↓
                              5 index writes (fulltext/vector/metadata/backlinks/graph)
                                             ↓
                               Governance + Export (60min)
```

---

## Configuration Files

| File | Purpose |
|------|---------|
| `config/daemon.yaml` | Scheduling intervals, worker count, log level |
| `config/domains.yaml` | Domain definitions (5 configured: vulpine-solutions, home-assistant, homelab, personal, general) |
| `config/models.yaml` | LLM provider config per task (extraction, integration, lint) |
| `config/routing.yaml` | Source path → domain routing rules |

---

## Daemon Jobs

| Job | Interval | Purpose |
|-----|----------|---------|
| Inbox scan | 15s | Pick up new files from `inbox/new/` |
| Queue-to-pages | 15min | Promote queued pages to `pages/` |
| Retry failed ingests | 30min | Retry previously failed ingestions |
| Index rebuild | 30min | Full rebuild of all 5 indexes |
| Export | 60min | Re-generate llms.txt, graph, sitemap |
| Governance/lint | 60min | Run all governance checks, write report |
| Review queue | 60min | Score and populate review queue |
| Staleness check | 24h | Flag outdated time-sensitive content |
| Duplicate detection | 24h | Find near-duplicate pages |

---

## Known Issues (P0 — Fix Before V2)

| Issue | Severity | Location |
|-------|----------|---------|
| Non-atomic JSON index writes | Critical | `index/*.py:save()` |
| No write mutex for concurrent jobs | High | All index files |
| Stuck `inbox/processing/` files | High | `ingest/watcher.py` |
| LLM calls lack timeout | High | `models/client.py` |

Full remediation plan: [bmad/ROADMAP_REMAINING.md](bmad/ROADMAP_REMAINING.md)

---

## Quick Commands

```bash
# Setup
uv sync && uv run llm-wiki init

# Run tests
uv run pytest

# Start daemon
uv run llm-wiki daemon start

# Search
uv run llm-wiki search query "how does X work"

# Ingest a file
uv run llm-wiki ingest file path/to/doc.md

# Governance check
uv run llm-wiki govern check

# Rebuild indexes
uv run llm-wiki trigger index-rebuild

# Install Claude Code session hooks
uv run llm-wiki hooks install --scope project
```

---

## Optional Dependencies

| Extra | Install | Adds |
|-------|---------|------|
| `[vector]` | `uv sync --extra vector` | FAISS vector search + sentence-transformers |
| `[claude-agent]` | `uv sync --extra claude-agent` | Claude Agent SDK LLM provider |

Without `[vector]`: fulltext search still works; vector calls silently no-op.

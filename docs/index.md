# LLM Wiki — Documentation Index

**Project**: LLM Wiki v0.1.0 · Python 3.11+ · CLI + Library
**Status**: Feature-complete (all core Epics done) · 1,617 tests · ~93% coverage

---

## Start Here

| Document | What it answers |
|----------|----------------|
| [project-overview.md](project-overview.md) | What is this? Who is it for? What can it do? |
| [_bmad-output/planning-artifacts/architecture.md](../planning-artifacts/architecture.md) | How do the pieces fit together? Data flow diagrams, component breakdown |
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
| [bmad/PROJECT_STATUS.md](bmad/PROJECT_STATUS.md) | Current status; tech stack; completed features |
| [bmad/ROADMAP_REMAINING.md](bmad/ROADMAP_REMAINING.md) | Remaining work prioritization |
| [bmad/SESSION_REPORT_2026-05-16.md](bmad/SESSION_REPORT_2026-05-16.md) | Session report for Phase 1.1 (vector search, error hierarchy, lint) |
| [Product_Brief.md](Product_Brief.md) | Full product brief with roadmap vision |

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
├── adapters/         → Markdown, Text, Obsidian, session transcript adapters
├── api/              → FastAPI app, REST routers, MCP server, web UI routes, TUI
├── changelog/        → Append-only page mutation log
├── config/           → YAML config loading and validation
├── daemon/           → APScheduler daemon + 12 scheduled jobs
├── extraction/       → LLM-led and heuristic claims/entities/concepts extraction
├── governance/       → Lint, staleness, quality, contradictions, duplicates, routing
├── index/            → Fulltext (TF-IDF), Vector (FAISS), Metadata, Backlinks, Graph, Relationships
├── ingest/           → Inbox watcher, normalizer, domain router, trust tagging
├── integration/      → DeterministicIntegrator (merge strategies + rollback)
├── models/           → Pydantic schemas + LLM client
├── observability/    → OpenTelemetry metrics, Prometheus, structured logging
├── promotion/        → Authority scoring, cross-domain promotion engine
├── query/            → WikiQuery: unified search with RRF fusion
├── review/           → Review queue lifecycle
├── synthesis/        → Authority scoring, cache, cross-domain synthesis engine
├── templates/        → Jinja2 HTML templates (web UI)
└── utils/            → Frontmatter parsing, ID generation
```

### Data Flow
```
new file → Adapter → Normalizer → Router → Queue
                                             ↓
                                  DeterministicIntegrator
                                             ↓
                                  Extraction pipeline (trust-tagged claims)
                                             ↓
                              6 index writes (fulltext/vector/metadata/backlinks/graph/relationships)
                                             ↓
                               Governance + Export (60min) → Synthesis cache (6h)
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
| Queue-to-pages | 15min | Promote staged candidates to wiki pages |
| Retry failed ingests | 30min | Retry previously failed ingestions |
| Index rebuild | 30min | Full rebuild of all 6 indexes |
| Export | 60min | Re-generate llms.txt, graph, sitemap |
| Governance/lint | 60min | Run all governance checks, write report |
| Review queue | 60min | Score and populate review queue |
| Cross-domain summary | 6h | Generate cross-domain entity summaries |
| Synthesis cache | 6h | Cache high-value repeated queries |
| Staleness check | 24h | Flag outdated time-sensitive content |
| Duplicate detection | 24h | Find near-duplicate pages |
| Promotion | 24h | Score/score cross-domain promotion candidates |

---

## Remaining Work

Most core features are complete. Remaining high-priority items are documented in [bmad/ROADMAP_REMAINING.md](bmad/ROADMAP_REMAINING.md).

Notable areas for future development:
- **Honcho integration** (new Epic planned) — formal data pipeline between Honcho session memory and LLM Wiki compiled knowledge
- **E2E integration tests** — coverage for the full Docker stack, MCP → harness workflow
- **Web UI hardening** — Epic 4 templates are scaffolding; interactive features need implementation
- **API auth** — optional Bearer token auth for the REST API when network exposure is needed

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
uv run llm-wiki govern run index-rebuild

# Install Claude Code session hooks
uv run llm-wiki hooks install --scope project
```

---

## Optional Dependencies

| Extra | Install | Adds |
|-------|---------|------|
| `[claude-agent]` | `uv sync --extra claude-agent` | Claude Agent SDK LLM provider |

**Vector search** (FAISS + sentence-transformers) is a core dependency — always available without `--extra`.

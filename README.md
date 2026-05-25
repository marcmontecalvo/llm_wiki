# LLM Wiki

A daemon-governed knowledge service for AI agent harnesses. Runs as a Docker container and exposes MCP (Streamable HTTP), REST, and CLI interfaces. Knowledge is authored, maintained, and governed automatically by a background daemon — not by humans.

## How it fits in the stack

LLM Wiki sits alongside [Honcho](https://github.com/plastic-labs/honcho) (agent memory infrastructure) and your agent harness (e.g., Homefront, Claude Code, OpenCode) as layer three in a compound AI system:

| Layer           | Tool                               | Purpose                                                      |
| --------------- | ---------------------------------- | ------------------------------------------------------------ |
| Agent harness   | Homefront, Claude Code, etc.       | Orchestrates agent behavior and tool use                     |
| Session memory  | Honcho                             | Conversational context, peer representations, session continuity |
| Knowledge store | **LLM Wiki**                       | Compiled, governed domain knowledge that compounds over time |

Honcho answers "what were we just talking about?" — LLM Wiki answers "what do we know about X?" Honcho stores raw conversations and derives representations; LLM Wiki stores *processed, verified facts* with source provenance, contradiction detection, and authority scoring, not re-derived from scratch on every query.

**The data flow:** conversations are stored in Honcho for recent context; LLM Wiki ingests excerpts (via Claude Code hooks, API, or manual drop) and produces structured, governed wiki pages. The synthesized wiki pages can then be injected back into Honcho as enriched session context.

## Quick start

### Docker (recommended)

```bash
# Build and start the full stack
docker-compose up --build -d

# Wait for both services to become healthy
until curl -sf http://localhost:3050/v1/health; do sleep 2; done

# Point your MCP client at:
# http://localhost:3050/mcp  (Streamable HTTP)

# Or use the CLI directly
uv run llm-wiki health
uv run llm-wiki query "homelab network topology"
```

First-run auto-initializes the wiki directory structure. No manual `init` required.

Before first use, ensure `wiki_system` is owned by uid 1000:

```bash
mkdir -p wiki_system && sudo chown -R 1000:1000 wiki_system
```

### Local development

```bash
uv sync --extra vector       # include FAISS + sentence-transformers
uv run llm-wiki health       # CLI health check
uv run pytest                # run test suite
```

## Deployment

Each household runs its own isolated instance on a dedicated VM alongside Homefront (agent harness) and Honcho (session memory). The docker-compose file controls port exposure — the service binds to `0.0.0.0` inside the container; network isolation is at the VM and compose level.

Honcho and LLM Wiki are purpose-built for different layers: Honcho stores raw conversations and derives peer representations; LLM Wiki stores parsed, verified facts with source provenance. When configured, LLM Wiki can push its export bundle into Honcho's session context, and pull conclusions from Honcho into the wiki inbox — the agent harness is the mediator.

### Honcho Configuration

Enable auto-push of wiki exports to Honcho in `config/daemon.yaml`:

```yaml
features:
  honcho_push: true       # Enable Honcho push daemon job

honcho:
  workspace_id: default   # Honcho workspace for local push
  push_url: null          # Remote Honcho URL (e.g. http://honcho:8000)
  push_api_key: null      # API key for remote push authentication
```

Check Honcho connectivity: `GET /v1/honcho/status` or `curl http://host:3050/v1/honcho/status`.

```yaml
# docker-compose.yml (example)
services:
  llm-wiki:
    build: .
    ports:
      - "127.0.0.1:3050:3050"   # expose to host only
    volumes:
      - ./wiki_system:/wiki_system
      - ./config:/config:ro
```

## Interfaces

| Interface             | Endpoint               | Use                       |
| --------------------- | ---------------------- | ------------------------- |
| MCP (Streamable HTTP) | `http://host:3050/mcp` | Agent harnesses           |
| MCP (stdio)           | process spawn          | Local harness integration |
| REST                  | `http://host:3050/v1/` | Programmatic / scripts    |
| CLI                   | `uv run llm-wiki`      | Operator control          |

## MCP tools

| Tool            | Description                                                 |
| --------------- | ----------------------------------------------------------- |
| `query`         | Retrieve knowledge at three depths: quick / standard / deep |
| `ingest`        | Submit a source; returns `job_id`                           |
| `ingest_status` | Poll ingest job by `job_id`                                 |
| `search`        | Full-text + vector search                                   |
| `read_page`     | Fetch a single page by ID or slug                           |
| `list_pages`    | List pages by domain, kind, or tag                          |
| `export`        | Trigger or retrieve exports                                 |

## Feature flags

Controlled via `config/daemon.yaml`:

```yaml
features:
  llm_extraction: false      # LLM-assisted tag/summary/claim extraction (off by default)
  vector_search: true        # sentence-transformers semantic search
  synthesis_cache: false     # cache repeated query answers as wiki pages
  cross_domain_promotion: false  # auto-promote shared entities across domains
```

When `llm_extraction: false`, the system runs fully without any LLM — heuristic tag extraction, first-paragraph summaries, algorithmic contradiction detection. Enable it to get LLM-quality claim extraction, confidence scoring, and richer summaries.

LLM provider configured in `config/models.yaml`:

```yaml
extraction:
  provider: anthropic        # anthropic | openai | openrouter | local
  model: claude-haiku-4-5-20251001
  api_key_env: ANTHROPIC_API_KEY
  base_url: null             # null = provider default; set for openrouter or local vLLM
```

## Multi-user households

Domains carry a `scope` field:

```yaml
# config/domains.yaml
domains:
  - name: household
    scope: shared          # visible to all members
  - name: user-marc
    scope: personal
    owner: marc
```

Queries default to household + the requesting user's personal domain merged. Pass `domain: household` to restrict to shared knowledge, or `domain: user-{id}` for personal only.

## Daemon jobs

| Job            | Interval | Purpose                                           |
| -------------- | -------- | ------------------------------------------------- |
| Inbox scan     | 15s      | Pick up new files                                 |
| Queue to pages | 15min    | Promote queued content                            |
| Retry failed   | 30min    | Retry previously failed ingest jobs               |
| Index rebuild  | 30min    | Rebuild all search indexes + reload FAISS         |
| Governance     | 60min    | Lint, contradiction detection, staleness, routing |
| Export         | 60min    | Regenerate llms.txt, JSON-LD, graph               |
| Review queue   | 60min    | Surface review candidates                         |
| Staleness      | 24h      | Flag outdated pages                               |
| Duplicates     | 24h      | Near-duplicate detection                          |
| Promotion      | 24h      | Score pages for cross-domain promotion            |
| Honcho push    | 60min* | Push wiki export bundle to Honcho (if `honcho_push: true`) |

## Configuration files

All mounted read-only at `/config` in the container:

| File           | Purpose                                       |
| -------------- | --------------------------------------------- |
| `daemon.yaml`  | Job schedules, feature flags, daemon config   |
| `domains.yaml` | Domain definitions, scope, routing thresholds |
| `models.yaml`  | LLM provider config for optional extraction   |
| `routing.yaml` | Source path → domain routing rules            |

Config changes take effect on container restart — no rebuild required.

## Development

```bash
uv sync --extra vector    # include FAISS + sentence-transformers
uv run pytest             # run test suite (unit + integration; excludes performance)
uv run ruff check .       # lint
uv run mypy src/          # type check
```

### Performance tests

Performance tests are tagged `@pytest.mark.performance` and excluded from the default run
(they seed a 100-page wiki and assert on wall-clock latency — unsuitable for fast CI loops).

```bash
# Run performance baseline tests explicitly
uv run pytest -m performance

# Run a single performance test
uv run pytest -m performance tests/performance/test_query_latency.py::test_quick_query_under_200ms
```

Latency budgets (NFR-P1/P2/P3):

| Depth    | Budget                              |
| -------- | ----------------------------------- |
| quick    | ≤ 200ms                             |
| standard | ≤ 2s                                |
| deep     | ≤ 30s (submit + poll to completion) |

The deep test uses `httpx.AsyncClient` with `ASGITransport` so `asyncio.create_task()`
background jobs share the event loop and complete within the timeout window.

## Documentation

- `_bmad-output/planning-artifacts/architecture.md` — authoritative architecture document
- `_bmad-output/planning-artifacts/prd.md` — product requirements
- `_bmad-output/planning-artifacts/epics.md` — epic and story breakdown
- `docs/CLI.md` — full CLI reference
- `docs/CONFIG.md` — config file reference
- `docs/GOVERNANCE.md` — governance and maintenance
- `docs/EXPORTS.md` — export formats
- `docs/SETUP.md` — detailed setup guide

## Current status

**v0.1.0 — Feature-complete**

All core features are implemented and tested: Docker container, MCP server (Streamable HTTP + stdio), REST API, CLI, daemon with 13+ scheduled jobs, governance pipeline, trust/confidence scoring, cross-domain entity promotion, synthesis cache, per-domain dashboards, topic archive lifecycle, web UI, TUI, and Honcho integration (detect, push, pull).

1,632 tests passing (93% coverage). See `_bmad-output/planning-artifacts/epics.md` for the full epic breakdown showing all epics complete.

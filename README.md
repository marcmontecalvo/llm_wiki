# LLM Wiki

A daemon-governed knowledge service for AI agent harnesses. Runs as a Docker container and exposes MCP (Streamable HTTP), REST, and CLI interfaces. Knowledge is authored, maintained, and governed automatically by a background daemon — not by humans.

## How it fits in the stack

| Layer | Tool | Purpose |
|-------|------|---------|
| Agent harness | Homefront (and others) | Orchestrates agent behavior and tool use |
| Session memory | Honcho | Conversational context and continuity |
| Knowledge store | **LLM Wiki** | Compiled, governed domain knowledge that compounds over time |

Honcho answers "what were we just talking about?" — LLM Wiki answers "what do we know about X?" Pre-synthesized, with provenance and contradiction awareness, not re-derived from scratch on every query.

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

Before first use, ensure `wiki_data` is owned by uid 1000:

```bash
mkdir -p wiki_data && sudo chown -R 1000:1000 wiki_data
```

### Local development

```bash
uv sync --extra vector       # include FAISS + sentence-transformers
uv run llm-wiki health       # CLI health check
uv run pytest                # run test suite
```

## Deployment

Each household runs its own isolated instance on a dedicated VM alongside Homefront and Honcho. The docker-compose file controls port exposure — the service binds to `0.0.0.0` inside the container; network isolation is at the VM and compose level.

```yaml
# docker-compose.yml (example)
services:
  llm-wiki:
    build: .
    ports:
      - "127.0.0.1:3050:3050"   # expose to host only
    volumes:
      - ./wiki_data:/wiki
      - ./config:/config:ro
```

## Interfaces

| Interface | Endpoint | Use |
|-----------|----------|-----|
| MCP (Streamable HTTP) | `http://host:3050/mcp` | Agent harnesses |
| MCP (stdio) | process spawn | Local harness integration |
| REST | `http://host:3050/v1/` | Programmatic / scripts |
| CLI | `uv run llm-wiki` | Operator control |

## MCP tools

| Tool | Description |
|------|-------------|
| `query` | Retrieve knowledge at three depths: quick / standard / deep |
| `ingest` | Submit a source; returns `job_id` |
| `ingest_status` | Poll ingest job by `job_id` |
| `search` | Full-text + vector search |
| `read_page` | Fetch a single page by ID or slug |
| `list_pages` | List pages by domain, kind, or tag |
| `export` | Trigger or retrieve exports |

## Feature flags

Controlled via `config/daemon.yaml`:

```yaml
features:
  llm_extraction: false      # LLM-assisted tag/summary/claim extraction (off by default)
  vector_search: true        # sentence-transformers semantic search
  synthesis_cache: false     # cache repeated query answers as wiki pages
  cross_domain_promotion: false  # auto-promote shared entities across domains
  lazy_vector_load: false    # defer FAISS load to first search call (faster cold start)
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

| Job | Interval | Purpose |
|-----|----------|---------|
| Inbox scan | 15s | Pick up new files |
| Queue to pages | 15min | Promote queued content |
| Retry failed | 30min | Retry previously failed ingest jobs |
| Index rebuild | 30min | Rebuild all search indexes + reload FAISS |
| Governance | 60min | Lint, contradiction detection, staleness, routing |
| Export | 60min | Regenerate llms.txt, JSON-LD, graph |
| Review queue | 60min | Surface review candidates |
| Staleness | 24h | Flag outdated pages |
| Duplicates | 24h | Near-duplicate detection |
| Promotion | 24h | Score pages for cross-domain promotion |

## Configuration files

All mounted read-only at `/config` in the container:

| File | Purpose |
|------|---------|
| `daemon.yaml` | Job schedules, feature flags, daemon config |
| `domains.yaml` | Domain definitions, scope, routing thresholds |
| `models.yaml` | LLM provider config for optional extraction |
| `routing.yaml` | Source path → domain routing rules |

Config changes take effect on container restart — no rebuild required.

## Development

```bash
uv sync --extra vector    # include FAISS + sentence-transformers
uv run pytest             # run test suite
uv run ruff check .       # lint
uv run mypy src/          # type check
```

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

**v0.1.0 — V1 library complete, service pivot in progress**

V1 core library is functionally complete (1106 tests, 93% coverage). Current work is the service pivot: Docker container, MCP server (Streamable HTTP), REST API, and daemon wiring into the container stack.

See `_bmad-output/planning-artifacts/epics.md` for the full sprint breakdown.

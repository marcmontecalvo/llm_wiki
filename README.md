# Federated LLM Wiki Base Repo

This repo is the starting point for a **daemon-governed, multi-domain LLM wiki system**.

Core decision:
- **Labhund/llm-wiki** is the model for the daemon, maintenance loop, and wiki governance.
- **nvk/llm-wiki** is the model for domain/project scoping, portable agent behavior, and wiki workflow conventions.
- **Pratiyush/llm-wiki** is the model for transcript/session ingest and machine-readable exports.
- **Ar9av/obsidian-wiki** is the model for cross-agent compatibility and skill/bootstrap wiring.

## Why this design

A pure skill-only wiki is too fragile. Behavior drifts by model, prompt, and tool discipline.
A daemon-only single-domain wiki is more stable, but it needs clean domain partitioning to avoid turning into one giant pile.

So the design here is:

- **one wiki system**
- **one shared daemon + index + governance loop**
- **many bounded domains**
- **one shared cross-domain graph**
- **one inbox + export pipeline**

That gives you consistency without forcing everything into one flat vault.

## Repos to borrow from

Primary:
- Labhund/llm-wiki: https://github.com/Labhund/llm-wiki
- nvk/llm-wiki: https://github.com/nvk/llm-wiki

Secondary:
- Pratiyush/llm-wiki: https://github.com/Pratiyush/llm-wiki
- Ar9av/obsidian-wiki: https://github.com/Ar9av/obsidian-wiki

Later-stage references:
- nashsu/llm_wiki: https://github.com/nashsu/llm_wiki
- lucasastorian/llmwiki: https://github.com/lucasastorian/llmwiki
- kenhuangus/llm-wiki: https://github.com/kenhuangus/llm-wiki

## Current repo signals checked on April 13, 2026

- **Labhund/llm-wiki**: active-development warning in README; agent-first daemon + MCP design.
- **nvk/llm-wiki**: active repo with releases and an open issue discussing automatic routing across topic wikis.
- **Pratiyush/llm-wiki**: ~76 stars, ~25 open issues; strong session adapter + export focus.
- **Ar9av/obsidian-wiki**: ~340 stars, 0 open issues; best cross-agent skill/bootstrap layer.
- **nashsu/llm_wiki**: ~1.1k stars, ~7 open issues; best later UI/product inspiration.
- **lucasastorian/llmwiki**: ~350+ stars, ~1 open issue; useful later if you want a heavier web app shell.
- **kenhuangus/llm-wiki**: ~15 stars, 0 open issues; too niche for core use.

## Repo shape

```text
src/
  daemon/         # background workers, scheduler, orchestration
  ingest/         # inbox routing, adapters, normalization
  index/          # fulltext index, graph index, metadata index
  query/          # retrieval, traversal, ranking
  governance/     # lint, review, contradiction checks, stale checks
  adapters/       # codex, claude, cursor, obsidian, manual docs
  models/         # prompts, schemas, extraction contracts
wiki_system/
  inbox/          # raw unclassified inputs
  domains/        # per-domain wiki spaces
  index/          # search indexes (metadata, fulltext)
  exports/        # llms.txt, json, graph, sitemap
  reports/        # governance reports
  logs/           # daemon logs, ingest logs, decisions
  state/          # queue state, checkpoints, worker state
config/
  domains.yaml
  daemon.yaml
  routing.yaml
  models.yaml
templates/
  page.md
  entity.md
  concept.md
  source.md
```

## First implementation target

Build **one local-first daemon** that can:
1. accept inputs into `wiki_system/inbox/`
2. route them to the right domain
3. normalize them into markdown
4. extract entities/claims/links
5. integrate them into domain wiki pages
6. update shared graph/index
7. emit machine-readable exports
8. run maintenance jobs on a schedule

## Domain model

Recommended initial domains:
- `vulpine-solutions`
- `home-assistant`
- `homelab`
- `personal`
- `general`

Do **not** start with 20 domains. Start with 4-6.

## Current Status

**✅ v0.1.0 - Core system complete!**

See `docs/IMPLEMENTATION_STATUS.md` for detailed status.

- 534 tests (93% coverage)
- Full CLI interface (`llm-wiki --help`)
- Complete ingestion, search, governance, and export pipeline
- CI/CD with GitHub Actions

## Getting Started

```bash
# Install dependencies
uv sync

# Initialize wiki
uv run llm-wiki init

# Run tests
uv run pytest

# Start daemon
uv run llm-wiki daemon
```

See `docs/SETUP.md` for detailed setup instructions.

## Build order (for understanding architecture)

Read these in order:
1. `docs/overview.md`
2. `docs/roadmap.md`
3. `docs/implementation_step_1.md`
4. `docs/implementation_step_2.md`
5. `docs/implementation_step_3.md`
6. `docs/implementation_step_4.md`
7. `docs/IMPLEMENTATION_STATUS.md` (current state)

## Non-goals for v1

- polished UI
- cloud multi-tenant auth
- perfect semantic search
- autonomous internet crawling at scale
- fully automatic cross-domain synthesis without review

## What success looks like

By the end of v1, this system should reliably:
- keep separate domains clean
- allow cross-domain search
- ingest agent transcripts and markdown notes
- survive model swaps without losing structure
- produce deterministic enough outputs to trust as a real substrate

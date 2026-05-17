# Product Brief: LLM Wiki

## Executive Summary

LLM Wiki is a structured, daemon-governed knowledge layer for AI agents — a bridge between raw files on disk and the intelligent queries your assistants need to answer. Most LLM + document systems today work like RAG: upload files, retrieve chunks at query time, derive the answer from scratch every session. Nothing accumulates. Ask a question that requires synthesizing five sources, and the LLM has to rediscover the same ground every time.

LLM Wiki solves this by compiling knowledge into a persistent, interlinked collection of domain-separated markdown files that the LLM maintains automatically. When a new source arrives, the system reads it, extracts entities and claims, integrates it into existing pages, flags contradictions, and keeps the knowledge base current. The wiki compounds — cross-references are pre-built, synthesis is pre-computed, and every new source makes everything richer.

This matters because your AI assistants need a reliable knowledge substrate — not a flat dump of files they guess their way through, but a structured, queryable, governed knowledge graph with explicit relationships and provenance. They can still access raw files directly, but now they also have a second, indexed layer they can reason about.

This system was built for your own agent harness — you're the primary user — but designed from the start as a general-purpose library so others can build on it too. It doesn't require Honcho or any specific agent to function. It works as a standalone knowledge store.

## The Problem

You already have a rich knowledge base scattered across tools — Claude Code session transcripts, homelab configuration files, software project notes, personal documentation. But you don't have a way for your AI helpers to reason about that knowledge well.

Flat file access means the LLM fumbles through directories, guessing what's relevant. RAG (retrieval-augmented generation) is better but still re-derives everything from scratch on every query. There's no accumulation, no cross-referencing, no maintenance between sessions. Claims get stale. Connections get missed.

You needed a structured knowledge layer that your AI assistant could query confidently — with provenance, with contradiction awareness, with domain context — without requiring a specific agent or framework to run.

## The Solution

LLM Wiki is a federated, daemon-governed knowledge store for AI agents. One shared daemon, one shared index, one governance loop, many bounded domains. Knowledge flows through a deterministic pipeline: inbox → route → normalize → extract → integrate → index → govern → export. The daemon runs maintenance jobs on schedule — linting, contradiction detection, staleness checks, export generation, index rebuilding — all automatically.

Your agent harness queries the wiki using CLI commands or direct library imports. The knowledge is structured, indexed, and governed so the agent gets ranked results with confidence scores, provenance links, and contradiction warnings instead of unranked parallel chunks.

## What Makes This Different

**Compounding knowledge**: The system writes and maintains the wiki. You source, explore, and ask questions. The LLM does the bookkeeping — cross-referencing, filing, flagging contradictions. Knowledge accumulates with every source.

**Domain separation with federation**: Unlike monolithic wikis that flatten everything into one vault, knowledge lives in bounded domains (vulpine-solutions, home-assistant, homelab, personal, general) with explicit cross-domain linking when warranted. Domains stay clean; shared knowledge flows through a promotion pipeline with quality gates.

**Agent-agnostic**: The wiki doesn't depend on Honcho, Claude Code, Cursor, or any specific tool. It ingests from many sources (session transcripts, markdown, Obsidian vaults) but serves its knowledge through a library interface and CLI that any agent harness can consume independently.

**Governance at the core**: Contradiction detection, duplicate detection, staleness detection, quality scoring, routing mistake detection — the system maintains its own health automatically. Not as an afterthought but as scheduled daemon jobs running in the background.

**Deterministic integration**: When new knowledge arrives that overlaps existing pages, the system applies merge strategies (keep_existing, union, union with dedup, prefer_newer) instead of copying content blindly. Each page has an append-only change log with diff tracking.

## Who This Serves

**Primary**: The creator, building an agent harness that queries this knowledge store alongside Honcho. The wiki is layer two — structured and indexed knowledge on top of raw filesystem access.

**Secondary**: Other developers building agent harnesses or automated knowledge workflows who need a structured knowledge base that compounds over time without requiring a specific agent frontend.

**Tertiary**: Teams or workshops looking for a wiki system maintained by AI agents with explicit governance and cross-domain organization.

## Success Criteria

**For the creator (month 12):**
- The agent harness queries the wiki for domain-specific knowledge with high accuracy
- New knowledge (session transcripts, scraped content, documents) lands in the inbox and is automatically processed without manual intervention
- The knowledge base is self-maintaining — governance jobs catch issues before they become problems
- The system is the primary knowledge substrate for my agent workflows, not a supplementary tool

**For the project (12-24 months):**
- Other developers successfully embed the library in their own agent harnesses
- The exports (llms.txt, JSON sidecars) are recognized standards for LLM-readable documentation
- Community contributions fill the gaps between competing wiki projects
- The system is referenced as a canonical implementation of Karpathy's compounding wiki pattern

## Scope

**In for V2-V5** (the complete roadmap detailed below):
- Trust layer: score pages, enforce citations, auto-flag hallucinations, truth-seeking audits
- Cross-domain synthesis: shared concepts, entity promotion, topic-level dashboards
- Web UI with graph visualization, browse-by-entity, daemon control panel
- Online integrations: GitHub, docs sites, RSS feeds
- Vector search, synthesis cache, talk pages, community detection
- Full multi-agent coverage (add Gemini CLI, Ollama as provider)

**Explicitly out:**
- Multi-tenant SaaS with authentication (for now — stays local-first)
- Autonomous internet crawling at scale (online integrations are optional, bounded)
- Perfect semantic search (good enough through vector search, but not a search engine)

## Vision

By the end of V5, LLM Wiki becomes the canonical self-maintaining knowledge infrastructure for agentic AI — the layer between raw files and the reasoning that happens on top of them. It's a library you import into your agent harness, a daemon that maintains your knowledge while you sleep, and a structured knowledge graph that gets better every day you use it.

Whether you're building an agent harness, running a homelab, doing deep research on a topic, or managing a team's knowledge base — you drop sources into the inbox, the daemon takes care of the rest, and your agents query a knowledge base that compounds with every new piece of information.

---

# Full Roadmap: V2 through V5

## V2 — Trust Layer

**Goal**: Make the wiki safer to trust. Prevent hallucination drift, surface stale content, enforce provenance.

| # | Feature | Source Inspiration | Effort | Status |
|---|---------|-------------------|--------|--------|
| 1 | Score candidate pages before promotion; enforce confidence thresholds | nvk topic lifecycle | 200 lines | Planned |
| 2 | Source citation enforcement — pages without valid source refs marked low-confidence | nvk thesis tracking | 150 lines | Planned |
| 3 | Confidence fields on pages and claims, visible in search results | kenhuangus metrics | 150 lines | Planned |
| 4 | Hallucination guard: candidate pages go through auto-approval or review queue based on source overlap | labhund + nvk | 200 lines | Planned |
| 5 | Truth-seeking audits: periodic scans for unsupported claims, run as daemon job | nvk | 200 lines | Planned |
| 6 | Orphan page detection and alerting | web conventions | 100 lines | Planned |
| 7 | Stale content auto-tagging with configurable thresholds | labhund auditor | 100 lines | Planned |

**Exit criteria**: Hallucinated page creation is contained (all new pages gated through promotion). Stale claims are surfaced automatically by scheduled daemon jobs. Low-confidence content is visible and reviewable in the UI.

---

## V3 — Cross-Domain Synthesis

**Goal**: Allow useful shared knowledge without flattening all domains.

| # | Feature | Source Inspiration | Effort | Status |
|---|---------|-------------------|--------|--------|
| 8 | Shared concept/entity promotion flow (already partially exists — refine) | nvk + this project | 200 lines | In progress |
| 9 | Cross-domain summary pages auto-generated from entities appearing in multiple domains | nashsu co-occurrence | 400 lines | Planned |
| 10 | Per-domain dashboards and global knowledge overview | nashsu heatmap | 200 lines | Planned |
| 11 | Better ranking and traversal heuristics — authority scoring based on cross-domain references | labhund authority graph | 200 lines | Planned |
| 12 | Per-domain schemas: policies, tags, ingestion rules per domain | kenhuangus domain structure | 150 lines | Planned |
| 13 | Topic archive lifecycle: old topics archived, preserved but out of normal context | nvk topic archive | 200 lines | Planned |

**Exit criteria**: Shared pages are high-signal, not clutter. Cross-domain navigation helps the agent reason across boundaries without confusing domain context.

---

## V4 — UX + Product Layer

**Goal**: Make the system pleasant to browse and operate for humans, not just agents.

| # | Feature | Source Inspiration | Effort | Status |
|---|---------|-------------------|--------|--------|
| 14 | Web UI: search, browse by entity/concept/source, page editor with preview | nashsu + lucasastorian | 2-3 weeks | Planned |
| 15 | Graph visualization: knowledge graph with clustering, force-directed layout | nashsu graph view | 300 lines | Planned |
| 16 | Community detection: Louvain algorithm on knowledge graph to auto-suggest domain boundaries | nashsu Louvain | 400 lines | Planned |
| 17 | Daemon control panel: start/stop jobs, view job history, adjust schedules | lucasastorian admin | 200 lines | Planned |
| 18 | Richer site generation: full JSON-LD graph export per page, RSS feeds | Pratiyush exports | 150 lines | Planned |
| 19 | Backlinks panel on each page (already partially built — surface in UI) | Web conventions | 100 lines | Planned |

**Exit criteria**: A human can open the UI, browse domains, follow cross-links, and understand what the system knows. The graph view reveals clusters and unexpected connections.

---

## V5 — Online Integrations

**Goal**: Selectively add remote inputs without losing local-first discipline.

| # | Feature | Source Inspiration | Effort | Status |
|---|---------|-------------------|--------|--------|
| 20 | GitHub repo ingestion: watch repositories, ingest new content automatically | kenhuangus GitHub monitor | 300 lines | Planned |
| 21 | Docs site ingestion: crawl documentation sites, extract structured content | Pratiyush session adapter | 300 lines | Planned |
| 22 | RSS feed ingestion: subscribe tofeeds, process new articles | web conventions | 200 lines | Planned |
| 23 | Optional cloud sync: encrypted sync across machines, not multi-tenant SaaS | nashsu queue design | 200 lines | Planned |
| 24 | arXiv monitor: fetch latest papers in relevant categories | kenhuangus arXiv monitor | 200 lines | Planned |
| 25 | Extension point: plugin architecture for custom input sources | nvk plugins | 150 lines | Planned |

**Hard rule**: Remote ingestion is optional, not required for core correctness. The system works perfectly with local-only sources.

---

## Cross-Cutting Gaps (from Competitive Analysis)

These gaps exist across all V2-V5 phases. Each should be delivered when its dependencies are ready:

| # | Feature | Inspiration | Effort | When |
|---|---------|------------|--------|------|
| 26 | Vector/semantic search alongside BM25 | nashsu concept | 500 lines | V2 or V3 |
| 27 | AI-consumable exports: programmatic `llms.txt`, `llms-full.txt` via CLI | Pratiyush | 300 lines | V2 |
| 28 | Synthesis cache: record high-value queries, auto-expand wiki where gaps found | labhund | 400 lines | V3 |
| 29 | Talk pages: companion discussion files for each wiki page | labhund | 100 lines | V3 or V4 |
| 30 | Multi-agent session coverage: add Gemini CLI, Ollama as provider | Pratiyush + ADR-001 | 200 lines | V2 |
| 31 | Graphviz export for knowledge graph visualization | web conventions | 150 lines | V4 |

---

## Delivery Order Recommendation

Minimize interdependencies, maximize visible progress:

**Phase 1 (V2, ~3-4 weeks):** Governance wiring (Job 1), exports CLI (Job 2), citation enforcement (Job 2), hooks install (Job 1), vector search (Gap 26), multi-agent coverage (Gap 30).

**Phase 2 (V2-V3, ~3-4 weeks):** Promotion pipeline wiring (Job 1), confidence fields (Job 3), hallucination guard (Job 4), cross-domain scoring (Job 11), synthesis cache (Gap 27).

**Phase 3 (V3, ~2-3 weeks):** Cross-domain summary pages (Job 9), per-domain dashboards (Job 10), topic archive (Job 13), talk pages (Gap 29).

**Phase 4 (V4, ~2-3 weeks):** Web UI (Job 14), graph visualization (Job 15), community detection (Job 16), daemon control panel (Job 17).

**Phase 5 (V5, ~2-3 weeks):** Online integrations (Jobs 20-25), plugin architecture (Gap 31).

Total estimated effort: 6-10 weeks of focused development.

---

## Competitive Positioning

After rolling together the best parts of every related project, LLM Wiki occupies a unique space:

- **vs nashsu**: Same compounding knowledge philosophy, but as a library not a desktop app. Agent-agnostic instead of single-agent. Domain-separated instead of flat. Governed instead of passive.
- **vs lucasastorian**: Same wiki pattern, but you choose the frontend (or roll your own). The daemon is already built; lucasastorian has a server we don't need.
- **vs labhund**: We have all the daemon + governance they had, plus federation, CLI, and a clearer path to completion. They deprecated in favor of lacuna-wiki.
- **vs nvk**: We share the thesis tracking and promotion ideas, but we're a library not a plugin framework. Simpler surface, focused internal abstraction.
- **vs Pratiyush**: We share the export philosophy. They have broader agent coverage; we have stronger internal governance.
- **vs Ar9av**: Same skills-first, agent-agnostic philosophy. We have the daemon + federation they lack.
- **vs kenhuangus**: Same domain compartmentalization and local-first discipline. We have richer governance and a broader feature set.

No other project combines: daemon execution + domain federation + full governance + agent-agnostic library + complete CLI + deterministic integration + contradiction detection + promotion pipeline. All of those are already here. The roadmap fills the remaining gaps so this becomes the superset.

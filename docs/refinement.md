# LLM Wiki Comparative Analysis & Project Refinement Plan

**Version**: 1.0
**Date**: 2026-05-16
**Author**: Marc Montecalvo
**Purpose**: Comprehensive analysis of 9 related LLM wiki projects followed by a detailed blueprint for refining the standalone `llm_wiki` Python library based on proven patterns from each.

---

## Part I: The Reference Point

### Karpathy's LLM Wiki Concept (Original Gist)

Andrej Karpathy's gist is a methodology document, not code. The core insight is that most LLM+document systems (RAG, NotebookLM, ChatGPT file uploads) re-derive knowledge from scratch every query. The wiki pattern compiles knowledge once into a persistent, interlinked collection of markdown files. The LLM reads raw sources and incrementally updates the wiki — updating entity pages, revising summaries, flagging contradictions. The wiki compounds: cross-references are pre-built, synthesis is pre-computed, and knowledge is always kept current.

The architecture has three layers:
- **Raw sources**: immutable collection (PDFs, articles, images, data files). The LLM reads but never modifies.
- **Wiki**: LLM-generated, structured markdown pages with cross-references in `[[wikilink]]` format. This is the source of truth for the user.
- **Schema**: rules and policies governing how the LLM interacts with wiki. This is the source of truth for the LLM.

Two navigation files:
- **index.md**: content catalog with links, summaries, and metadata. Updated on every ingest.
- **log.md**: chronological, append-only record of what happened and when.

Three operations:
- **Ingest**: drop a source → LLM reads it, discusses takeaways, writes wiki pages, updates index, updates log.
- **Query**: search wiki → synthesize answer. The wiki is the primary source, not raw documents.
- **Lint**: health check across the wiki.

Key philosophy: Obsidian is the IDE, the LLM is the programmer, the wiki is the codebase. The tedious part of maintaining knowledge is not reading or thinking — it's bookkeeping. LLMs don't forget cross-references and can touch 15 files in one pass.

---

## Part II: Deep Dives Into Each Related Project

### 1. nashsu/llm_wiki (7,673 stars)

**What it is**: A desktop application for building personal knowledge bases using LLMs. It is the most-starred wiki project by a wide margin, indicating strong market interest in the concept.

**Architecture**: Desktop-first. It runs as a standalone app with a marble-inspired theme, providing a graphical interface for interacting with the LLM wiki pattern. The desktop approach means it can hook into the local filesystem directly and manage file I/O without external dependencies.

**Ingestion flow**: Two-step process. First, "analysis" — the LLM reads the raw source and extracts structural information. Second, "generation" — the LLM writes structured wiki pages based on the analysis. This separation makes the ingestion more deliberate and produces higher-quality wiki pages than a single-read-then-write approach.

**Knowledge graph**: Four-signal knowledge graph with named relationships:
- **Direct**: explicit `[[wikilink]]` references between pages. Standard markdown wikilink pattern.
- **Source overlap**: pages sharing the same raw source files. This is a weak signal but captures topical relationships without LLM inference.
- **Existence**: co-occurrence in the same context window. If two entities appear in the same source document, there is a statistical relationship worth noting.
- **Type**: entity-type relationships (e.g., person→organization, concept→domain). These are schema-level relationships.

**Community detection**: Louvain algorithm applied to the knowledge graph to detect clusters of tightly-related pages. This auto-identifies topical clusters and can suggest domain boundaries, concept groupings, or organizational structure for the wiki. The output is SEO-friendly — clusters map naturally to site sections or index subsections.

**Persistent ingest queue**: Not simply "drop and process." Sources enter a persistent queue that survives app restarts. This is a robust design because it handles intermittent LLM availability — you can queue up sources during the day, and the system processes them when the LLM is ready. It decouples source acquisition from LLM processing.

**Multimodal capabilities**: Image ingestion is supported. The LLM reads images (via multimodal models) and produces structured text descriptions for the wiki. This is critical for journal articles with charts, slides with diagrams, or any visual source that otherwise has no text representation.

**Deep research**: Extended LLM sessions that perform iterative lookups and synthesis across the wiki. Not just "query this one thing" but "research this topic thoroughly" — generating a series of related queries and synthesizing a comprehensive response.

**Chrome Web Clipper**: Browser extension that clips web articles to markdown and deposits them into the raw sources directory. This is a quality-of-life feature that removes friction from source acquisition.

**What it got right**: The two-step ingest (analyze → generate) produces higher quality pages. The four-signal knowledge graph is comprehensive — it captures both explicit links and implicit relationships. The persistent queue is a subtle but important reliability feature. Deep research extends the query pattern from single-shot to multi-hop reasoning.

**Where this project diverges from the standalone library approach**: It is a complete desktop application with its own UI, data model, and runtime. This means decisions are baked in. The standalone `llm_wiki` library should learn from its data model but remain framework-agnostic.

---

### 2. Ar9av/obsidian-wiki (1,295 stars)

**What it is**: An agent-skills framework for the LLM wiki pattern. Unlike other projects that target a specific LLM provider, this one is provider-agnostic and designed to work with 15+ coding agents including Claude Code, Cursor, VS Code, Codex, and others.

**Skills-first philosophy**: The project is organized as a collection of "skills" — self-contained prompts, scripts, and configurations that a coding agent can execute. Each skill handles one aspect of the wiki lifecycle:
- Ingest skill: reads sources, writes wiki pages
- Query skill: takes questions, synthesizes answers from the wiki
- Lint skill: checks wiki health

**Slash commands**: Natural-language commands like `/ingest`, `/query`, `/lint` that map to underlying skills. This is how a user and agent communicate — the user types a slash command, the agent executes the associated skill.

**Setup script**: `setup.sh` auto-discovers the workspace, detects which LLM agent is available, and configures the appropriate skills. This makes onboarding frictionless — one command and you have a working system.

**Agent compatibility matrix**: Explicitly tested with 15+ agents. This is unusual and valuable because most wiki projects target a single agent. By designing for compatibility, this project proved that the wiki pattern is agent-agnostic — the same skills work regardless of which LLM is driving.

**No server required**: Unlike Lucas Astorian's project that requires a Next.js + FastAPI server, obsidian-wiki runs purely from the filesystem. Ambients run from within the IDE with no external service needed.

**What it got right**: The skills-first approach is the cleanest abstraction for the wiki lifecycle. Slash commands provide discoverable UX. The focus on agent compatibility (rather than provider compatibility) is the right abstraction — it means the system works with whatever LLM you have access to today and any LLM in the future.

**Gap for standalone library**: The skill definitions themselves could be packaged as PromptTemplates or lunr-query files in the `llm_wiki` package. The slash command convention could become CLI commands (`llm-wiki ingest`, `llm-wiki query`).

---

### 3. lucasastorian/llmwiki (908 stars)

**What it is**: A self-contained, self-hosted server application for the LLM wiki pattern. Next.js frontend, FastAPI backend, SQLite database.

**One-command setup**: `llm-wiki init` → `llm-wiki serve` → open browser. The entire stack boots in one command. This is the lowest-barrier entry of any wiki project — no filesystem navigation, no Obsidian installation, no agent configuration needed.

**Server architecture**: REST API for wiki operations (ingest, query, lint). SQLite for persistence. Next.js for the web UI. The web UI provides a modern browsing experience — search, navigation, page editing.

**What it got right**: The one-command setup is a UX achievement. It makes the wiki pattern accessible to non-technical users. The web UI is the limiting factor of filesystem-only approaches (like Karpathy's original or this project) because it's not as feature-rich as Obsidian's graph view and backlinks.

**Gap for standalone library**: This project solves the wrong problem for our use case. We are building a library, not a server. The daemon module already provides similar server-like capabilities via APScheduler. A web frontend would be a separate project (e.g., `llm-wiki-web`) rather than core functionality.

---

### 4. Pratiyush/llm-wiki (250 stars)

**What it is**: A static site generator for the wiki pattern. It generates beautiful documentation sites from wiki content with heatmaps showing content depth.

**Session-to-wiki conversion**: Takes Claude Code session transcripts (structured as markdown) and converts them into wiki pages. This bridges the gap between conversational knowledge acquisition and structured wiki output. Instead of treating a conversation as ephemeral, it becomes lasting, structured wiki content.

**AI-consumable exports**: Generates `llms.txt` (a hierarchical catalog of wiki pages) and `llms-full.txt` (all content concatenated) in standard formats that other LLM agents can consume. Plus JSON-LD structured data export. This is a critical feature — the wiki becomes a knowledge asset that other tools can read.

**Static site generation**: Converts markdown wiki into a navigable HTML site with:
- Heatmap visualization (content depth by topic)
- Tag-based browsing
- Search
- Graph-like page graphs (from Backlinks)

**What it got right**: The AI-consumable exports are the most valuable contribution here. `llms.txt` and `llms-full.txt` are becoming de facto standards for LLM-readable documentation (see Anthropic's own implementation). The session-to-wiki conversion is an elegant ingest pattern that turns conversational interaction into structured knowledge.

**Gap for standalone library**: The static site generator (HTML output) adds complexity. But the export functionality — `llm_wiki export llms.txt` and `llm_wiki export full` — is a clear addition. The `docs/export/` directory already has examples; the thing that is missing is a programmatic CLI command.

---

### 5. Labhund/llm-wiki (27 stars)

**What it is**: A background-agent system for wiki maintenance. Multiple specialized agents run unsupervised and continuously improve wiki quality.

**Background agents**:
- **Auditor**: reviews wiki pages for quality, identifies contradictions, and flags outdated information.
- **Librarian**: organizes content, updates taxonomy, maintains cross-references, and ensures proper categorization.
- **Adversary**: actively challenges wiki content by looking for weaknesses, inconsistencies, and unsupported claims.

**Synthesis cache**: A specialized feature where "productive" queries (searches that lead to meaningful synthesis) are cached and automatically expanded into wiki pages. When a query reveals a gap in existing knowledge, the system addresses it by creating the missing page. This turns the wiki from reactive (you ask, it answers) into proactive (it notices what you're not asking and fills gaps).

**Talk pages**: Every wiki page gets a companion `talk/page-id.md` file where the LLM and user discuss content decisions. It is Wikipedia-style editorial discussion. The LLM can leave notes about why it decided to change something, flag claims that need verification, or record disagreements between sources.

**What it got right**: The three-agent model (auditor/librarian/adversary) is a clean abstraction for maintenance. The synthesis cache is an elegant way to automatically grow wiki coverage based on user interests. Talk pages provide an audit trail of decisions.

**Gap for standalone library**:
- The three-agent model maps directly to three existing modules: `governance/linter.py` (auditor), `index/` helpers (librarian), `governance/contradictions.py` (adversary). They need to be orchestrated together.
- The synthesis cache could be built as a `synthesis_cache.py` module that records high-value queries and triggers wiki expansion.
- Talk pages can be a thin service: `talks.py` that reads/writes `talk/{page_id}.md` alongside each page.

---

### 6. kenhuangus/llm-wiki (20 stars)

**What it is**: A domain-specific wiki with automated content discovery. Designed for structured, domain-organized wikis with live monitors.

**Domain-specific structure**: The wiki has explicit domain boundaries. Each domain has its own raw and wiki directories. Domain metadata files define schema, tags, and policies per domain. This is the domain-compartmentalization pattern.

**GitHub monitor**: Watches specific repositories and automatically ingests when new content appears. Pull requests, issues, or star changes can trigger wiki updates. This turns the wiki into an active intelligence tracker.

**arXiv monitor**: Fetches from arXiv (via their API) and processes the latest papers in relevant categories. This is domain-specific content discovery — you say "I care about computer vision" and the system watches arXiv for CV papers.

**Agent behavioral rules**: Defines rules for how the LLM should behave during wiki operations. For example: "When contradicting a prior claim, cite which page was changed and why." This provides governance over the LLM's output quality.

**What it got right**: Domain-specific structure is proven to scale better than monolithic wikis. The idea of watches monitors is elegant: live data sources keep the wiki fresh without manual effort. Behavioral rules are a lightweight approach to quality governance.

**Gap for standalone library**: Domain support already exists in this codebase (`domains/` directory). The monitors (GitHub, arXiv) are interesting but domain-specific — they belong in a `llm_wiki/monitors/` module or as optional plugins. The behavioral rules could inform the schema system.

---

### 7. nvk/llm-wiki (425 stars)

**What it is**: A multi-platform plugin architecture for the wiki pattern with thesis-driven research capabilities.

**Plugin architecture**: The system supports plugins that can be loaded at runtime to add new capabilities. This makes the system extensible without core modifications. Plugins can add new extractors, new import formats, new export formats, new search backends.

**Thesis-driven research**: Unlike simple RAG where you query and get answers, this system builds a thesis over time. As sources are ingested, it compares new information against existing claims, provides evidence counters, strengthens or weakens thesis positions. The thesis evolves as more evidence accumulates.

**Topic lifecycle**: Every page/wik е entity has a lifecycle: `pending → draft → active → featured/deprecated`. This is a maturity model. New pages start as drafts and gain prominence as they are validated by multiple sources. Deprecated pages are flagged but not deleted.

**Truth-seeking audits**: Periodic audits that scan the entire wiki for contradictions, unsupported claims, and outdated information. These audits can be triggered manually or on a schedule. The system produces a report of findings and optionally fixes contradictions automatically.

**What it got right**: Plugin architecture is the right abstractions for a library. The thesis-driven approach gives the wiki a "point of view" rather than being a passive repository. The topic lifecycle model is essential for wiki maintenance — it gives pages status and handles transitions over time.

**Gap for standalone library**: The promotion pipeline (`promotion/` module) already implements a draft→active lifecycle. The plugin architecture maps to the existing `adapters/` and `models/domain.py` structure. Truth-seeking audits map to `governance/` module — these are conceptually identical. This project's contribution is validating the thesis/lifecycle/audit paradigm.

---

### 8. Data Science Dojo Tutorial

**What it is**: A tutorial from a data science community teaching the LLM wiki pattern. It provides step-by-step instructions for building a personal knowledge base using the three-layer architecture.

**What it got right**: The tutorial format makes the concept accessible. It validates that the wiki pattern is learnable and implementable by anyone, not just LLM/ML engineers. It also shows that the pattern works for real use cases (course notes, research tracking) rather than just proof-of-concept.

---

### 9. Karpathy's Original Gist (Revisited)

**Key insight**: The three-layer architecture (raw → wiki → schema) is the foundation. Everything else is augmentation. The opimization principle (compile once, query from persistent wiki, keep current, don't re-derive) is the north star.

Specific concepts from the gist:
- Knowledge compounding: "the wiki is cumulative knowledge compounds." Each source makes the wiki richer.
- Cross-reference maintenance: the LLM maintains `[[wikilink]]` references, building relationships between pages over time.
- Three-lens update: when a new source arrives, the LLM considers (a) what to add, (b) what to revise, (c) what to delete from the wiki.
- Two questions when reading a source: "What is the key message or point of this source?" and "What claim, observation, or fact does it establish that is worth preserving?"
- Word on this pattern: "If you like it but want to customize it, a great way to start is to give this same prompt to your own LLM agent, say 'build this out' and then tell it how to implement each layer or even what tools/utilities it should use."

---

## Part III: What This Project Already Has (Before Looking at the Competition)

This build-out was proceeding before seeing the competing projects. Here is the mapping between existing code and the concepts found in the competitor analysis:

### Ingestion Pipeline (maps to nashsu's two-step + obsidian-wiki's skills)
- `ingest/watcher.py`: Filesystem watcher for raw sources. Automatically detects new files.
- `ingest/normalizer.py`: Normalizes raw content into a standard format.
- `ingest/router.py`: Routes content to the correct domain.
- `ingest/failed.py`: Tracks failed ingestions for retry.
- `adapters/`: Adapter system for different input formats (Claude sessions, Obsidian, markdown).

### Extraction Pipeline (maps to nashsu's knowledge graph + labhund's agents)
- `extraction/pipeline.py`: Main extraction orchestration.
- `extraction/entities.py`: Extracts entities (people, organizations, places).
- `extraction/concepts.py`: Extracts abstract concepts and ideas.
- `extraction/relationships.py`: Extracts relationships between entities and concepts.
- `extraction/claims.py`: Extracts verifiable claims with confidence scores.
- `extraction/enrichment.py`: Enriches pages with extracted metadata.
- `extraction/qa.py`: Extracts question-answer pairs from content.

### Domain Model (maps to kenhuangus's domain structure)
- `models/domain.py`: Domain abstraction for compartmentalization.
- Each domain has its own pages/ and queue/ directories.

### Governance (maps to labhund's agents + nvk's audits)
- `governance/linter.py`: General wiki health checks.
- `governance/contradictions.py`: Detects contradictory claims.
- `governance/duplicates.py`: Finds duplicate pages.
- `governance/staleness.py`: Detects outdated content.
- `governance/quality.py`: Quality scoring and validation.
- `governance/routing_mistakes.py`: Catches misrouted content.

### Indexing and Search (maps to nashsu's knowledge graph + query interface)
- `index/backlinks.py`: Backlink tracking for wikilinks.
- `index/graph_edges.py`: Graph edges for entity relationships.
- `index/metadata.py`: Page metadata index.
- `index/fulltext.py`: Fulltext search index.
- `query/search.py`: Unified search interface.

### Promotion Pipeline (maps to nvk's topic lifecycle)
- `promotion/engine.py`: Promotion orchestration logic.
- `promotion/scorer.py`: Quality scoring for promotion decisions.
- `promotion/config.py`: Promotion configuration.

### Daemon and Scheduling (provides server-like capabilities)
- `daemon/scheduler.py`: APScheduler-based job orchestration.
- `daemon/workers.py`: Background job workers.
- `daemon/execution_store.py`: Stores execution history.
- `daemon/retry.py`: Retry logic for failed jobs.

### CLI and Configuration
- `cli.py`: Command-line interface.
- `models/config.py`: Model and provider configuration.
- `models/client.py`: Model client abstraction (OpenAI, Claude Agent SDK, etc.).

---

## Part IV: Gap Analysis

Based on comparing the 9 projects against what this project already has, here are the gaps — what exists nowhere in this codebase yet:

### Gap 1: AI-Consumable Exports (Pratiyush)

**What**: Programmatic generation of `llms.txt` (hierarchical page catalog) and `llms-full.txt` (all content concatenated) as export formats.

**Current state**: `docs/export/` has example files. No programmatic export command exists in the CLI.

**Scope**: 200-300 lines of new code in a new `cli.py` subcommand.

### Gap 2: Vector/Semantic Search (nashsu concept, no direct equivalent)

**What**: Embedding-based semantic search alongside the existing fulltext index. When someone queries "ways LLMs maintain stories" the fulltext index returns nothing (those exact words don't exist), but semantic search finds the relevant page.

**Current state**: Only fulltext (BM25) and metadata filtering.

**Scope**: 300-500 lines. Depends on embedding model choice. Needs a `_search_semantic` method in the query module.

### Gap 3: Governance Jobs in the Daemon (Labhund's background agents)

**What**: Register the existing governance modules (contradictions, duplicates, staleness, quality) as background jobs in the daemon scheduler.

**Current state**: Governance modules exist and work. Scheduler exists. No job registration ties them together.

**Scope**: ~150 lines in `daemon/main.py`. Import governance functions, register them as cron/interval jobs.

### Gap 4: Promotion Pipeline Wiring (nvk's lifecycle + labhund's curation)

**What**: Connect the promotion engine to the review queue so extraction results actually flow through a draft→active pipeline based on quality scores.

**Current state**: Promotion module exists. Review module exists. No glue code connects them.

**Scope**: ~200 lines to wire the pipeline together and add a `llm-wiki promote` CLI command.

### Gap 5: Claude Code Hooks Installation (obsidian-wiki's setup script)

**What**: A `llm-wiki hooks install` CLI command that sets up Claude Code hook integration per ADR 004.

**Current state**: ADR 004 documents the single capture script. The script exists. No CLI command installs it.

**Scope**: ~100 lines. A new CLI command that copies the capture script to the right location and registers hooks.

### Gap 6: Synthesis Cache (Labhund)

**What**: Record high-value queries that reveal knowledge gaps and trigger automatic wiki expansion.

**Current state**: Nothing. The `review/` module tracks items but not query-driven expansion triggers.

**Scope**: 200-400 lines. Needs a new `synthesis_cache.py` module and integration with the query pipeline.

### Gap 7: Talk Pages (Labhund)

**What**: A companion talk page for each wiki page, where the LLM and user discuss content decisions.

**Current state**: Nothing.

**Scope**: ~100 lines. A thin service that reads/writes `talk/{page_id}.md` alongside each page.

### Gap 8: Community Detection / Graph Visualization (nashsu)

**What**: Louvain-based clustering of the knowledge graph to auto-suggest domain boundaries or concept groupings. Graph visualization export (Graphviz format).

**Current state**: `graph_edges.py` stores edges but no clustering or visualization.

**Scope**: 300-500 lines. Needs `community_detection.py` and optional `graphviz` dependency.

---

## Part V: Design Decisions and Tradeoffs

### Library vs. Application

The competing projects split between library (this project) and application (nashsu, lucasastorian, Ar9av). Selection of library is the right choice because:
- Application constraints (UI framework, database, hosting) are application-specific decisions that users should make.
- As a library, users can embed wiki functionality in their own applications (Jupyter notebooks, CLI tools, dashboards).
- Multiple frontends become possible: Obsidian, web, CLI, desktop.

### Plugin Architecture

nvk's plugin architecture is the right pattern for extensibility. The existing `adapters/` module is the seed of this — it should be generalized into a plugin system.

### Domain Compartmentalization

kenhuangus and this project both independently arrived at domain-based wiki organization. This validates that multi-domain wikis are the right abstraction for scaling.

### Promotion vs. Passive Wiki

nvk's topic lifecycle and this project's promotion pipeline converge on the idea that wiki pages should have explicit status. A draft page is a work-in-progress. An active page is validated. A featured page has strong multi-source support. This is a critical feature for wiki quality over time.

---

## Part VI: Refinement Plan

The refinement order is:

1. **Tie governance into daemon** (150 lines) — register existing governance modules as scheduled jobs. Lowest effort, highest visibility change because it transforms internal modules into active background processes.
2. **Add export CLI** (300 lines) — adds `llm-wiki export llms-txt` and `llm-wiki export full` which are useful immediately and validate the library's export capability.
3. **Wire promotion pipeline** (200 lines) — connects extraction results to promotion decisions. Transforms extraction from a one-shot operation into a pipeline with quality gates.
4. **Add hooks install command** (100 lines) — activates Claude Code hook integration. Makes the ADR 004 work production-ready.
5. **Add vector search** (500 lines) — augments the search interface with semantic search. Requires embedding model choice and dependency on `sentence-transformers` or equivalent.
6. **Implement synthesis cache** (400 lines) — auto-expands wiki based on revealed knowledge gaps. Makes the wiki proactive rather than reactive.
7. **Implement talk pages** (100 lines) — thin service for LLM/user discussion about content decisions.
8. **Implement community detection** (400 lines) — Louvain clustering of knowledge graph. The highest-capital item — nice to have for publication/analysis, not essential for core functionality.

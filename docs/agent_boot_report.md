# Agent Boot Report

Generated: 2026-04-13

## Architecture Summary

This repository implements a **federated LLM wiki system** with the following architecture:

### Core Design Principles

1. **Federated Domain Model**
   - One unified runtime and daemon
   - Multiple bounded wiki domains (vulpine-solutions, home-assistant, homelab, personal, general)
   - Shared search/index layer across all domains
   - Cross-domain graph for linking related concepts
   - Domain-local pages first, shared pages by promotion only

2. **Daemon-Governed Workflow**
   - Background daemon manages all operations
   - Scheduled maintenance loops for indexing, linting, exports
   - Inbox-based ingestion pipeline
   - Deterministic routing and normalization
   - Append-only operation logs for auditability

3. **Multi-Source Ingestion**
   - Adapter-based architecture for different input types
   - Initial support: markdown, text, agent transcripts (Claude Code, Codex, Cursor)
   - Normalization pipeline to standard markdown with frontmatter
   - Domain routing via explicit override, source rules, or classification

4. **Structured Knowledge Extraction**
   - Schema-validated extraction (entities, concepts, claims, relationships)
   - Integration pipeline updates existing wiki pages additively
   - Source citation preservation
   - Confidence tracking throughout

5. **Machine-Readable Outputs**
   - llms.txt exports for AI consumption
   - JSON sidecars for structured data
   - Graph exports for relationships
   - Sitemap generation

### Architectural Influences

- **Labhund/llm-wiki**: Daemon concept, governance loops, MCP integration, operational discipline
- **nvk/llm-wiki**: Domain/project partitioning, portable agent conventions, topic wiki patterns
- **Pratiyush/llm-wiki**: Transcript adapters, session ingest, export formats
- **Ar9av/obsidian-wiki**: Cross-agent compatibility, bootstrap patterns

### Technology Stack Assumptions

- Language: Python (inferred from __pycache__ in .gitignore)
- Config format: YAML
- Storage: Local filesystem with markdown files
- Indexing: TBD (likely fulltext + metadata + graph indexes)
- Schema validation: JSON Schema or Pydantic (per implementation_step_1.md)

## Assumptions

1. **Local-First Design**
   - All operations happen locally
   - No cloud dependencies for core functionality
   - Remote integrations are optional v5+ features

2. **Model-Agnostic**
   - No hardwired dependency on a single model/provider
   - Configuration in models.yaml allows swapping
   - System must survive model changes with acceptable drift

3. **Domain Boundaries**
   - Each document belongs to exactly one domain
   - Shared space is opt-in, not default
   - Promotion to shared requires cross-domain evidence

4. **Schema-First Development**
   - All model outputs must pass validation
   - No freeform page writes allowed (per models.yaml contracts)
   - Frontmatter is mandatory for all pages

5. **Append-Only Operations**
   - Changes are logged
   - Integration is additive where possible
   - No silent rewrites of existing content

6. **Review Queue**
   - Low-confidence content surfaces for human review
   - New shared pages require approval
   - Contradictions and stale content flagged

## Open Questions That Block Coding

### High Priority

1. **Python Version & Dependencies**
   - What Python version should we target? (suggest: 3.11+)
   - What dependency management? (suggest: poetry or uv)
   - Do we need a requirements.txt or pyproject.toml?

2. **Model Provider Integration**
   - models.yaml shows "provider: local" - what does this mean?
   - Should we support OpenAI-compatible APIs?
   - Anthropic API? Ollama? LM Studio?
   - What's the abstraction layer for model calls?

3. **Index Implementation**
   - What fulltext indexing library? (whoosh, tantivy, sqlite FTS5?)
   - Graph index storage? (networkx, sqlite, json files?)
   - Metadata index? (sqlite, json files, in-memory?)

4. **Daemon Implementation**
   - What scheduler? (APScheduler, custom loop, systemd timer?)
   - Should it run as a systemd service, launchd, or manual process?
   - How do we handle graceful shutdown?

5. **Unique ID Generation**
   - What format for page/entity IDs? (UUID, slug, hash?)
   - How to ensure ID stability across re-ingestion?

### Medium Priority

6. **Testing Strategy**
   - Unit tests? Integration tests? Both?
   - Test framework? (pytest assumed from .pytest_cache)
   - How to test daemon without long waits?
   - Fixture data strategy?

7. **Configuration Validation**
   - Should config files be validated on load?
   - Schema for YAML configs?

8. **Error Handling**
   - Retry strategy for failed ingests?
   - What makes an ingest "failed" vs "low confidence"?
   - Dead letter queue behavior?

9. **Concurrency**
   - max_parallel_jobs: 2 in daemon.yaml - how to enforce?
   - Thread pool? Process pool? Async?

### Lower Priority

10. **Export Formats**
    - Exact llms.txt format? (see Anthropic/OpenAI conventions)
    - Graph export format? (GraphML, Cytoscape JSON, custom?)
    - Sitemap spec?

## Implementation Risks

### High Risk

1. **Model Output Variability**
   - Risk: Different models produce incompatible schemas
   - Mitigation: Strict schema validation, rejection of invalid outputs

2. **Routing Accuracy**
   - Risk: Content misrouted to wrong domains
   - Mitigation: Confidence thresholds, review queue, manual override

3. **Index Drift**
   - Risk: Indexes get out of sync with wiki content
   - Mitigation: Scheduled rebuilds, change logging, verification checks

4. **Shared Page Pollution**
   - Risk: Shared space becomes a dumping ground
   - Mitigation: Promotion thresholds, explicit opt-in, regular audits

### Medium Risk

5. **Performance at Scale**
   - Risk: Daemon slows down with many pages/domains
   - Mitigation: Incremental indexing, pagination, caching

6. **Merge Conflicts**
   - Risk: Multiple sources update same page simultaneously
   - Mitigation: Additive-only operations, conflict detection, review queue

7. **Dependency on External Repos**
   - Risk: Referenced repos change or disappear
   - Mitigation: Document patterns, not code; don't clone directly

### Lower Risk

8. **Bootstrap Fragility**
   - Risk: New users can't get started easily
   - Mitigation: Good bootstrap script, clear setup docs

9. **Cross-Agent Compatibility**
   - Risk: Different coding agents interpret wiki differently
   - Mitigation: Templates, skill files, clear conventions

## Suggested Issue Groups

### Group 1: Foundation (Bootstrap & Standards)
- Repository structure and tooling setup
- Python environment and dependencies
- Development standards (linting, formatting, pre-commit)
- Basic testing framework
- Documentation structure

### Group 2: Configuration Layer
- Config file validation and loading
- Domain model implementation
- Daemon configuration
- Routing rules implementation
- Model provider abstraction

### Group 3: Core Data Model
- Page frontmatter schemas
- Entity/concept/claim schemas
- Source metadata schemas
- Validation framework
- Template engine

### Group 4: Filesystem & Domain Structure
- Domain directory initialization
- Shared space structure
- Inbox management
- Log file handling
- State persistence

### Group 5: Daemon Core
- Scheduler implementation
- Job queue system
- Worker pool
- Graceful shutdown
- Health checks

### Group 6: Ingest Pipeline
- Inbox watcher
- Source adapters (markdown, text, transcripts)
- Normalization pipeline
- Domain router
- Ingest logging

### Group 7: Extraction Pipeline
- Model client abstraction
- Extraction prompts and schemas
- Entity extraction
- Concept extraction
- Claim extraction
- Relationship detection

### Group 8: Integration Pipeline
- Page merge logic
- Citation appending
- Backlink updates
- Change logging
- Conflict detection

### Group 9: Indexing System
- Metadata index
- Fulltext index
- Graph index
- Index rebuild
- Query interface

### Group 10: Search & Retrieval
- Domain-scoped search
- Cross-domain search
- Ranking heuristics
- Result presentation

### Group 11: Governance Jobs
- Lint checks (schema, orphans, duplicates)
- Stale page detection
- Contradiction detection
- Low-confidence flagging
- Source-less claim detection

### Group 12: Export Pipeline
- llms.txt generator
- JSON sidecar generator
- Graph export
- Sitemap generator
- Export scheduling

### Group 13: Review Queue
- Queue data model
- Queue management API
- Review triggers
- Review UI (CLI or web)

### Group 14: Agent Compatibility
- Skill files
- Bootstrap scripts
- Cross-agent conventions
- MCP server (future)

### Group 15: Testing & Quality
- Unit test suite
- Integration test suite
- Test fixtures
- CI/CD pipeline

### Group 16: Documentation
- Setup guide
- Architecture docs
- API docs
- Contributing guide
- Examples and tutorials

## Decision Log

### Decisions Made During Analysis

1. **Stick to documented architecture** - No major deviations from planning docs unless critical gaps found
2. **Python as implementation language** - Based on .gitignore hints and common LLM tooling
3. **Start with 5 domains** - Per README.md: vulpine-solutions, home-assistant, homelab, personal, general
4. **Schema validation is mandatory** - Per models.yaml: require_schema_validation: true

### Decisions Needed Before Implementation

1. Dependency management approach (poetry vs uv vs pip-tools)
2. Model provider integration approach
3. Index storage implementation
4. Daemon scheduling mechanism
5. ID generation strategy

## Next Steps

1. ✅ Complete repo analysis
2. ✅ Write agent_boot_report.md
3. ⏭️ Create GitHub issue tree (markdown preview)
4. ⏭️ Create actual GitHub issues with labels
5. ⏭️ Begin implementation from issue #1

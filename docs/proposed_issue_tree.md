# Proposed GitHub Issue Tree

## Epic Issues

### Epic 1: Repository Bootstrap & Tooling
Foundation setup for development environment

### Epic 2: Configuration Management
Config file loading, validation, and domain model

### Epic 3: Core Data Structures & Schemas
Page schemas, validation framework, templates

### Epic 4: Daemon Infrastructure
Background worker, scheduler, job orchestration

### Epic 5: Ingest Pipeline
Inbox watching, adapters, normalization, routing

### Epic 6: Extraction & Integration
Knowledge extraction and wiki page integration

### Epic 7: Indexing & Search
Metadata, fulltext, and graph indexes plus query

### Epic 8: Governance & Maintenance
Lint, review, contradiction detection, stale checks

### Epic 9: Export Pipeline
llms.txt, JSON, graph, sitemap generation

### Epic 10: Agent Compatibility Layer
Skills, bootstrap, cross-agent conventions

### Epic 11: Testing & Quality
Test framework, fixtures, CI/CD

### Epic 12: Documentation & Examples
Setup guides, architecture docs, tutorials

---

## Detailed Issue Breakdown

### Epic 1: Repository Bootstrap & Tooling

#### Issue #1: Setup Python project structure
**Labels**: `epic`, `infra`, `good-first-task`
**Why**: Establish dependency management and project scaffolding
**Scope**:
- Choose and configure dependency manager (poetry/uv)
- Create pyproject.toml or requirements.txt
- Set Python version requirement (>=3.11)
- Add initial core dependencies
**Out of scope**: Installing optional or future dependencies
**Acceptance criteria**:
- [ ] Dependency file exists and is valid
- [ ] Python version pinned
- [ ] Installation works on clean system
- [ ] Basic package structure in src/
**Dependencies**: None
**Risks**: Dependency conflicts, version incompatibilities

#### Issue #2: Setup development tooling
**Labels**: `infra`, `good-first-task`
**Why**: Ensure code quality and consistency
**Scope**:
- Configure black/ruff for formatting
- Configure ruff/pylint for linting
- Setup pre-commit hooks
- Add mypy for type checking
**Out of scope**: CI/CD automation (separate issue)
**Acceptance criteria**:
- [ ] .pre-commit-config.yaml exists
- [ ] Running pre-commit hooks succeeds
- [ ] Code formatter runs on commit
- [ ] Type checker configured
**Dependencies**: #1
**Risks**: Tool conflicts, overly strict rules

#### Issue #3: Move planning docs to main repo
**Labels**: `docs`, `good-first-task`
**Why**: Consolidate all documentation in main repo
**Scope**:
- Copy all .md files from llm-wiki-base-repo/ to docs/
- Copy config/ directory to main repo
- Copy templates/ directory to main repo
- Delete extracted folder
- Update paths in docs as needed
**Out of scope**: Rewriting docs content
**Acceptance criteria**:
- [ ] All docs in docs/ directory
- [ ] config/ and templates/ in repo root
- [ ] No llm-wiki-base-repo/ folder remains
- [ ] README.md in repo root
**Dependencies**: None
**Risks**: None

#### Issue #4: Initialize wiki_system directory structure
**Labels**: `infra`, `wiki-core`
**Why**: Create the foundational filesystem structure
**Scope**:
- Run scripts/bootstrap.sh
- Create domain subdirectories
- Create shared/{concepts,entities,synthesis}
- Create inbox/{new,processing,failed,done}
- Create exports/, logs/, state/
**Out of scope**: Populating directories with content
**Acceptance criteria**:
- [ ] All directories exist per README.md structure
- [ ] .gitkeep files in empty dirs where appropriate
- [ ] .gitignore excludes appropriate subdirs
**Dependencies**: #3
**Risks**: None
**Reference**: llm-wiki-base-repo/scripts/bootstrap.sh

#### Issue #5: Setup pytest framework
**Labels**: `testing`, `infra`
**Why**: Enable test-driven development
**Scope**:
- Add pytest to dependencies
- Create tests/ directory structure
- Create conftest.py with basic fixtures
- Add pytest configuration to pyproject.toml
- Create example test file
**Out of scope**: Writing actual test cases (per-feature)
**Acceptance criteria**:
- [ ] pytest runs successfully
- [ ] Test discovery works
- [ ] Example test passes
- [ ] Coverage reporting configured
**Dependencies**: #1
**Risks**: None

---

### Epic 2: Configuration Management

#### Issue #6: Create config schema definitions
**Labels**: `architecture`, `backend`
**Why**: Validate config files before use
**Scope**:
- Create Pydantic models for domains.yaml
- Create Pydantic models for daemon.yaml
- Create Pydantic models for routing.yaml
- Create Pydantic models for models.yaml
- Add validation on load
**Out of scope**: Config UI or editor
**Acceptance criteria**:
- [ ] Schema models in src/models/config.py
- [ ] Invalid configs raise clear errors
- [ ] All fields documented with types
- [ ] Unit tests for validation
**Dependencies**: #1
**Risks**: Schema too strict or too loose
**Reference repos**: Labhund/llm-wiki, Pratiyush/llm-wiki

#### Issue #7: Implement config loader
**Labels**: `backend`
**Why**: Load and validate YAML configs
**Scope**:
- Create ConfigLoader class
- Load all YAML files from config/
- Validate against schemas
- Provide typed config objects
- Handle missing or invalid files gracefully
**Out of scope**: Hot reloading, config merging
**Acceptance criteria**:
- [ ] Config loads successfully
- [ ] Invalid config raises exception
- [ ] Missing config has clear error
- [ ] Unit tests cover edge cases
**Dependencies**: #6
**Risks**: YAML parsing edge cases

#### Issue #8: Implement domain model
**Labels**: `architecture`, `wiki-core`
**Why**: Core abstraction for wiki domains
**Scope**:
- Create Domain class
- Load domains from config
- Validate domain IDs
- Provide domain lookup by ID
- Track domain metadata (title, description, owners)
**Out of scope**: Domain CRUD operations
**Acceptance criteria**:
- [ ] Domain class implemented
- [ ] All config domains loaded
- [ ] Domain lookup works
- [ ] Unit tests pass
**Dependencies**: #7
**Risks**: Domain ID conflicts

#### Issue #9: Implement model provider abstraction
**Labels**: `architecture`, `backend`, `decision-needed`
**Why**: Support multiple LLM providers
**Scope**:
- Design provider interface
- Decide on provider support (OpenAI-compatible, Anthropic, Ollama)
- Create base ModelClient class
- Implement chat completion interface
- Handle API keys from environment
**Out of scope**: Specific provider implementations (separate issues)
**Acceptance criteria**:
- [ ] Provider interface defined
- [ ] Base client class exists
- [ ] API documented
- [ ] Design decision logged
**Dependencies**: #6
**Risks**: Interface too specific or too generic
**Reference repos**: Labhund/llm-wiki

---

### Epic 3: Core Data Structures & Schemas

#### Issue #10: Define page frontmatter schemas
**Labels**: `architecture`, `wiki-core`
**Why**: Strict contract for all wiki pages
**Scope**:
- Create Pydantic models for page frontmatter
- Support all page kinds: page, entity, concept, source
- Define required and optional fields
- Add validation rules
**Out of scope**: Page content parsing
**Acceptance criteria**:
- [ ] Schema models in src/models/page.py
- [ ] All page kinds supported
- [ ] Validation works
- [ ] Documentation for each field
- [ ] Unit tests pass
**Dependencies**: #1
**Risks**: Schema evolution challenges
**Reference files**: templates/*.md

#### Issue #11: Define extraction schemas
**Labels**: `architecture`, `backend`
**Why**: Validate model extraction outputs
**Scope**:
- Create schema for EntityExtraction
- Create schema for ConceptExtraction
- Create schema for ClaimExtraction
- Create schema for RelationshipExtraction
- Include confidence scores
**Out of scope**: Extraction logic itself
**Acceptance criteria**:
- [ ] All extraction schemas defined
- [ ] Confidence field validated (0.0-1.0)
- [ ] Source references required
- [ ] Unit tests pass
**Dependencies**: #1
**Risks**: Schema doesn't capture all needed data
**Reference**: implementation_step_3.md

#### Issue #12: Create markdown frontmatter parser
**Labels**: `backend`, `wiki-core`
**Why**: Read and write frontmatter reliably
**Scope**:
- Parse YAML frontmatter from markdown
- Validate against page schemas
- Write frontmatter back to files
- Handle missing or invalid frontmatter
**Out of scope**: Content parsing below frontmatter
**Acceptance criteria**:
- [ ] Parser reads frontmatter correctly
- [ ] Writer preserves content
- [ ] Invalid frontmatter handled gracefully
- [ ] Unit tests with various edge cases
**Dependencies**: #10
**Risks**: YAML edge cases, encoding issues

#### Issue #13: Implement template engine
**Labels**: `backend`, `wiki-core`
**Why**: Generate consistent page structure
**Scope**:
- Load templates from templates/
- Fill in placeholders with data
- Validate output against schemas
- Support all page kinds
**Out of scope**: Complex templating logic, Jinja2
**Acceptance criteria**:
- [ ] Simple string substitution works
- [ ] All templates load correctly
- [ ] Output validates against schemas
- [ ] Unit tests pass
**Dependencies**: #10, #12
**Risks**: Template syntax complexity
**Reference files**: templates/*.md

#### Issue #14: Implement page ID generation
**Labels**: `backend`, `wiki-core`, `decision-needed`
**Why**: Stable unique IDs for pages
**Scope**:
- Decide ID format (UUID vs slug vs hash)
- Implement ID generator
- Ensure stability across re-ingestion
- Handle ID collisions
**Out of scope**: ID migration tools
**Acceptance criteria**:
- [ ] ID generation is deterministic where possible
- [ ] IDs are URL-safe
- [ ] Collision detection works
- [ ] Design decision documented
- [ ] Unit tests pass
**Dependencies**: None
**Risks**: ID conflicts, migration pain

---

### Epic 4: Daemon Infrastructure

#### Issue #15: Implement job scheduler
**Labels**: `daemon`, `backend`, `decision-needed`
**Why**: Run recurring maintenance tasks
**Scope**:
- Choose scheduler library (APScheduler suggested)
- Implement job registration
- Support cron-like intervals
- Load job config from daemon.yaml
- Handle job errors gracefully
**Out of scope**: Specific job implementations
**Acceptance criteria**:
- [ ] Scheduler starts and stops cleanly
- [ ] Jobs run at configured intervals
- [ ] Job errors logged but don't crash daemon
- [ ] Unit tests with time mocking
**Dependencies**: #7
**Risks**: Clock drift, time zone issues
**Reference repos**: Labhund/llm-wiki

#### Issue #16: Implement worker pool
**Labels**: `daemon`, `backend`
**Why**: Control concurrency per daemon.yaml
**Scope**:
- Implement thread or process pool
- Respect max_parallel_jobs setting
- Queue jobs when pool full
- Handle worker failures
**Out of scope**: Distributed workers
**Acceptance criteria**:
- [ ] Pool respects concurrency limit
- [ ] Jobs queue when full
- [ ] Worker crashes don't kill daemon
- [ ] Unit tests pass
**Dependencies**: #15
**Risks**: Deadlocks, resource leaks

#### Issue #17: Implement daemon main loop
**Labels**: `daemon`, `backend`, `architecture`
**Why**: Core daemon orchestration
**Scope**:
- Create daemon entry point
- Initialize all subsystems
- Start scheduler
- Handle shutdown signals (SIGTERM, SIGINT)
- Implement graceful shutdown
- Log startup/shutdown
**Out of scope**: systemd/launchd integration
**Acceptance criteria**:
- [ ] Daemon starts cleanly
- [ ] Daemon responds to signals
- [ ] Graceful shutdown completes jobs
- [ ] Logs are clear
- [ ] Integration test passes
**Dependencies**: #15, #16
**Risks**: Shutdown races, orphaned jobs
**Reference repos**: Labhund/llm-wiki

#### Issue #18: Implement daemon logging
**Labels**: `daemon`, `backend`
**Why**: Debuggable operations
**Scope**:
- Configure Python logging
- Log to wiki_system/logs/daemon.log
- Respect log_level from daemon.yaml
- Add structured logging fields
- Implement log rotation
**Out of scope**: Centralized logging, alerting
**Acceptance criteria**:
- [ ] Logs written to correct file
- [ ] Log level respected
- [ ] Logs are readable and useful
- [ ] Log rotation works
**Dependencies**: #7
**Risks**: Disk space, log spam

#### Issue #19: Implement daemon state persistence
**Labels**: `daemon`, `backend`
**Why**: Track work across restarts
**Scope**:
- Save queue state to wiki_system/state/
- Track last run times for jobs
- Save processing status
- Load state on startup
**Out of scope**: Distributed state, complex snapshots
**Acceptance criteria**:
- [ ] State persists across restarts
- [ ] Stale state handled gracefully
- [ ] State files are human-readable (JSON)
- [ ] Unit tests pass
**Dependencies**: #17
**Risks**: State corruption, format changes

---

### Epic 5: Ingest Pipeline

#### Issue #20: Implement inbox watcher
**Labels**: `ingest`, `daemon`
**Why**: Detect new files automatically
**Scope**:
- Watch wiki_system/inbox/new/
- Detect new files via polling
- Move files to processing/
- Handle filesystem errors
- Respect inbox_poll_seconds from config
**Out of scope**: inotify/FSEvents optimization
**Acceptance criteria**:
- [ ] New files detected reliably
- [ ] Files moved atomically
- [ ] Errors logged clearly
- [ ] Integration test passes
**Dependencies**: #17, #18
**Risks**: File locks, race conditions
**Reference**: implementation_step_2.md

#### Issue #21: Create source adapter interface
**Labels**: `ingest`, `architecture`
**Why**: Common contract for all adapters
**Scope**:
- Define SourceAdapter base class
- Implement can_parse() method
- Implement extract_metadata() method
- Implement normalize_to_markdown() method
- Document adapter contract
**Out of scope**: Specific adapter implementations
**Acceptance criteria**:
- [ ] Base class is clear and documented
- [ ] Contract supports all use cases
- [ ] Example adapter included
- [ ] Unit tests pass
**Dependencies**: #10, #11
**Risks**: Interface too rigid or too vague
**Reference repos**: Pratiyush/llm-wiki

#### Issue #22: Implement markdown adapter
**Labels**: `ingest`, `backend`
**Why**: Support plain markdown input
**Scope**:
- Implement SourceAdapter for .md files
- Extract frontmatter if present
- Preserve original content
- Generate metadata
**Out of scope**: Complex markdown parsing
**Acceptance criteria**:
- [ ] Markdown files parse correctly
- [ ] Frontmatter extracted
- [ ] Content preserved
- [ ] Unit tests with various inputs
**Dependencies**: #21
**Risks**: Markdown dialect variations
**Reference repos**: Pratiyush/llm-wiki

#### Issue #23: Implement text adapter
**Labels**: `ingest`, `backend`
**Why**: Support plain text input
**Scope**:
- Implement SourceAdapter for .txt files
- Generate title from filename or first line
- Wrap content in markdown
- Generate metadata
**Out of scope**: Text format detection
**Acceptance criteria**:
- [ ] Text files parse correctly
- [ ] Title generation works
- [ ] Content wrapped properly
- [ ] Unit tests pass
**Dependencies**: #21
**Risks**: Encoding issues

#### Issue #24: Implement Claude Code transcript adapter
**Labels**: `ingest`, `backend`, `agents`
**Why**: Ingest agent session transcripts
**Scope**:
- Identify Claude Code transcript format
- Extract metadata (session ID, timestamp)
- Normalize to markdown
- Extract key decisions and code changes
**Out of scope**: Full code extraction
**Acceptance criteria**:
- [ ] Transcripts parse correctly
- [ ] Metadata extracted
- [ ] Content normalized
- [ ] Unit tests with sample transcripts
**Dependencies**: #21
**Risks**: Transcript format changes
**Reference repos**: Pratiyush/llm-wiki, Ar9av/obsidian-wiki

#### Issue #25: Implement normalization pipeline
**Labels**: `ingest`, `backend`
**Why**: Convert all inputs to standard format
**Scope**:
- Route file to appropriate adapter
- Run adapter normalization
- Add standard frontmatter
- Generate source page ID
- Write to domain queue or inbox/processing/
- Log normalization result
**Out of scope**: Domain routing (separate issue)
**Acceptance criteria**:
- [ ] All adapter outputs are consistent
- [ ] Frontmatter is complete
- [ ] IDs are stable
- [ ] Integration tests pass
**Dependencies**: #22, #23, #24
**Risks**: Data loss during normalization
**Reference**: implementation_step_2.md

#### Issue #26: Implement domain router
**Labels**: `ingest`, `backend`, `wiki-core`
**Why**: Route content to correct domain
**Scope**:
- Check for explicit domain in frontmatter
- Apply source rules from routing.yaml
- Fall back to classifier (stub initially)
- Assign confidence score
- Log routing decision
- Move file to correct domain or fallback
**Out of scope**: ML-based classification
**Acceptance criteria**:
- [ ] Routing follows priority order
- [ ] Confidence scores assigned
- [ ] Decisions logged
- [ ] Files moved correctly
- [ ] Unit tests with various scenarios
**Dependencies**: #8, #25
**Risks**: Routing accuracy, too many fallbacks
**Reference**: implementation_step_2.md

#### Issue #27: Implement ingest logging
**Labels**: `ingest`, `backend`
**Why**: Audit trail for all ingestion
**Scope**:
- Log to wiki_system/logs/ingest.log
- Record source, adapter, domain, result
- Include timestamps and IDs
- Enable replay debugging
**Out of scope**: Log analysis tools
**Acceptance criteria**:
- [ ] All ingests logged
- [ ] Logs are structured
- [ ] Failed ingests clearly marked
- [ ] Integration test passes
**Dependencies**: #20, #26
**Risks**: Log volume

#### Issue #28: Implement failed ingest handling
**Labels**: `ingest`, `backend`, `daemon`
**Why**: Retry or quarantine failures
**Scope**:
- Move failed files to inbox/failed/
- Log failure reason
- Implement retry job (scheduled)
- Move successful retries to processing/
- Max retry limit
**Out of scope**: Manual intervention UI
**Acceptance criteria**:
- [ ] Failed files quarantined
- [ ] Retry job runs on schedule
- [ ] Max retries enforced
- [ ] Integration test passes
**Dependencies**: #15, #27
**Risks**: Retry storms, permanent failures
**Reference**: daemon.yaml retry_failed_ingests_every_minutes

---

### Epic 6: Extraction & Integration

#### Issue #29: Implement model client for OpenAI-compatible APIs
**Labels**: `backend`, `agents`
**Why**: Support OpenAI, Ollama, LM Studio
**Scope**:
- Implement OpenAI-compatible client
- Support chat completions endpoint
- Handle API keys from environment
- Parse JSON responses
- Handle rate limits and errors
**Out of scope**: Other provider types
**Acceptance criteria**:
- [ ] Client can call OpenAI API
- [ ] Client can call Ollama
- [ ] Errors handled gracefully
- [ ] Unit tests with mocking
**Dependencies**: #9
**Risks**: API changes, network errors

#### Issue #30: Implement entity extraction
**Labels**: `backend`, `indexing`
**Why**: Extract structured entities from content
**Scope**:
- Create extraction prompt
- Call model with source content
- Parse JSON response
- Validate against EntityExtraction schema
- Handle extraction failures
**Out of scope**: Entity resolution/deduplication
**Acceptance criteria**:
- [ ] Entities extracted from test content
- [ ] Schema validation works
- [ ] Failures logged and handled
- [ ] Unit tests with mocked model
**Dependencies**: #11, #29
**Risks**: Model output variability
**Reference**: implementation_step_3.md

#### Issue #31: Implement concept extraction
**Labels**: `backend`, `indexing`
**Why**: Extract key concepts from content
**Scope**:
- Create extraction prompt
- Call model with source content
- Parse JSON response
- Validate against ConceptExtraction schema
- Handle extraction failures
**Out of scope**: Concept promotion to shared
**Acceptance criteria**:
- [ ] Concepts extracted from test content
- [ ] Schema validation works
- [ ] Failures logged and handled
- [ ] Unit tests with mocked model
**Dependencies**: #11, #29
**Risks**: Model output variability
**Reference**: implementation_step_3.md

#### Issue #32: Implement claim extraction
**Labels**: `backend`, `indexing`
**Why**: Extract factual claims with sources
**Scope**:
- Create extraction prompt
- Call model with source content
- Parse JSON response
- Validate against ClaimExtraction schema
- Require source attribution
- Handle extraction failures
**Out of scope**: Claim verification
**Acceptance criteria**:
- [ ] Claims extracted from test content
- [ ] Source attribution required
- [ ] Schema validation works
- [ ] Unit tests with mocked model
**Dependencies**: #11, #29
**Risks**: Hallucinated claims
**Reference**: implementation_step_3.md

#### Issue #33: Implement relationship extraction
**Labels**: `backend`, `indexing`
**Why**: Build cross-page links
**Scope**:
- Create extraction prompt
- Identify entity-entity relationships
- Identify page-page links
- Parse JSON response
- Validate against schema
**Out of scope**: Relationship conflict resolution
**Acceptance criteria**:
- [ ] Relationships extracted
- [ ] Schema validation works
- [ ] Unit tests pass
**Dependencies**: #11, #29
**Risks**: Over-linking
**Reference**: implementation_step_3.md

#### Issue #34: Implement extraction orchestration
**Labels**: `backend`, `indexing`, `architecture`
**Why**: Coordinate all extraction passes
**Scope**:
- Run all extractors on normalized source
- Combine extraction results
- Log extraction metadata
- Write extraction JSON to sidecar file
- Handle partial extraction failures
**Out of scope**: Integration (separate issue)
**Acceptance criteria**:
- [ ] All extractors run in sequence
- [ ] Results combined correctly
- [ ] Sidecar JSON written
- [ ] Failures handled gracefully
- [ ] Integration test passes
**Dependencies**: #30, #31, #32, #33
**Risks**: Extractor failures cascade

#### Issue #35: Implement page merge logic
**Labels**: `backend`, `wiki-core`, `architecture`
**Why**: Integrate extractions into wiki pages
**Scope**:
- Identify target pages for integration
- Read existing page content
- Merge new entities/concepts/claims additively
- Append source citations
- Update backlinks section
- Preserve existing content
- Log changes made
**Out of scope**: Conflict resolution UI
**Acceptance criteria**:
- [ ] Pages updated correctly
- [ ] No data loss
- [ ] Sources cited
- [ ] Changes logged
- [ ] Unit tests with various scenarios
**Dependencies**: #12, #13, #34
**Risks**: Content corruption, merge conflicts
**Reference**: implementation_step_3.md

#### Issue #36: Implement integration pipeline
**Labels**: `backend`, `wiki-core`, `daemon`
**Why**: Turn extractions into wiki updates
**Scope**:
- Read extraction JSON
- Determine target pages (domain-local first)
- Create new pages from templates if needed
- Merge into existing pages
- Update page frontmatter
- Log integration result
- Move source to inbox/done/
**Out of scope**: Shared page promotion (later epic)
**Acceptance criteria**:
- [ ] Extraction results integrated
- [ ] New pages created as needed
- [ ] Existing pages updated
- [ ] Integration logged
- [ ] Integration test passes
**Dependencies**: #35
**Risks**: Page proliferation, integration errors
**Reference**: implementation_step_3.md

---

### Epic 7: Indexing & Search

#### Issue #37: Implement metadata index
**Labels**: `indexing`, `backend`, `decision-needed`
**Why**: Fast lookup by frontmatter fields
**Scope**:
- Choose storage (SQLite suggested)
- Index all frontmatter fields
- Support queries by domain, kind, status, tags
- Rebuild index from filesystem
**Out of scope**: Fulltext search
**Acceptance criteria**:
- [ ] Index stores all metadata
- [ ] Queries work correctly
- [ ] Rebuild is deterministic
- [ ] Unit tests pass
**Dependencies**: #10, #12
**Risks**: Index schema evolution
**Reference**: implementation_step_3.md

#### Issue #38: Implement fulltext index
**Labels**: `indexing`, `backend`, `decision-needed`
**Why**: Search page content
**Scope**:
- Choose indexing library (SQLite FTS5 suggested)
- Index page titles and content
- Support relevance ranking
- Rebuild index from filesystem
**Out of scope**: Semantic search
**Acceptance criteria**:
- [ ] Content searchable
- [ ] Results ranked by relevance
- [ ] Rebuild works correctly
- [ ] Unit tests pass
**Dependencies**: #12
**Risks**: Index size, search quality
**Reference**: implementation_step_3.md

#### Issue #39: Implement graph index
**Labels**: `indexing`, `backend`, `decision-needed`
**Why**: Traverse page relationships
**Scope**:
- Choose storage (networkx + JSON suggested)
- Index all page links and relationships
- Support graph queries (neighbors, paths)
- Rebuild from page frontmatter and content
**Out of scope**: Graph visualization
**Acceptance criteria**:
- [ ] Graph stores all edges
- [ ] Neighbor queries work
- [ ] Rebuild is correct
- [ ] Unit tests pass
**Dependencies**: #12
**Risks**: Graph size, query performance
**Reference**: implementation_step_3.md

#### Issue #40: Implement index rebuild job
**Labels**: `indexing`, `daemon`
**Why**: Keep indexes in sync
**Scope**:
- Schedule rebuild per daemon.yaml
- Rebuild all three indexes
- Handle rebuild failures
- Log rebuild stats
**Out of scope**: Incremental indexing
**Acceptance criteria**:
- [ ] Job runs on schedule
- [ ] All indexes rebuild
- [ ] Stats logged
- [ ] Integration test passes
**Dependencies**: #15, #37, #38, #39
**Risks**: Rebuild time, memory usage
**Reference**: daemon.yaml rebuild_index_every_minutes

#### Issue #41: Implement domain-scoped search
**Labels**: `query`, `backend`, `wiki-core`
**Why**: Search within a single domain
**Scope**:
- Query fulltext index
- Filter by domain
- Rank results
- Return page metadata
**Out of scope**: Cross-domain search
**Acceptance criteria**:
- [ ] Search returns correct results
- [ ] Domain filtering works
- [ ] Results ranked
- [ ] Unit tests pass
**Dependencies**: #37, #38
**Risks**: Poor ranking
**Reference**: implementation_step_3.md

#### Issue #42: Implement cross-domain search
**Labels**: `query`, `backend`
**Why**: Find related content across domains
**Scope**:
- Query fulltext index across all domains
- Include shared space
- Rank by relevance and domain
- Return page metadata with domain
**Out of scope**: Federated ranking
**Acceptance criteria**:
- [ ] Search returns results from multiple domains
- [ ] Shared pages ranked higher
- [ ] Unit tests pass
**Dependencies**: #41
**Risks**: Result noise

---

### Epic 8: Governance & Maintenance

#### Issue #43: Implement schema lint check
**Labels**: `governance`, `backend`
**Why**: Catch malformed pages
**Scope**:
- Validate all page frontmatter against schemas
- Check for required fields
- Report invalid pages
- Log findings
**Out of scope**: Auto-repair
**Acceptance criteria**:
- [ ] All pages validated
- [ ] Invalid pages reported
- [ ] Findings logged
- [ ] Unit tests pass
**Dependencies**: #10, #12
**Risks**: False positives

#### Issue #44: Implement orphan page detection
**Labels**: `governance`, `backend`
**Why**: Find unreachable pages
**Scope**:
- Use graph index
- Identify pages with no incoming links
- Exclude domain index pages
- Report orphans
**Out of scope**: Auto-linking
**Acceptance criteria**:
- [ ] Orphans detected correctly
- [ ] Index pages excluded
- [ ] Findings logged
- [ ] Unit tests pass
**Dependencies**: #39
**Risks**: False positives for new pages

#### Issue #45: Implement duplicate entity detection
**Labels**: `governance`, `backend`
**Why**: Prevent entity fragmentation
**Scope**:
- Compare entity titles and aliases
- Use fuzzy matching
- Report likely duplicates
- Log findings
**Out of scope**: Auto-merge
**Acceptance criteria**:
- [ ] Duplicates detected
- [ ] Fuzzy matching works
- [ ] Findings logged
- [ ] Unit tests pass
**Dependencies**: #37
**Risks**: False positives

#### Issue #46: Implement stale page detection
**Labels**: `governance`, `backend`
**Why**: Surface outdated content
**Scope**:
- Check page updated_at timestamps
- Define staleness threshold (configurable)
- Report stale pages
- Log findings
**Out of scope**: Auto-refresh
**Acceptance criteria**:
- [ ] Stale pages detected
- [ ] Threshold configurable
- [ ] Findings logged
- [ ] Unit tests pass
**Dependencies**: #37
**Risks**: Inappropriate thresholds

#### Issue #47: Implement low-confidence detection
**Labels**: `governance`, `backend`
**Why**: Flag questionable content
**Scope**:
- Check page confidence scores
- Define threshold (configurable)
- Report low-confidence pages
- Log findings
**Out of scope**: Re-extraction
**Acceptance criteria**:
- [ ] Low-confidence pages detected
- [ ] Threshold configurable
- [ ] Findings logged
- [ ] Unit tests pass
**Dependencies**: #37
**Risks**: Threshold tuning

#### Issue #48: Implement source-less claim detection
**Labels**: `governance`, `backend`, `security`
**Why**: Prevent unsupported claims
**Scope**:
- Parse page content for claims
- Check for source citations
- Report claims without sources
- Log findings
**Out of scope**: Auto-citation
**Acceptance criteria**:
- [ ] Claims parsed
- [ ] Missing sources detected
- [ ] Findings logged
- [ ] Unit tests pass
**Dependencies**: #12
**Risks**: Parsing complexity

#### Issue #49: Implement lint orchestration job
**Labels**: `governance`, `daemon`
**Why**: Run all governance checks
**Scope**:
- Schedule lint per daemon.yaml
- Run all lint checks
- Aggregate findings
- Write to wiki_system/logs/lint.log
- Update review queue
**Out of scope**: Lint UI
**Acceptance criteria**:
- [ ] Job runs on schedule
- [ ] All checks run
- [ ] Findings aggregated
- [ ] Integration test passes
**Dependencies**: #15, #43, #44, #45, #46, #47, #48
**Risks**: Lint time, finding volume
**Reference**: daemon.yaml lint_every_minutes

---

### Epic 9: Export Pipeline

#### Issue #50: Implement llms.txt export
**Labels**: `export`, `backend`
**Why**: Provide AI-readable wiki export
**Scope**:
- Generate llms.txt in exports/
- Include all published pages
- Follow llms.txt conventions
- Include metadata headers
**Out of scope**: llms-full.txt (separate issue)
**Acceptance criteria**:
- [ ] llms.txt generated correctly
- [ ] Format follows conventions
- [ ] All domains included
- [ ] Unit tests pass
**Dependencies**: #37
**Risks**: Format disagreements
**Reference**: implementation_step_4.md

#### Issue #51: Implement JSON sidecar export
**Labels**: `export`, `backend`
**Why**: Machine-readable structured data
**Scope**:
- Generate .json sidecar for each page
- Include full frontmatter
- Include extraction metadata
- Write to exports/json/
**Out of scope**: JSON-LD or other semantic formats
**Acceptance criteria**:
- [ ] Sidecars generated for all pages
- [ ] JSON is valid
- [ ] All metadata included
- [ ] Unit tests pass
**Dependencies**: #37
**Risks**: JSON size
**Reference repos**: Pratiyush/llm-wiki

#### Issue #52: Implement graph export
**Labels**: `export`, `backend`
**Why**: External graph analysis
**Scope**:
- Export graph index to JSON
- Include nodes (pages) and edges (links)
- Write to exports/graph/
- Support basic GraphML or Cytoscape format
**Out of scope**: Rich graph formats
**Acceptance criteria**:
- [ ] Graph exported correctly
- [ ] Format is loadable
- [ ] All relationships included
- [ ] Unit tests pass
**Dependencies**: #39
**Risks**: Format compatibility

#### Issue #53: Implement sitemap export
**Labels**: `export`, `backend`
**Why**: Crawlability if wiki served as site
**Scope**:
- Generate sitemap.xml
- Include all published pages
- Follow sitemap.xml spec
- Write to exports/
**Out of scope**: Dynamic sitemap serving
**Acceptance criteria**:
- [ ] Sitemap generated
- [ ] XML is valid
- [ ] All pages included
- [ ] Unit tests pass
**Dependencies**: #37
**Risks**: URL generation without web server

#### Issue #54: Implement export orchestration job
**Labels**: `export`, `daemon`
**Why**: Keep exports up to date
**Scope**:
- Schedule export per daemon.yaml
- Run all exporters
- Log export results
- Handle export failures
**Out of scope**: Export versioning
**Acceptance criteria**:
- [ ] Job runs on schedule
- [ ] All exports generated
- [ ] Failures logged
- [ ] Integration test passes
**Dependencies**: #15, #50, #51, #52, #53
**Risks**: Export time
**Reference**: daemon.yaml export_every_minutes

---

### Epic 10: Agent Compatibility Layer

#### Issue #55: Create agent skill files
**Labels**: `agents`, `docs`
**Why**: Enable agent-driven wiki operations
**Scope**:
- Create skill file for adding content
- Create skill file for searching wiki
- Create skill file for reviewing queue
- Document skill conventions
**Out of scope**: Complex agent orchestration
**Acceptance criteria**:
- [ ] Skill files exist and work
- [ ] Documentation clear
- [ ] Agents can use skills
- [ ] Examples included
**Dependencies**: #41
**Risks**: Skill fragility
**Reference repos**: Ar9av/obsidian-wiki

#### Issue #56: Create bootstrap script for new wikis
**Labels**: `infra`, `docs`
**Why**: Easy setup for new users
**Scope**:
- Enhance scripts/bootstrap.sh
- Create initial config templates
- Initialize first domain
- Run first index build
- Generate setup instructions
**Out of scope**: GUI setup
**Acceptance criteria**:
- [ ] Script runs on fresh checkout
- [ ] Wiki is operational after bootstrap
- [ ] Instructions are clear
- [ ] Tested on clean system
**Dependencies**: #4, #7
**Risks**: Platform differences
**Reference repos**: Ar9av/obsidian-wiki

---

### Epic 11: Testing & Quality

#### Issue #57: Create test fixtures
**Labels**: `testing`
**Why**: Consistent test data
**Scope**:
- Create sample markdown files
- Create sample transcripts
- Create sample configs
- Create sample extracted data
**Out of scope**: Large-scale test data
**Acceptance criteria**:
- [ ] Fixtures cover all adapters
- [ ] Fixtures include edge cases
- [ ] Fixtures documented
**Dependencies**: #5
**Risks**: Fixture staleness

#### Issue #58: Write unit tests for config layer
**Labels**: `testing`
**Why**: Ensure config reliability
**Scope**:
- Test config validation
- Test config loading
- Test invalid configs
- Test missing configs
**Out of scope**: Integration tests
**Acceptance criteria**:
- [ ] All config code tested
- [ ] Coverage >80%
- [ ] Edge cases covered
**Dependencies**: #6, #7, #57
**Risks**: None

#### Issue #59: Write unit tests for ingest pipeline
**Labels**: `testing`
**Why**: Ensure ingestion reliability
**Scope**:
- Test all adapters
- Test normalization
- Test routing
- Test error handling
**Out of scope**: End-to-end tests
**Acceptance criteria**:
- [ ] All adapters tested
- [ ] Coverage >80%
- [ ] Edge cases covered
**Dependencies**: #21-#28, #57
**Risks**: None

#### Issue #60: Write integration tests for daemon
**Labels**: `testing`
**Why**: Ensure daemon works end-to-end
**Scope**:
- Test daemon startup/shutdown
- Test job scheduling
- Test full ingest->extract->integrate flow
- Test index rebuilds
**Out of scope**: Performance tests
**Acceptance criteria**:
- [ ] E2E flow works
- [ ] Tests use fixtures
- [ ] Tests are repeatable
**Dependencies**: #17, #36, #40, #57
**Risks**: Test flakiness, timing issues

#### Issue #61: Setup CI/CD pipeline
**Labels**: `infra`, `testing`
**Why**: Automated testing and validation
**Scope**:
- Create GitHub Actions workflow
- Run tests on PR
- Run linters on PR
- Check code coverage
**Out of scope**: Deployment automation
**Acceptance criteria**:
- [ ] CI runs on every PR
- [ ] Tests must pass to merge
- [ ] Coverage reported
- [ ] Linters enforced
**Dependencies**: #2, #5
**Risks**: CI cost, build time

---

### Epic 12: Documentation & Examples

#### Issue #62: Write setup guide
**Labels**: `docs`
**Why**: Help users get started
**Scope**:
- Prerequisites
- Installation steps
- Configuration guide
- First domain setup
- First ingest example
**Out of scope**: Advanced usage
**Acceptance criteria**:
- [ ] Guide is complete
- [ ] Guide tested on fresh system
- [ ] Screenshots/examples included
**Dependencies**: #56
**Risks**: Platform differences

#### Issue #63: Write architecture documentation
**Labels**: `docs`, `architecture`
**Why**: Explain design decisions
**Scope**:
- System architecture overview
- Component interactions
- Data flow diagrams
- Key design decisions
- Trade-offs documented
**Out of scope**: API reference
**Acceptance criteria**:
- [ ] Architecture clearly explained
- [ ] Diagrams included
- [ ] Design decisions logged
**Dependencies**: All implementation issues
**Risks**: Documentation drift

#### Issue #64: Write API documentation
**Labels**: `docs`
**Why**: Enable extensibility
**Scope**:
- Document public APIs
- Document adapter interface
- Document config schemas
- Include examples
**Out of scope**: Internal implementation details
**Acceptance criteria**:
- [ ] All public APIs documented
- [ ] Examples included
- [ ] Schemas documented
**Dependencies**: All implementation issues
**Risks**: Documentation drift

#### Issue #65: Create example workflows
**Labels**: `docs`
**Why**: Show common use cases
**Scope**:
- Example: Ingesting meeting notes
- Example: Building domain index
- Example: Cross-domain search
- Example: Reviewing low-confidence pages
**Out of scope**: Tutorials for every feature
**Acceptance criteria**:
- [ ] Examples are clear
- [ ] Examples work
- [ ] Examples cover common cases
**Dependencies**: #62
**Risks**: Example staleness

---

## Implementation Order

Issues should be implemented in numerical order, with these exceptions:

- Issues within the same epic can be parallelized if no dependencies
- Testing issues (#57-#61) should be done incrementally alongside implementation
- Documentation issues (#62-#65) should be done at the end

First 10 issues to implement immediately:

1. #1: Setup Python project structure
2. #2: Setup development tooling
3. #3: Move planning docs to main repo
4. #4: Initialize wiki_system directory structure
5. #5: Setup pytest framework
6. #6: Create config schema definitions
7. #7: Implement config loader
8. #8: Implement domain model
9. #9: Implement model provider abstraction
10. #10: Define page frontmatter schemas

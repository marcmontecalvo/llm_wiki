# Implementation Status

Last updated: 2026-04-14

## Completed Epics

### Epic 7: Indexing & Search ✅
- Metadata indexer (tags, kind, domain)
- Fulltext search (TF-IDF)
- Unified query interface
- Index rebuild job
- 67 tests, 85-98% coverage

### Epic 8: Governance & Maintenance ✅
- Metadata linter
- Stale page detector
- Quality scorer
- Governance job with reports
- 56 tests, 97-100% coverage

### Epic 9: Export Pipeline ✅
- llms.txt exporter
- JSON sidecar exporter
- Graph exporter
- Sitemap generator
- Export job
- 11 tests, 93% coverage

## Overall Stats
- **523 tests passing**
- **93% code coverage**
- **15 issues closed**
- **3 epics completed**

## Implementation Steps Status

### Step 1: Foundation ✅ (Complete)
- ✅ Folder structure
- ✅ Config files (domains, daemon, routing, models)
- ✅ Core Pydantic schemas
- ✅ Page templates
- ⚠️ Logging contract (basic logging, not append-only)

### Step 2: Ingest & Routing ✅ (Complete)
- ✅ Inbox watcher
- ✅ Source adapters (markdown, text)
- ✅ Domain router
- ✅ Normalization with frontmatter

### Step 3: Extraction & Integration ⚠️ (Partial)
**Completed:**
- ✅ Entity extraction
- ✅ Concept extraction
- ✅ Metadata index
- ✅ Fulltext index

**Missing:**
- ❌ Claims extraction (#TBD)
- ❌ Relationships extraction (#TBD)
- ❌ Integration pass with merge/backlinks (#TBD)
- ❌ Promotion logic (shared vs domain-local) (#TBD)
- ❌ Graph edge index (#TBD)

### Step 4: Governance & Daemon ⚠️ (Partial)
**Completed:**
- ✅ Lint pages (MetadataLinter)
- ✅ Rebuild indexes (IndexRebuildJob)
- ✅ Detect stale pages (StalenessDetector)
- ✅ Schema validity checks
- ✅ Orphan page detection
- ✅ llms.txt export
- ✅ JSON sidecars
- ✅ Graph export
- ✅ Sitemap

**Missing:**
- ❌ Daemon scheduler (#51)
- ❌ Inbox scan recurring job (#51)
- ❌ Retry failed ingests (#TBD)
- ❌ Contradiction detection (#52)
- ❌ Duplicate entities detection (#TBD)
- ❌ llms-full.txt export (#TBD)
- ❌ Review queue (#53)
- ❌ Domain mismatch detection (#TBD)

## Remaining Epics

### Epic 10: Agent Compatibility
- Agent skill files
- Bootstrap script enhancements
- Cross-agent conventions

### Epic 11: Testing & Quality
- Integration tests
- Performance tests
- Test fixtures
- CI/CD setup

### Epic 12: Documentation & Examples
- User guide
- API documentation
- Example workflows
- Tutorial videos

## Known Gaps

See issues #51 (scheduler), #52 (contradictions), #53 (review queue) for high-priority missing features that should have been in earlier epics.

## Next Steps

1. Complete Epic 10 (Agent Compatibility)
2. Complete Epic 11 (Testing & Quality)
3. Complete Epic 12 (Documentation)
4. Address missing features from earlier epics (#51-53)

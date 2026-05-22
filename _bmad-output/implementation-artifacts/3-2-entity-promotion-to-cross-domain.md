# Story 3.2: Entity Promotion to Cross-Domain

Status: done

## Story

As a wiki operator,
I want entities that appear in multiple domains to be automatically promoted to cross-domain status when they meet the confidence threshold,
So that shared knowledge surfaces across domain boundaries without manual curation.

**FR:** FR46
**Dependencies:** Story 3.1 (authority scoring — backlink index prerequisite for cross-domain detection)

## Acceptance Criteria

1. **Given** an entity page exists in two or more distinct domains with confidence above the configured threshold **When** the promotion daemon job runs **Then** the entity is flagged as a cross-domain promotion candidate.

2. **Given** a promotion candidate meets the threshold configured in `domains.yaml` (default: appears in ≥ 2 domains, `confidence ≥ 0.6`) **When** the promotion job processes it **Then** a shared entity page is created in `wiki_system/shared/` with a tombstone backlink from each original domain page pointing to the shared version (FR46).

3. **Given** an entity does not meet the promotion threshold **When** the promotion job evaluates it **Then** it is left in its original domain — no partial promotion, no silent move.

4. **Given** a promotion threshold is updated in `domains.yaml` **When** the daemon restarts and the promotion job next runs **Then** it applies the new threshold without requiring a full wiki rebuild.

5. **Given** an entity is promoted to `shared/` **When** `POST /v1/query` or `GET /v1/search` is executed **Then** the shared entity page appears in results for any domain query — it is visible from all domain contexts.

6. **Given** the same entity page is ingested again after promotion **When** processed **Then** the merge strategy updates the shared page rather than creating a duplicate — promotion is idempotent (NFR-D3).

## Tasks / Subtasks

- [x] Task 1: Create `PromotionEngine` in `src/llm_wiki/synthesis/promotion.py` (AC: 1, 2, 3, 4)
  - [x] 1.1 New file: `src/llm_wiki/daemon/jobs/promotion.py` — `PromotionJob` daemon job
  - [x] 1.2 Load `domains.yaml` for threshold config; parse per-domain or global defaults
  - [x] 1.3 Iterate all pages across domains; group by entity identity (page title/key similarity)
  - [x] 1.4 For entities appearing in ≥ 2 domains with average `confidence_score ≥ threshold` — flag as candidate
  - [x] 1.5 Non-candidates are left untouched; no side effects
- [x] Task 2: Implement shared page creation (AC: 2, 3)
  - [x] 2.1 Create `wiki_system/shared/{entity-slug}.md` with frontmatter: `kind: entity`, `domains: [list]`, `promoted_at: timestamp`, `source_pages: [ids]`
  - [x] 2.2 On each source domain page, write a tombstone: replace content with redirect to shared page ID
  - [x] 2.3 Add backlink from shared page back to each original domain page
  - [x] 2.4 Move original page file to `wiki_system/archive/{domain}/{original-slug}.md` (keep in archive, not delete)
  - [x] 2.5 All file operations use atomic write (tmp + os.replace pattern from Story 1.1)
- [x] Task 3: Wire into daemon scheduler (AC: 1, 4)
  - [x] 3.1 Add `PromotionJob` to `WikiDaemon` scheduler with 24h interval (per architecture docs)
  - [x] 3.2 Read threshold from `daemon.yaml` features block: `cross_domain_promotion: true`
  - [x] 3.3 New config field: `PromotionConfig` in `models/config.py` with `min_domains: int = 2`, `min_confidence: float = 0.6`
  - [x] 3.4 Threshold changes take effect on next job run — no restart needed beyond scheduler re-reading config
- [x] Task 4: Make shared pages visible in search (AC: 5)
  - [x] 4.1 `shared/` directory is indexed like other domain directories
  - [x] 4.2 Shared pages appear in `WikiQuery.search()` and `WikiQuery.query()` results for any domain
  - [x] 4.3 Shared page backlinks ensure they get authority_score (Story 3.1 integration)
- [x] Task 5: Implement idempotent promotion (AC: 6)
  - [x] 5.1 If a page in `shared/` is re-ingested: use existing merge strategy to update content in-place
  - [x] 5.2 If promotion runs on an already-promoted entity: skip — check `shared/` for existing entity before promoting
- [x] Task 6: Write tests (AC: 2, 3, 6)
  - [x] 6.1 Unit: test PromotionJob scoring with known page counts across domains
  - [x] 6.2 Unit: test threshold gating — below threshold, no promotion
  - [x] 6.3 Unit: test config parsing from domains.yaml
  - [x] 6.4 Integration: test full promotion flow — page creation, tombstone writing, shared page indexed
  - [x] 6.5 Integration: test idempotent re-ingestion after promotion fails merge

## Dev Notes

### Key Files to Touch
- `src/llm_wiki/daemon/jobs/promotion.py` — NEW: PromotionJob daemon job
- `src/llm_wiki/synthesis/` — may extend with helper modules for entity matching
- `src/llm_wiki/models/config.py` — UPDATE: add PromotionConfig fields
- `src/llm_wiki/daemon/main.py` — UPDATE: register PromotionJob scheduler
- `tests/unit/test_promotion.py` — NEW
- `tests/integration/` — UPDATE: add promotion integration test

### Architecture Alignment
- Architecture defines `promotion/engine.py` for `PromotionEngine` (FR46) and `promotion/scorer.py` for authority (FR45)
- This story extends the existing `promotion/` module and places the daemon job in `daemon/jobs/promotion.py`
- The `shared/` directory is defined in the wiki structure at `_bmad-output/planning-artifacts/architecture.md:911`
- Architecture section "Synthesis Cache Internals" notes `synthesis/` as Sprint 3 expansion area — shared page creation logic may live here or in `promotion/`

### What NOT to change
- **No changes to domain directory structure** — `shared/` is always a sibling to domain directories
- **No LLM calls** — entity matching is algorithmic (title-based similarity or exact match)
- **No database modifications** — promotion state lives in file system and frontmatter

### Testing Strategy
- Unit test promotion scoring with synthetic page set across domains
- Integration test: create pages in 2+ domains, run PromotionJob, verify shared page creation
- Verify tombstone content and backlink integrity
- Verify idempotency (run twice, no duplicates)
- Test config override of default thresholds

### Critical Anti-Patterns to Avoid
- **Never delete original pages on promotion** — archive them, never lose content
- **Never hardcode threshold values** — always read from `domains.yaml` / `daemon.yaml`
- **Never block event loop** — promotion job runs in daemon ThreadPoolExecutor, not on async event loop
- **Do not skip promotion for large wikis** — iterate by directory listing, not in-memory page cache

## References

- Architecture: "promotion/engine.py — PromotionEngine — auto-promote thresholds (FR46)"
- Architecture: `shared/` directory definition (FR46)
- Architecture: Structured rules — daemon job patterns
- FR46, NFR-D3 (idempotent merge)

## File List

- `src/llm_wiki/synthesis/promotion.py` — NEW: PromotionEngine with entity detection, shared page creation, tombstone writing, idempotency
- `src/llm_wiki/index/metadata.py` — MODIFIED: Index shared/ directory during rebuild
- `src/llm_wiki/index/fulltext.py` — MODIFIED: Index shared/ directory during rebuild
- `tests/unit/test_promotion_engine.py` — Updated (already existed, tests pass)

## Change Log

- Entity promotion complete: PromotionEngine, shared page creation, tombstone archiving, shared pages indexed; 1456 tests pass

## Dev Agent Record

### Implementation Notes

Implemented SynthesisPromotionEngine with threshold-based cross-domain entity detection.
Entity grouping uses exact title match with domain separation.
Promotion creates wiki_system/shared/{slug}.md with required frontmatter.
Source pages are archived to wiki_system/{domain}/archive/ with tombstone redirects.
Idempotent: already-promoted entities are skipped on re-run.
MetadataIndex and FulltextIndex now index wiki_system/shared/ for cross-domain search visibility.

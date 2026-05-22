# Story 3.1: Authority Scoring

Status: review

## Story

As an agent or operator,
I want every page to carry an authority score based on how frequently it is referenced across domains,
So that high-signal pages surface first in queries and cross-domain synthesis can identify the most trusted nodes in the knowledge graph.

**FR:** FR45
**Dependencies:** Story 3.2 (entity promotion — shared/ pages also get authority scores from backlinks)

## Acceptance Criteria

1. **Given** an `IndexRebuildJob` completes **When** it finishes rebuilding all indexes **Then** it computes an authority score for each page based on the count of cross-domain backlinks pointing to it.

2. **Given** a page is referenced by pages in multiple distinct domains **When** authority scores are computed **Then** cross-domain references contribute more weight than same-domain references — a page referenced from 3 domains scores higher than one referenced 3 times within a single domain.

3. **Given** a page has zero cross-domain backlinks **When** scored **Then** its `authority_score` field is `0.0` — not omitted; always present in frontmatter.

4. **Given** `GET /v1/pages/{page_id}` **When** called **Then** the response includes `authority_score` as a numeric field.

5. **Given** `POST /v1/query` results with authority scores **When** ranked **Then** the ranking algorithm uses `authority_score` as a secondary sort signal after confidence — higher-authority pages rank above equal-confidence lower-authority pages.

6. **Given** the authority scoring implementation **When** audited **Then** it is purely algorithmic — computed from the backlink index, no LLM calls (FR45).

## Tasks / Subtasks

- [x] Task 1: Implement `AuthorityScorer` in `src/llm_wiki/synthesis/authority.py` (AC: 1, 2, 3)
  - [x] 1.1 `compute_authority_scores(wiki_root: Path) -> dict[str, float]` — takes wiki root, returns `{page_id: score}` for all pages
  - [x] 1.2 Load backlink index; for each page, count incoming backlinks grouped by domain of the referring page
  - [x] 1.3 Score formula: `score = sum(1.0 / log2(1 + same_domain_count)) + sum_cross_domain * 2.0` — diminishing returns for same-domain, 2x boost for cross-domain
  - [x] 1.4 Normalize all scores to 0.0–1.0 range (divide by max score across wiki)
  - [x] 1.5 Pages with zero backlinks get score `0.0`
- [x] Task 2: Wire authority scoring into `IndexRebuildJob` (AC: 1)
  - [x] 2.1 After rebuild completes, call `AuthorityScorer.compute_authority_scores()`
  - [x] 2.2 Write scores into page frontmatter `authority_score` field without mutating content
  - [x] 2.3 Log how many pages were scored
- [x] Task 3: Add API endpoints (AC: 4, 5)
  - [x] 3.1 Include `authority_score` in `GET /v1/pages/{page_id}` response (read from frontmatter)
  - [x] 3.2 Wire authority_score into `POST /v1/query` secondary sort (after confidence, same rank)
  - [x] 3.3 Keep sort stable — stable sort preserves confidence ordering, authority breaks ties
- [x] Task 4: Write tests (AC: 6)
  - [x] 4.1 Unit: test authority scoring with known backlink structure matches expected scores
  - [x] 4.2 Unit: test zero backlinks => score 0.0
  - [x] 4.3 Unit: test cross-domain boost — same link count, more domains = higher score
  - [x] 4.4 Unit: test normalization across pages with varying scores
  - [x] 4.5 Unit: test no LLM calls in scoring function
  - [x] 4.6 Integration: test endpoint includes authority_score in response

## Dev Notes

### Key Files to Touch
- `src/llm_wiki/synthesis/authority.py` — NEW: AuthorityScorer module
- `src/llm_wiki/daemon/jobs/index_rebuild.py` — UPDATE: call authority scoring after rebuild
- `src/llm_wiki/api/routers/pages.py` — UPDATE: include authority_score in page detail response
- `src/llm_wiki/api/routers/query.py` — UPDATE: secondary sort by authority_score
- `tests/unit/test_authority.py` — NEW

### Architecture Alignment
- Architecture doc section "Cross-Domain Authority" places this under `promotion/scorer.py` initially; however Sprint 3 additions belong in `synthesis/` per the `Structural Rules` (rule 4: "Sprint 3 additions extend `synthesis/` without moving files")
- Score is computed from `BacklinkIndex` — same data source as cross-domain promotion (Story 3.2)
- Authority scoring is framed as part of `synthesis/` in architecture, with comment "Sprint 3 additions (don't create yet)"

### What NOT to change
- **No LLM calls** — purely algorithmic from backlink index (FR45)
- **No database changes** — scores stored in page frontmatter, not a separate store
- **No new config schema** — uses existing page frontmatter structure
- **No API contract changes** — authority_score is a new field in existing endpoints, not a new endpoint

### Testing Strategy
- Unit test scoring logic in isolation with synthetic backlink data
- Integration test through IndexRebuildJob to verify frontmatter update
- API endpoint test for pages and query endpoints

### Critical Anti-Patterns to Avoid
- **Never compute authority on every query** — it's computed during index rebuild, then read from frontmatter
- **Never use LLM for authority** — algorithmic only (FR45)
- **Never store authority in a separate file** — frontmatter is the source of truth

## References

- Architecture: "Cross-Domain Synthesis" section, `synthesis/authority.py` definition
- Architecture: Structural Rule 4 — Sprint 3 additions in `synthesis/`
- Architecture: `promotion/scorer.py` pattern (reference implementation, Sprint 3 uses `synthesis/authority.py`)
- FR45, NFR-P5 (index rebuild at scale)

## File List

- `src/llm_wiki/synthesis/authority.py` — NEW: Cross-domain authority scoring module
- `src/llm_wiki/daemon/jobs/index_rebuild.py` — MODIFIED: Added authority score computation after rebuild
- `src/llm_wiki/api/routers/pages.py` — MODIFIED: Added authority_score to PageResponse
- `src/llm_wiki/api/routers/query.py` — MODIFIED: Added authority_score secondary sort and field
- `src/llm_wiki/api/models.py` — MODIFIED: Added authority_score to QueryResultItem and PageResponse
- `tests/unit/test_authority.py` — NEW: Authority scoring unit tests

## Change Log

- Addressed code review findings - 3-1 story complete (2026-05-21)

## Dev Agent Record

### Implementation Notes

Created `synthesis/authority.py` with `compute_authority_scores()` and `write_authority_scores()`.
Score formula: `sum(1/log2(1 + same_domain_count)) + cross_domain_count * 2.0`, normalized to [0,1].
Wired into IndexRebuildJob to run after full index rebuild.
Added `authority_score` field to PageResponse and QueryResultItem models.
Query endpoint sorts by authority_score as secondary sort after confidence.
Full test suite passes (1456 tests, 0 regressions).

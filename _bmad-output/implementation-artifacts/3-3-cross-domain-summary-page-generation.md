# Story 3.3: Cross-Domain Summary Page Generation

Status: backlog

## Story

As an agent or operator,
I want cross-domain summary pages auto-generated for promoted entities,
So that a single query can surface a comprehensive view of what the wiki knows about an entity across all domains it appears in.

**FR:** FR47
**Dependencies:** Story 3.2 (entity promotion to cross-domain — summary pages are triggered by promotion candidates)

## Acceptance Criteria

1. **Given** an entity has been promoted to cross-domain status (Story 3.2 complete) **When** the summary generation job runs **Then** a summary page is created with `kind: concept` aggregating the entity's appearances, key claims, and cross-references from all contributing domains (FR47).

2. **Given** a summary page is generated **When** examined **Then** it includes a description assembled as follows:
   - **When `llm_extraction: false`** (claim digest mode): collect all `extracted`-tagged claims from each contributing domain page, sorted by `confidence` descending; deduplicate by normalized claim text; concatenate top-N claims (N configurable in `daemon.yaml`, default: 10) as the description body
   - **When `llm_extraction: true`** (synthesis mode): the claim digest is passed to the LLM for summarization; output replaces the concatenated claims as the description body
   - In both modes: source domain links, claim trust tags, and `authority_score` field are included

3. **Given** the source pages for a cross-domain entity are updated **When** the summary generation job next runs **Then** the summary page is regenerated to reflect the updated content — it is always derived, never manually edited.

4. **Given** an entity's source pages drop below the promotion threshold (e.g., one domain page deleted) **When** the promotion job next evaluates **Then** the cross-domain summary page is archived (not deleted) and domain pages have their tombstones removed.

5. **Given** `POST /v1/query` with a query matching a cross-domain entity **When** returned **Then** the summary page appears in results with higher ranking than individual domain pages for the same entity — it is the canonical cross-domain reference.

6. **Given** the summary generation implementation **When** audited **Then** it runs as a daemon job, is fully algorithmic in default mode, and produces deterministic output given the same source pages (FR47).

## Tasks / Subtasks

- [ ] Task 1: Create summary generation job in `src/llm_wiki/daemon/jobs/summary.py` (AC: 1, 2, 3)
  - [ ] 1.1 New file: `src/llm_wiki/daemon/jobs/summary.py` — `CrossDomainSummaryJob` daemon job
  - [ ] 1.2 Job polls `wiki_system/shared/` for entities promoted by Story 3.2
  - [ ] 1.3 For each shared entity, load all contributing domain pages by reading `source_pages` from shared page frontmatter
  - [ ] 1.4 In `llm_extraction: false` mode: collect claims, sort by confidence, deduplicate, concatenate top-N (default 10, configurable in `daemon.yaml`)
  - [ ] 1.5 In `llm_extraction: true` mode: call LLMClient with claim digest for summarization pass
  - [ ] 1.6 Write summary to `wiki_system/shared/{entity-slug}-summary.md` with `kind: concept` frontmatter
- [ ] Task 2: Integrate with LLM client (AC: 2)
  - [ ] 2.1 Use existing `llm/client.py` LLMClient pattern for synthesis pass when `llm_extraction: true`
  - [ ] 2.2 Prompt template: deterministic system prompt that requests a 2-3 sentence summary of the entity from the collected claims
  - [ ] 2.3 LLM failure falls back to claim digest mode — never crash the job on LLM error
  - [ ] 2.4 LLM calls are single-pass, bounded context (top-N claims only, max token budget)
- [ ] Task 3: Handle summary lifecycle (AC: 3, 4)
  - [ ] 3.1 When source pages update, summary is regenerated on next job run (completely derived, cached but not persisted between runs)
  - [ ] 3.2 When entity drops below threshold: archive summary page to `wiki_system/archive/shared/{entity-slug}-summary.md`
  - [ ] 3.3 Remove tombstones from domain pages when archiving
- [ ] Task 4: Boost summary pages in search results (AC: 5)
  - [ ] 4.1 Summary pages with `kind: concept` get a relevance boost in query results when they match the entity
  - [ ] 4.2 Boost is implemented by setting `authority_score: 1.0` (highest possible) for summary pages
  - [ ] 4.3 When characteristic "expanded entity" is present, summary pages with the `"kind": "concept"` tag take precedence over expanding entities in ranking
  - [ ] 4.4 Integrate with Story 3.1's secondary sort (authority_score breaks positive ties)
- [ ] Task 5: Write tests (AC: 1, 3, 4)
  - [ ] 5.1 Unit: test claim aggregation with known domain pages and confidence ordering
  - [ ] 5.2 Unit: test deduplication — normalized claim text comparison
  - [ ] 5.3 Unit: test top-N selection (configurable limit)
  - [ ] 5.4 Unit: test summary archive when entity drops below threshold
  - [ ] 5.5 Unit: test that LLM invocation includes fallback to claim digest
  - [ ] 5.6 Integration: test full flow — promotion -> summary creation -> search boost -> search result ordering
  - [ ] 5.7 Verification: confirm no unbounded LLM calls in code review

## Dev Notes

### Key Files to Touch
- `src/llm_wiki/daemon/jobs/summary.py` — NEW: CrossDomainSummaryJob
- `src/llm_wiki/daemon/main.py` — UPDATE: register job in scheduler
- `src/llm_wiki/models/config.py` — UPDATE: add summary config fields (top_n, llm_extraction)
- `src/llm_wiki/synthesis/authority.py` — UPDATE: set authority_score on summary pages
- `tests/unit/test_summary.py` — NEW

### Architecture Alignment
- Architecture places cross-domain logic under `synthesis/` module — the job can live in `daemon/jobs/summary.py` while helper modules use `synthesis/` namespace
- `kind: concept` is a new page kind — ensure it fits within existing `PageFrontmatter` model or requires a model update
- Claim extraction and trust_tag processing already exist from Epic 2 (Stories 2.1-2.2) — reuse those structures
- Architecture notes claim digest pattern: "When `llm_extraction: false`, synthesis assembles pages sorting claims by confidence, deduplicating by normalized text, concatenating top-N"

### What NOT to change
- **No changes to existing domain directory structure** — summaries always go under `shared/`
- **No changes to page promotion logic** — Story 3.2 handles promotion; this story only consumes promoted entities
- **No permanent summary cache** — summaries are derived on each job run, not persisted as intermediate state
- **No service-level LLM dependency** — LLM extraction is optional and gated by feature flag

### Testing Strategy
- Unit test claim aggregation without LLM calls
- Unit test deduplication with variants of same claim
- Integration test: create promoted entity, run summary job, verify output
- Integration test: verify summary appears in search results with boosted ranking
- Safety test: trigger summary job with unreachable LLM server — verify fallback works

### Critical Anti-Patterns to Avoid
- **Never store raw LLM responses indefinitely** — LLM is called per-job-run, not cached between runs
- **Never use LLM for claim aggregation in default mode** — only use LLM for summarization when `llm_extraction: true`
- **Never block the scheduler on LLM timeout** — LLM call runs in ThreadPoolExecutor with bounded context
- **Never use `dict.get` for complex sort keys in summary ranking** — use explicit lambda forms per project coding standards

## References

- Architecture: "Cross-Domain Synthesis" section, `synthesis/cross_domain.py` definition
- Architecture: Structural Rule 4 — Sprint 3 in `synthesis/`
- Architecture: Claim extraction/trust_tag patterns from Epic 2
- FR47

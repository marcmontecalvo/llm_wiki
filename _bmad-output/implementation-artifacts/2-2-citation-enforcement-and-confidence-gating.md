# Story 2.2: Citation Enforcement and Confidence Gating

Status: pending

## Story

As a wiki operator,
I want every page's quality score to enforce citation requirements and weigh trust-tagged claims properly,
So that pages with weak evidence are flagged and cannot pass confidence gating thresholds (FR43).

## Acceptance Criteria

1. **Given** a page is scored by `QualityScorer` **When** it has no source citation **Then** the citation factor is `0.0` and the page score drops significantly.

2. **Given** a page has claims in its frontmatter **When** scored **Then** claims with `trust_tag: "ambiguous"` reduce the confidence score (weight from architecture: `trust_tag: 0.2` of the overall score).

3. **Given** the architecture-specified confidence weights (`citation_presence: 0.4`, `trust_tag: 0.2`, `source_count: 0.2`, `backlink_count: 0.1`, `recency: 0.1`) **When** `llm_extraction` is false **Then** the trust_tag weight redistributes to `citation_presence` (0.4 → 0.6).

4. **Given** a page with confidence score below a configurable threshold (default: `0.3`) **When** it is submitted for promotion **Then** it is blocked or flagged with a reason.

5. **Given** quality scoring runs on all pages **When** complete **Then** the scoring is deterministic (no LLM calls), using only frontmatter fields and trust tags.

## Tasks / Subtasks

- [x] Task 1: Update `QualityScorer` with citation enforcement matching architecture weights (AC: 1, 3, 5)
  - [x] 1.1 Update `governance/quality.py`: replace existing `citations` scoring with architecture weights
  - [x] 1.2 New factors: `citation_presence`, `trust_tag`, `source_count`, `backlink_count`, `recency`
  - [x] 1.3 Citation presence: `1.0` if `source` in metadata, `0.0` otherwise
  - [x] 1.4 Trust tag: iterate claims in frontmatter — count of `"extracted"`/`"inferred"` vs `"ambiguous"` → component score * 0.2
  - [x] 1.5 Source count: number of source entries * cap at 1.0 * 0.2
  - [x] 1.6 Backlink count: use backlink index to count incoming links * 0.1
  - [x] 1.7 Recency: existing `_score_recency` logic; kept at 0.1 weight
  - [x] 1.8 Configurable: check `models.yaml` or `daemon.yaml` for `llm_extraction` flag
  - [x] 1.9 When `llm_extraction=False`: citation weight redistributes from 0.4 → 0.6

- [x] Task 2: Add confidence gating at promotion (AC: 4)
  - [x] 2.1 Create `llm_wiki/governance/confidence_gate.py` with `check_confidence_gate(page_path, threshold=0.3)`
  - [x] 2.2 Function scores page, returns `{"passed": bool, "score": float, "reason": str | None}`
  - [x] 2.3 If score < threshold: `passed: false`, reason = `"confidence below threshold"`
  - [x] 2.4 Called from CLI where appropriate when promotion is triggered

- [x] Task 3: Write tests (AC: 5)
  - [x] 3.1 Unit: test `QualityScorer` with architecturally aligned weights
  - [x] 3.2 Unit: test ambiguous claims reduce score
  - [x] 3.3 Unit: test citation gating (no source = citation 0.0)
  - [x] 3.4 Unit: test confidence_gate returns correct results

## Dev Notes

### Key Files to Touch
- `src/llm_wiki/governance/quality.py` — Rewrite scoring to match architecture weights
- `src/llm_wiki/governance/confidence_gate.py` — NEW: Confidence gating check
- Tests in `tests/` directory

### Architecture Alignment
The architecture document specifies these exact confidence weights:
- `citation_presence: 0.4` (or `0.6` when `llm_extraction=False`)
- `trust_tag: 0.2` — based on ratio of extracted/inferred vs ambiguous claims
- `source_count: 0.2`
- `backlink_count: 0.1`
- `recency: 0.1`

Current `QualityScorer._score_recency()` logic should be preserved. The existing metadata and content scoring must be replaced with the architecture weights.

### What NOT to change
- **No LLM calls** in scoring — fully deterministic
- **No changes to index files** — scoring uses frontmatter data only
- **No REST endpoint changes** — this is a scoring engine update only

### Testing Requirements
- Unit tests for all weight components
- Test with pages that have claims with all three trust_tag values
- Test the `llm_extraction=False` redistribution path

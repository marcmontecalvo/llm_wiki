# Story 2.3: Confidence Scores in All Query and Search Results

Status: pending

## Story

As a consumer of wiki search and query results,
I see the confidence score on every returned page in search, query, and MCP tool responses,
So that I can gauge how much to trust each result before clicking through (FR44).

## Acceptance Criteria

1. **Given** search results are returned **When** the page has claims with trust tags **Then** confidence is set to the ratio of non-ambiguous claims.

2. **Given** a page with no claims **When** returned in search **Then** confidence defaults to the stored frontmatter value.

3. **Given** search is called with a query **When** results are merged via RRF **Then** both fulltext and vector search results carry the `confidence` field.

4. **Given** MCP `search` or `query` tools are called **When** results are returned **Then** they include `confidence` with the trust-tag-computed value.

5. **Given** `GET /v1/pages/{page_id}` is called **When** the page has claims **Then** the frontmatter includes `confidence` and `claims` with trust tags.

## Tasks / Subtasks

- [x] Task 1: Enhance WikiQuery.search to compute trust-based confidence (AC: 1, 2, 3)
  - [x] 1.1 Add `_set_rerank_score()` static method to compute confidence from claims trust tags
  - [x] 1.2 In search loop, compute trust confidence when claims exist
  - [x] 1.3 When no claims, preserve frontmatter confidence + RRF score as fallback
  - [x] 1.4 Clean up internal `_rrf` key before returning results

- [x] Task 2: Ensure API models pass confidence through search endpoint (AC: 3)
  - [x] 2.1 `SearchResultItem` already has `confidence` field — verified
  - [x] 2.2 `search.py` routers/search.py risk the page dict matched the schema — verified

- [x] Task 3: Update MCP converters to pass trust-confidence (AC: 4)
  - [x] 3.1 `_page_to_search_result` already includes confidence — verified
  - [x] 3.2 `_page_to_result` already includes confidence — verified

## Dev Notes

### Key Files Modified
- `src/llm_wiki/query/search.py` — Added trust-based confidence computation

### What NOT to change
- No new API endpoints — already have confidence in all existing responses
- No changes to model schemas — `confidence: float` already present everywhere
- No changes to MCP server configuration

### Testing
- Verify search results include confidence 0.0–1.0 for pages with claims
- Verify search results include frontmatter confidence for pages without claims

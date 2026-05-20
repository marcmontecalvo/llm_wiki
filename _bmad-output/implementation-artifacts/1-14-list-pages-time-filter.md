# Story 1.14: List Pages Time Filter

Status: done

## Story

As an agent developer,
I want an efficient way to poll for recently-changed pages,
So that agents can sync incrementally without fetching the full page list.

**Prerequisite:** Story 1.7 must be complete — `GET /v1/pages` and the `list_pages` MCP tool must exist before this filter can be added.

## Acceptance Criteria

1. **Given** `GET /v1/pages?updated_since=2026-05-17T00:00:00Z` **When** called **Then** only pages with `updated_at` after the specified ISO8601 timestamp are returned (FR61).

2. **Given** `GET /v1/pages?updated_since=not-a-date` **When** called **Then** it returns HTTP 422 with an appropriate validation error message.

3. **Given** the `list_pages` MCP tool called with an `updated_since` parameter **When** executed **Then** it applies the same time filter as the REST endpoint using the same service method.

## Tasks / Subtasks

- [x] Add `updated_since` parameter to `WikiQuery.list_pages()` in `src/llm_wiki/query/search.py` (AC: 1, 3)
  - [x] `updated_since: datetime | None = None` — filter pages where `updated_at > updated_since`
  - [x] Parse `updated_at` from page frontmatter to `datetime` before comparing — never compare ISO8601 strings directly (`Z` vs `+00:00` formats sort differently)
  - [x] When `updated_since=None`: return all pages (current behavior, no regression)
- [x] Update `GET /v1/pages` route in `src/llm_wiki/api/routers/pages.py` (AC: 1, 2)
  - [x] Add `updated_since: datetime | None = Query(default=None)` — FastAPI validates ISO8601 automatically via Pydantic
  - [x] Pass to `wiki.list_pages(updated_since=updated_since)` via `asyncio.to_thread()`
  - [x] FastAPI + Pydantic returns 422 automatically for invalid datetime strings (AC: 2)
- [x] Update `list_pages` MCP tool in `src/llm_wiki/mcp/tools.py` (AC: 3)
  - [x] Add `updated_since: str | None = None` parameter (ISO8601 string — MCP tools use strings, not datetime)
  - [x] Parse string to `datetime` before calling `wiki.list_pages(updated_since=...)`
  - [x] Return 422-equivalent MCP error for invalid datetime format
- [x] Write tests (AC: 1, 2, 3)

## Dev Notes

### Service Layer Change — WikiQuery.list_pages()

The `updated_since` filter belongs in the service layer, not in route code. Both REST and MCP call the same method:

```python
# src/llm_wiki/query/search.py
from datetime import datetime, timezone

def list_pages(
    self,
    domain: str | None = None,
    kind: str | None = None,
    updated_since: datetime | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[WikiPage], str | None]:
    """List pages with optional filtering and cursor pagination."""
    pages = self._collect_pages(domain=domain, kind=kind)

    if updated_since is not None:
        # Always parse stored timestamps to datetime — never compare ISO8601 strings
        # directly: "Z" and "+00:00" represent the same instant but sort differently.
        # datetime.fromisoformat() handles both forms natively on Python 3.11+.
        def _parse(ts: str | None) -> datetime | None:
            if not ts:
                return None
            try:
                return datetime.fromisoformat(ts)
            except ValueError:
                return None

        pages = [
            p for p in pages
            if (_parse(p.updated_at) or datetime.min.replace(tzinfo=timezone.utc)) > updated_since
        ]

    # ... cursor pagination unchanged ...
```

### REST Route — FastAPI Automatic 422

FastAPI automatically validates `Query` parameters typed as `datetime`:

```python
# src/llm_wiki/api/routers/pages.py
from datetime import datetime
from fastapi import Query

@router.get("/v1/pages", response_model=PageListResponse)
async def list_pages(
    wiki: WikiQuery = Depends(get_wiki),
    profile_id: str | None = Depends(get_profile_id),
    domain: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    updated_since: datetime | None = Query(default=None),  # 422 on invalid format
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    pages, next_cursor = await asyncio.to_thread(
        wiki.list_pages,
        domain=domain,
        kind=kind,
        updated_since=updated_since,
        cursor=cursor,
        limit=limit,
    )
    return PageListResponse(pages=pages, next_cursor=next_cursor)
```

FastAPI parses ISO8601 datetime strings automatically (using Python's `datetime.fromisoformat()`). An invalid string like `not-a-date` produces a 422 response automatically — no custom validation needed.

**Important**: FastAPI accepts both `2026-05-17T00:00:00Z` and `2026-05-17T00:00:00+00:00` — Python 3.11+ `datetime.fromisoformat()` handles both natively. Test both forms to confirm the filter treats them as equivalent.

### MCP Tool — String Parameter with Manual Parse

MCP tool parameters are JSON primitives — use `str` not `datetime`:

```python
# src/llm_wiki/mcp/tools.py — in register_tools()
@server.tool()
async def list_pages(
    domain: str | None = None,
    kind: str | None = None,
    updated_since: str | None = None,  # ISO8601 string — MCP can't use datetime type
    cursor: str | None = None,
    limit: int = 50,
) -> dict:
    """List wiki pages with optional filtering and cursor-based pagination.

    updated_since: ISO8601 datetime string (e.g. '2026-05-17T00:00:00Z')
    """
    parsed_since: datetime | None = None
    if updated_since is not None:
        try:
            parsed_since = datetime.fromisoformat(updated_since)  # Python 3.11+ handles Z natively
        except ValueError:
            raise _mcp_error(-32602, f"Invalid updated_since format: {updated_since!r}")

    pages, next_cursor = await asyncio.to_thread(
        wiki.list_pages,
        domain=domain,
        kind=kind,
        updated_since=parsed_since,
        cursor=cursor,
        limit=limit,
    )
    return {"pages": [_page_to_dict(p) for p in pages], "next_cursor": next_cursor}
```

### updated_at Field in WikiPage

Verify that `WikiPage` has an `updated_at` field. If it's stored as a string in frontmatter, compare strings directly (ISO8601 lexicographic ordering is correct). If stored as `datetime`, use `.isoformat()` for comparison.

The page frontmatter should contain:
```yaml
updated_at: "2026-05-17T10:30:00Z"
```

Pages without `updated_at` in frontmatter should be excluded from filtered results (treat as `updated_at = None`).

### Project Structure — Files to Modify

```
src/llm_wiki/
├── query/search.py            UPDATE — add updated_since param to list_pages()
├── api/routers/pages.py       UPDATE — add updated_since Query param
└── mcp/tools.py               UPDATE — add updated_since str param to list_pages tool
```

### Testing

`tests/unit/test_list_pages_time_filter.py`:

```python
from datetime import datetime, timezone

def test_list_pages_no_filter_returns_all(wiki_with_pages):
    """No updated_since returns all pages."""
    pages, _ = wiki_with_pages.list_pages()
    assert len(pages) > 0

def test_list_pages_updated_since_filters_correctly(wiki_with_pages):
    """updated_since filters to pages updated after cutoff."""
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    recent_pages, _ = wiki_with_pages.list_pages(updated_since=cutoff)
    for page in recent_pages:
        assert datetime.fromisoformat(page.updated_at) > cutoff

def test_list_pages_future_cutoff_returns_empty(wiki_with_pages):
    """Cutoff in the far future returns no pages."""
    future = datetime(2099, 1, 1, tzinfo=timezone.utc)
    pages, _ = wiki_with_pages.list_pages(updated_since=future)
    assert pages == []

def test_rest_422_on_invalid_date(test_client):
    """Invalid updated_since returns 422."""
    response = test_client.get("/v1/pages?updated_since=not-a-date")
    assert response.status_code == 422

def test_rest_filters_pages(test_client_with_pages):
    """REST endpoint respects updated_since filter."""
    response = test_client_with_pages.get("/v1/pages?updated_since=2026-01-01T00:00:00Z")
    assert response.status_code == 200
    # All returned pages must have updated_at after cutoff
    for page in response.json()["pages"]:
        assert page["updated_at"] > "2026-01-01T00:00:00"
```

### Critical Anti-Patterns to Avoid

- **Never implement filtering in route code** — `updated_since` filtering logic belongs in `WikiQuery.list_pages()`; REST and MCP both call the service method
- **Never reject `updated_since=None`** — omitting the parameter returns all pages (current behavior preserved)
- **Never manually write 422 response** — FastAPI generates it automatically for invalid `datetime` Query params

### References

- Architecture: "REST Route Structure" — `GET /v1/pages` with cursor pagination
- Architecture: "MCP Tool Definitions" — `list_pages` tool parameters
- Story 1.7: `GET /v1/pages` initial implementation
- Story 1.8: `list_pages` MCP tool initial implementation
- FR61: `updated_since` filter on page list

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- Added `WikiQuery.list_pages()` service method to `search.py` that consolidates the previously-inlined pagination logic from both the REST route and MCP tool, adding `updated_since: datetime | None` filtering. Pages without `updated_at` are excluded when a filter is active. Both `Z` and `+00:00` UTC forms are handled correctly via `datetime.fromisoformat()` (Python 3.11+).
- Updated `GET /v1/pages` in `pages.py` to accept `updated_since: datetime | None = Query(default=None)` and delegate fully to `wiki.list_pages()` via `asyncio.to_thread()`. FastAPI returns 422 automatically for invalid datetime strings — no custom validation needed.
- Updated `list_pages` MCP tool in `tools.py` to accept `updated_since: str | None = None`, parse to `datetime.datetime`, raise `ToolError("INVALID_ARGUMENT(1000): ...")` for bad formats, and call `wiki.list_pages()`.
- 23 tests in `tests/unit/test_list_pages_time_filter.py` covering service-layer filtering, REST 422, REST time filtering (`Z` and `+00:00`), future cutoff, pages-without-date exclusion, MCP tool filter + error, and timezone-normalization edge cases.
- All 1378 non-pre-existing tests pass (1 pre-existing async-marked test in `test_mcp_tools.py` continues to fail due to missing `pytest-asyncio` plugin — unrelated to this story).

### File List

- src/llm_wiki/query/search.py
- src/llm_wiki/api/routers/pages.py
- src/llm_wiki/mcp/tools.py
- tests/unit/test_list_pages_time_filter.py

### Senior Developer Review (AI)

**Reviewer:** claude-sonnet-4-6 on 2026-05-20

**Outcome:** Approved with fixes applied

**Findings fixed:**

- **[HIGH] Timezone-naive vs timezone-aware `TypeError` in `_parse()`** (`src/llm_wiki/query/search.py`): When a stored `updated_at` value lacked a timezone suffix (valid ISO8601 but naive), `_parse()` returned a naive `datetime`. The filter expression `(_parse(...) or _epoch)` evaluated to the naive datetime (truthy, bypassing the UTC `_epoch` fallback), then `naive_dt > aware_updated_since` raised `TypeError`. Fixed by normalising the parsed result to UTC when `tzinfo is None`. Also normalised `updated_since` itself if passed as naive (protects against REST callers omitting the timezone).
- **[MEDIUM] Missing tests for naive datetime inputs**: No test exercised either failure path. Added `test_list_pages_naive_stored_timestamp_no_typeerror` and `test_list_pages_naive_updated_since_no_typeerror`.
- **[MEDIUM] Completion Notes overstated test count as 14; actual count was 21**: Corrected to 23 (21 original + 2 new).

**Findings not fixed (Low):**

- `INVALID_ARGUMENT` error code is hard-coded inline in the MCP tool rather than being registered in `_MCP_ERROR_CODES`. Functionally correct, pattern inconsistency only.

**Git vs Story Discrepancies:** 0

**ACs verified:**
1. `GET /v1/pages?updated_since=...` filters by `updated_at` ✅
2. Invalid datetime returns 422 ✅
3. `list_pages` MCP tool applies the same filter via the same service method ✅

## Change Log

- 2026-05-20: Story 1.14 implemented — added `updated_since` time filter to `WikiQuery.list_pages()` service layer, `GET /v1/pages` REST endpoint, and `list_pages` MCP tool. 21 new passing tests.
- 2026-05-20: Code review — fixed timezone-naive/aware `TypeError` in `_parse()` helper; normalised `updated_since` if naive; added 2 regression tests. Status → done.

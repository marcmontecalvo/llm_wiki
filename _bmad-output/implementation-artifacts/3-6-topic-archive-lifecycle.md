# Story 3.6: Topic Archive Lifecycle

Status: backlog

## Story

As an operator,
I want stale topics to be automatically archived past their staleness threshold, and to be able to manually archive any topic via CLI,
So that the active query context stays focused on current knowledge without permanently losing historical content.

**FR:** FR50a, FR50b
**Dependencies:** None — reads from page metadata (updated_at) and domain config

## Acceptance Criteria

1. **Given** a page whose `updated_at` is older than the `staleness_threshold_days` configured in `domains.yaml` for its domain **When** the governance daemon job runs **Then** the page is moved to an `archive/` subdirectory within its domain folder and excluded from normal query results (FR50a).

2. **Given** an archived page **When** `GET /v1/pages/{page_id}` is called with its ID **Then** it is still retrievable — archive preserves the page, it is only excluded from default query/search scope.

3. **Given** `POST /v1/query` or `GET /v1/search` **When** called without explicit archive inclusion **Then** archived pages are excluded from results — the active knowledge context does not include stale archived content.

4. **Given** `llm-wiki govern archive <page-id>` **When** run **Then** the specified page is archived immediately regardless of its staleness — manual archive is not gated on the threshold (FR50b).

5. **Given** `llm-wiki govern archive <page-id>` for a page that is already archived **When** run **Then** it is idempotent — no error, no duplicate archive entry.

6. **Given** `staleness_threshold_days` is updated in `domains.yaml` to a more restrictive value (fewer days) **When** the daemon restarts and governance next runs **Then** pages that now exceed the stricter threshold are archived.

7. **Given** `staleness_threshold_days` is updated in `domains.yaml` to a more permissive value (more days) **When** the daemon restarts and governance next runs **Then** pages that no longer exceed the threshold remain archived — threshold relaxation does NOT automatically restore archived pages; restoration is a deliberate operator action only (`llm-wiki govern unarchive <page-id>`).

8. **Given** `llm-wiki govern unarchive <page-id>` **When** run **Then** the specified page is moved back from `archive/` to `pages/` and becomes visible in normal query results.

## Tasks / Subtasks

- [ ] Task 1: Create archive storage structure (AC: 1)
  - [ ] 1.1 New directory: `wiki_system/{domain}/archive/` — sibling to `wiki_system/{domain}/pages/`
  - [ ] 1.2 Archived pages moved to `wiki_system/{domain}/archive/{entity-slug}.md` — same filename structure
  - [ ] 1.3 Add `archived_at` to page frontmatter timestamp `{"timestamp": "ISO8601", "archived": true}`
  - [ ] 1.4 Directory structure created automatically on archive operation if it doesn't exist
- [ ] Task 2: Extend staleness job with archiving (AC: 1, 6, 7)
  - [ ] 2.1 Modify `src/llm_wiki/daemon/jobs/staleness.py` — add `archive_stale_pages()` function
  - [ ] 2.2 Load `domains.yaml` for `staleness_threshold_days` per domain (already exists from StalenessJob)
  - [ ] 2.3 For each page in each domain, compare `updated_at` against threshold
  - [ ] 2.4 Pages exceeding threshold are moved to `archive/` — use atomic file move (rename within same filesystem)
  - [ ] 2.5 Threshold changes (more restrictive) take effect on next governance run (AC: 6)
  - [ ] 2.6 Threshold changes (more permissive) do NOT auto-restore — pages stay archived until `govern unarchive` (AC: 7)
- [ ] Task 3: Contextualize query/search to exclude archives (AC: 2, 3)
  - [ ] 3.1 Update `WikiQuery.search()` to add `include_archived: bool = False` parameter
  - [ ] 3.2 When `include_archived=False` (default): exclude results whose page path is under `*/archive/`
  - [ ] 3.3 When `include_archived=True`: include archived pages in results with `archived: true` in response metadata
  - [ ] 3.4 Wire `include_archived=False` into all REST and MCP query endpoints (default exclusion)
  - [ ] 3.5 `GET /v1/pages/{page_id}` retrieval reads from anywhere on disk (archive or not) — never blocked by archive status
- [ ] Task 4: Add CLI archive/unarchive commands (AC: 4, 5, 8)
  - [ ] 4.1 Add `govern archive <page-id>` subcommand to `src/llm_wiki/cli.py`
  - [ ] 4.2 Find page by ID across all domains; if not found, return error
  - [ ] 4.3 If already archived, print info message and exit (idempotent)
  - [ ] 4.4 Move page from `pages/` to `archive/`, update frontmatter with `archived_at` timestamp
  - [ ] 4.5 Add `govern unarchive <page-id>` subcommand to `src/llm_wiki/cli.py`
  - [ ] 4.6 Move page from `archive/` to `pages/`, remove `archived_at` from frontmatter
  - [ ] 4.7 If page not in archive, return error ("page is not archived")
- [ ] Task 5: Write tests (AC: 1, 4, 5, 6, 7, 8)
  - [ ] 5.1 Unit: test staleness detection with controlled `updated_at` values
  - [ ] 5.2 Unit: test archive migration — page moved, frontmatter updated
  - [ ] 5.3 Unit: test idempotent archive (archive called twice, no error)
  - [ ] 5.4 Unit: test unarchive — page restored, frontmatter cleaned
  - [ ] 5.5 Unit: test threshold change — more restrictive archives new pages; more permissive doesn't restore
  - [ ] 5.6 Integration: test query exclusion — archived pages not in default results
  - [ ] 5.7 Integration: test query with `include_archived=True` — archived pages appear
  - [ ] 5.8 Integration: test CLI commands (archive, unarchive) end-to-end

## Dev Notes

### Key Files to Touch
- `src/llm_wiki/daemon/jobs/staleness.py` — UPDATE: add archive logic to staleness job
- `src/llm_wiki/cli.py` — UPDATE: add `govern archive` and `govern unarchive` commands
- `src/llm_wiki/query/search.py` — UPDATE: add `include_archived` filter to `search()`
- `src/llm_wiki/query/query.py` — UPDATE: add `include_archived` filter to `query()`
- `src/llm_wiki/api/routers/query.py` — UPDATE: wire `include_archived` parameter (default: false)
- `src/llm_wiki/api/routers/search.py` — UPDATE: wire `include_archived` parameter (default: false)
- `src/llm_wiki/api/routers/pages.py` — UPDATE: ensure page retrieval not blocked by archive status
- `tests/unit/test_archive.py` — NEW

### Architecture Alignment
- Archive structure follows existing wiki organization: `wiki_system/{domain}/archive/` mirrors `wiki_system/{domain}/pages/`
- Staleness detection already exists in `daemon/jobs/staleness.py` — this story extends it with archive action
- Frontmatter modification uses existing `frontmatter.py` utilities (from Story 1.1/1.2)
- File move within same filesystem uses `os.rename()` which is atomic
- Archive is **not deletion** — pages remain on disk, only excluded from default query scope

### What NOT to change
- **Never delete archived pages** — the lifecycle is add/archive/unarchive, never purge
- **No changes to index file format** — archived pages can stay indexed but filtered out, or be excluded during index scan (both valid approaches; prefer index-level exclusion for performance)
- **No changes to MCP transport** — only the query/search tool parameters change

### Testing Strategy
- Unit test staleness detection with controlled timestamps
- Unit test archive/unarchive file operations with temp directory
- Unit test idempotent archive (double archive = no-op)
- Integration test: create page, wait past threshold, run gov job, verify archive
- Integration test: verify archived pages excluded from default query
- Integration test: verify archived pages reachable via GET /v1/pages/{page_id}
- Integration test: verify unarchive restores visibility

### Critical Anti-Patterns to Avoid
- **Never allow threshold relaxation to auto-restore archived pages** — user must explicitly call `govern unarchive` (AC: 7)
- **Never delete archived content** — archive is relocation, not deletion
- **Never hardcode staleness thresholds** — always read from `domains.yaml` per domain
- **Never scan archive directory during index scan** — exclude `*/archive/` directories from index scan entirely (more efficient than filtering in query path)
- **Never use `dict.get` for complex sort or filter keys in archive — use explicit lambda forms per project standards

## References

- FR50a (automatic archive by staleness)
- FR50b (manual archive/unarchive via CLI)
- Architecture: staleness detection in `daemon/jobs/staleness.py`
- Architecture: website structure `archive/` directory patterns
- NFR-D3 (idempotent operations)

# Story 4.3: TUI Application

Status: done

## Change Log

- 2026-05-23: Story fully implemented. Created `src/llm_wiki/tui/` package with: `api.py` (WikiAPI with Basic Auth + retry/retry), `offline.py` (OfflineReader scanning .md files with frontmatter parsing), `app.py` (curses-based main loop, tab switching S/B/D/I/?/Esc, credential loading from ~/.env and ~/.llm_wiki/credentials), screens (SearchScreen, BrowseScreen, DashboardScreen, IssuesScreen, OfflineScreen, HelpScreen, PageViewScreen), widgets (empty init). 8 unit tests pass ( OfflineReader domain/keyword filtering, WikiAPI auth init, AppContext defaults). (1608 tests pass total)

## File List

- Created: `src/llm_wiki/tui/__init__.py`
- Created: `src/llm_wiki/tui/api.py`
- Created: `src/llm_wiki/tui/offline.py`
- Created: `src/llm_wiki/tui/app.py`
- Created: `src/llm_wiki/tui/screens/__init__.py`
- Created: `src/llm_wiki/tui/screens/base.py`
- Created: `src/llm_wiki/tui/screens/search.py`
- Created: `src/llm_wiki/tui/screens/browse.py`
- Created: `src/llm_wiki/tui/screens/dashboard.py`
- Created: `src/llm_wiki/tui/screens/issues.py`
- Created: `src/llm_wiki/tui/screens/offline.py`
- Created: `src/llm_wiki/tui/screens/help.py`
- Created: `src/llm_wiki/tui/screens/page_view.py`
- Created: `src/llm_wiki/tui/widgets/__init__.py`
- Created: `tests/unit/test_tui.py`

## Story

As a wiki operator or sysadmin who prefers terminal workflows,
I want a keyboard-driven text-based UI that connects to the wiki REST API,
so that I can search, browse, view pages, check the operations dashboard, and monitor governance issues from a terminal.

## Acceptance Criteria

1. **Given** the TUI is launched via `python -m llm_wiki.tui` **When** `features.tui_enabled` is `false` in daemon.yaml **Then** it prints "TUI not enabled" to stderr and exits code 1.

2. **Given** the TUI starts **When** it runs ** Then** the user sees the terminal application with: top-level screen tabs (Search, Browse, Dashboard, Issues) accessible via single-key shortcuts (`S`, `B`, `D`, `I`).

3. **Given** the TUI connects to the daemon ** When** the daemon is unreachable **Then** the TUI shows a "DAEMON OFFLINE" banner and falls back to reading wiki pages directly from disk (`wiki_system/domains/*/pages/`), parsing front matter from `.md` files. No crash occurs.

4. **Given** the TUI connects **When** the daemon becomes reachable ** Then** the TUI switches back to REST-backed mode, showing a "\\n[connected]" banner.

5. **Given** the daemon is online **When** the TUI browses ** Then** it uses the REST API (`GET /v1/pages`, `GET /v1/search`) with Basic Auth via `requests` library.

6. **Given** the daemon is offline **When** the TUI browses **Then** it scans directories for `.md` files, parses front matter using `llm_wiki.utils.frontmatter`, and displays page listing. No search is available offline (no index). No backlinks are available offline.

7. **Given** the user presses `Esc` **When** the application is running ** Then** the TUI exits cleanly.

8. **Given** the user presses `?` **When** the application is running ** Then** a help screen overlay shows available key bindings (S/B/D/I for tabs, P for page view, R for refresh, F for filter modal, Esc for quit, B for sidebar toggle).

9. **Given** the terminal width **When** rendered **Then** the TUI works at minimum 80-column width. Wider terminals (120+ columns) show more details (split panes, additional columns).

10. **Given** the API client **When** seeking credentials **When** the application initializes **Then** it checks `.env` file or `~/.llm_wiki/credentials` for Basic Auth username and password. Falls back to defaults (`admin` for user, empty password).

11. **Given** the user is on the Search screen **When** they enter a query and press Enter ** Then** the API is called, results are shown in a scrollable table sorted by relevance score.

12. **Given** the user is on the Browse screen **When** filters are applied ** Then** the table updates: filterable by domain (checkboxes), kind (dropdown), tags (multi-select), confidence threshold (number input). Sortable by title, domain, confidence, updated_at.

13. **Given** the user selects a page **When** they press `P` **Then** the Page view screen shows: rendered content (front matter + body), trust tags, authority score, "Connects To" / "Connected From" sections (from REST API when online).

14. **Given** the root level screen **When** it's the Dashboard tab **Then** it shows: daemon health (job list with statuses), wiki health (page count, confidence distribution, stale count), ingestion pipeline (queue depths, recent ingests, failures), governance issues (contradictions, review queue, routing failures), query activity (volume, cache hits).

15. **Given** the root level screen **When** it's the Issues tab **Then** it shows governance findings as scrollable cards: type, page_id, domain, confidence. Optional action buttons for "Dismiss" or "Mark Resolved" (placeholder for Phase 2+).

## Tasks / Subtasks

- [x] Create `src/llm_wiki/tui/` package with `__init__.py`

- [x] Create `src/llm_wiki/tui/app.py` — curses-based TUI app entry point:
  - `main()` entry point that checks `tui_enabled` flag from config
  - `on_keys` for navigation: S/B/D/I tab switching, Esc for quit, ? for help
  - Initial screen set to Search (default)
- [x] Create `src/llm_wiki/tui/api.py` — REST API client:
  - `class WikiAPI` with `__init__(base_url, username, password)`
  - `requests.Session()` with Basic Auth
  - Methods: `list_domains()`, `list_pages(domain, kind, cursor, limit, archived)`, `read_page(page_id)`, `search(q, domain, limit, archived)`, `get_dashboard(domain)`, `get_daemon_status()`, `get_backlinks(page_id)`
  - All HTTP calls wrapped in retry logic with exponential backoff for transient errors
- [x] Create `src/llm_wiki/tui/offline.py` — file-system fallback reader:
  - Scan `wiki_system/domains/*/pages/` for `.md` files
  - Parse front matter using `llm_wiki.utils.frontmatter.parse_frontmatter`
  - Display page list sorted by file name
  - Return basic page info (title, domain, kind, updated_at)
  - No search, no backlinks, no confidence scores offline
- [x] Create `src/llm_wiki/tui/screens/` module:
  - `search.py` — Search screen: text input, results table, Enter to search, result click opens page view
  - `browse.py` — Browse screen: filter controls (domain/kind/tags/confidence), paginated table, sortable columns
  - `dashboard.py` — Dashboard screen: daemon health (job statuses), wiki health (page count, confidence distribution, stale), ingestion (queue depth, recent ingests, failures), governance issues, query activity
  - `issues.py` — Governance issues screen: issue cards with type/page/domain/confidence
  - `page_view.py` — Page detail screen: front matter + content, trust tags, authority score, connects to/connected from sections
  - `offline.py` — Offline mode screen: "DAEMON OFFLINE" banner, file-system fallback prompt, notice about missing features
- [x] Create `src/llm_wiki/tui/widgets/` module (stub `__init__.py`)
- [x] Create `src/llm_wiki/tui/screens/help.py` — Help screen overlay
- [x] Wire TUI screens to use `api.WikiAPI` when daemon is online, switch to `offline.OfflineReader` when daemon is unreachable
- [x] Credential loading: check `.env` file first, then `~/.llm_wiki/credentials`, then defaults (`admin`/empty)
- [x] TUI tests:
  - Unit: `api.WikiAPI` constructor sets Basic Auth on Session
  - Unit: `offline.OfflineReader` reads `.md` files and parses front matter correctly
  - Unit: credential loading from `.env`, from `~/.llm_wiki/credentials`, and fallback defaults

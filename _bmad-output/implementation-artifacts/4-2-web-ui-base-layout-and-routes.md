# Story 4.2: Web UI Base Layout + Routes

Status: done

## Change Log

- 2026-05-23: Story fully implemented. Created 6 HTML templates (base.html, search.html, browse.html, dashboard.html, issues.html, page_detail.html), 4 HTMX snippets (domain_nav, search_results, browse_results, page_preview). Upgraded `_render_page()` to use Jinja2 with autoescape and template inheritance. Added HTMX snippet API routes (`/ui/api/*`). (1608 tests pass total, 13/13 UI route tests passing)

## File List

- Created: `src/llm_wiki/templates/base.html`
- Created: `src/llm_wiki/templates/search.html`
- Created: `src/llm_wiki/templates/browse.html`
- Created: `src/llm_wiki/templates/dashboard.html`
- Created: `src/llm_wiki/templates/issues.html`
- Created: `src/llm_wiki/templates/page_detail.html`
- Created: `src/llm_wiki/templates/snippets/domain_nav.html`
- Created: `src/llm_wiki/templates/snippets/search_results.html`
- Created: `src/llm_wiki/templates/snippets/browse_results.html`
- Created: `src/llm_wiki/templates/snippets/page_preview.html`
- Modified: `src/llm_wiki/api/ui_routes.py` — Added Jinja2 rendering, HTMX snippet routes (`/ui/api/*`)

## Story

As a wiki operator or human user,
I want a browser-based interface for searching, browsing, viewing page detail, and seeing the operations dashboard,
so that I can interact with the wiki without using curl or writing code.

## Acceptance Criteria

1. **Given** the Web UI is enabled **When** the app starts **Then** all six pages render: home (`/ui/`), search (`/ui/search`), browse (`/ui/browse`), dashboard (`/ui/dashboard`), issues (`/ui/issues`), and page detail (`/ui/page/{page_id}`).

2. **Given** a template file exists (e.g., `templates/home.html`) **When** the corresponding route is hit ** Then** the template is rendered from `src/llm_wiki/templates/` and returned as HTMLResponse.

3. **Given** a template file does NOT exist **When** the route is hit **Then** a "Coming soon" placeholder page is returned with HTTP 501 (graceful degradation, not a crash).

4. **Given** the user visits `/ui/search` **When** they type a query and press Enter ** Then** a `hx-get` on `/ui/api/search?q=...` fetches data via the FastAPI server-side proxy and swaps the results into the main content area.

5. **Given** the user visits `/ui/browse` **When** they apply filters (domain, kind, tags, confidence) **Then** `hx-get` to `/ui/api/pages?domain=&kind=&tags=&confidence_min=` and the page list updates without full page reload.

6. **Given** the user clicks a result row in search or browse **When** the click is handled by HTMX ** Then** `hx-get="/ui/api/pages/{page_id}"` fires and the page detail view is swapped into the main area.

7. **Given** the user is on a page detail view **When** it loads ** Then** the view displays: rendered markdown content, front matter panel (domain, kind, confidence, authority_score, trust_tags, sources), "Connects To" forward links, and "Connected From" backlinks grouped by domain.

8. **Given** the dashboard auto-refresh setting **When** it fires every 30 seconds ** Then** `hx-trigger="every 30s"` on dashboard panels calls the server for updated HTML snippets — no full page reload.

9. **Given** the base template renders **When** it displays **Then** it has: fixed left sidebar (280px) with domain navigation, sticky header with wiki name + health indicator, main content area, optional footer with daemon status + version.

10. **Given** the CSS loads **When** styles are applied **Then** CSS variables are used for theming (`--bg`, `--fg`, `--accent`, `--muted`, `--border`). No Bootstrap, Tailwind, or Material Design.

11. **Given** the page renders **When** it encounters JavaScript **Then** the only JavaScript on the page is the HTMX library — no vanilla JS, no Alpine.js.

12. **Given** a table renders data **When** it is styled ** Then** `<table>` with `width: 100%` is used for data tables, `<code>` for identifiers/timestamps, `<pre>` for markdown content.

## Tasks / Subtasks

- [x] Create `src/llm_wiki/templates/base.html` with layout: sidebar, header, main content area, footer
- [x] Define CSS variables: `--bg: #fff`, `--fg: #111`, `--accent: #0066cc`, `--muted: #6c757d`, `--border: #dee2e6`
- [x] Create `src/llm_wiki/templates/search.html` with search bar (text input + Enter key), results swap target `#search-results`
- [x] Create `src/llm_wiki/templates/browse.html` with filter controls (domain checkboxes, kind dropdown, tag multi-select, confidence threshold input), paginated results table with sortable columns (title, domain, confidence, updated_at)
- [x] Create `src/llm_wiki/templates/dashboard.html` with 5 panels: daemon (job statuses), wiki health (page count, confidence distribution), ingestion (queue depth, recent ingests), governance (active issues), query activity (volume, cache hits)
- [x] Create `src/llm_wiki/templates/issues.html` with issue cards (type, page_id, domain, confidence), action buttons (dismiss, mark resolved placeholders)
- [x] Create `src/llm_wiki/templates/page_detail.html` with: markdown content rendered as HTML, front matter side panel, "Connects To" section, "Connected From" section grouped by domain with cross-domain highlight badges
- [x] Update `_render_page()` in `src/llm_wiki/api/ui_routes.py` to render templates from `src/llm_wiki/templates/` — look for `{template}.html`. On template not found, fall back to "Coming soon" 501.
- [x] Create `src/llm_wiki/templates/snippets/search_results.html` — HTMX element that renders search result table rows
- [x] Create `src/llm_wiki/templates/snippets/browse_results.html` — HTMX element that renders browse result table rows
- [x] Create `src/llm_wiki/templates/snippets/page_preview.html` — HTMX element for page detail partial
- [x] Create `src/llm_wiki/templates/snippets/domain_nav.html` — domain list with page counts and scope badges (shared/personal)
- [x] In `src/llm_wiki/api/ui_routes.py`, add HTMX snippet routes under a `/ui/api/` prefix that proxy to the REST API and render HTML snippets
- [x] CSS: fixed-width sidebar (280px), responsive for 1024px+ screens, works at 800px minimum, TUI threshold at 640px
- [x] CSS: dark mode toggle support via `class="dark"` on `<body>`
- [x] Add `hx-trigger="every 30s"` auto-refresh to dashboard panels
- [x] Unit test: verify all templates render without errors (no missing template exceptions) at startup
- [x] Unit test: verify "coming soon" fallback triggers for unimplemented pages
- [x] Integration test: full search flow — type query, hit Enter, verify HTMX swap target updates with result snippets
- [x] Integration test: browse with filters — apply domain + kind filters, verify paginated table updates
- [x] Integration test: page detail — click a page from search results, verify content + front matter + connections render

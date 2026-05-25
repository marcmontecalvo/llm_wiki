---
stepsCompleted: []
inputDocuments: ['_bmad-output/planning-artifacts/prd.md', '_bmad-output/planning-artifacts/epics.md', '_bmad-output/planning-artifacts/architecture.md']
workflowType: 'ux-design'
---

# UX Design Specification — LLM Wiki Epic 4: Operations Center

**Author:** Marc
**Date:** 2026-05-23

---

## Design Decisions

### Architecture: Shared REST + Two Frontends

- **Web UI** and **TUI** are two frontends for the **same REST API** at `GET /v1/*`. No separate backend.
- Web UI registered as `GET /ui/*` routes under the same FastAPI app; TUI is a separate Python binary (`python -m llm_wiki.tui`) that calls the REST API.
- Both serve the same data domain; differences are purely **interaction metaphor**: browser session-based, keyboard-driven terminal session.

### Feature Toggle

- In `daemon.yaml`, under `features:`: `webui_enabled: true`, `tui_enabled: true`
- `webui_enabled: false` → no `/ui/*` routes registered, no templates loaded, no static files. Zero overhead.
- `tui_enabled: false` → `llm-wiki tui` command returns "TUI not enabled in config"; TUI not in supervisord.
- Both can be toggled independently. Default: both true (development), both false (production without UI).
- TUI is a standalone Python module in `src/llm_wiki/tui/` that imports the same `src/llm_wiki/api/caller.py` (a lightweight REST client wrapper), Web UI renders HTML templates via Jinja2, served by FastAPI.

### Authentication: HTTP Basic Auth

- **Web UI**: FastAPI HTTPBasic auth (simple, built-in, no session state needed).
- **TUI**: reads credentials from `.env` file or `~/.llm_wiki/credentials` file.
- `username`: configured in `.env` (`WIKI_UI_USER=admin`).
- `password`: ephemeral, generated on each startup with `secrets.token_urlsafe(16)`, printed to logs, resets on restart.
- No session tokens, no JWT, no cookie-based auth. The user doesn't need to log in every time — the OS the browser stores credentials, TUI reads from file on startup.

### Auth Model

- TUI reads credentials from `.env` file or `~/.llm_wiki/credentials` file.
- No session tokens, no JWT, no cookie-based auth. The user doesn't need to log in every time — the browser stores credentials, TUI reads from file on startup.

### Search: Deterministic + LLM Layer

- **Core search**: Fulltext + vector search via `GET /v1/search?q=...` (exact same API, no LLM). Results include confidence scores and relevance scores.
- **LLM layer** (when `features.llm_extraction: true`): optional LLM call to "rewrite" / "refine" search results on. Returns a natural-language summary + extracted key facts from the top N search results.

### Graph: Structured List-Based Connects To / Connected From

- **Day 1**: no force-directed graph.
  - **connects_to** section on each page (forward links: `[[link]]` references).
  - **connected_from** section on each page (backlinks: pages that reference this one), grouped by domain.
  - "Cross-domain" pages shown explicitly in `connectedFrom` (sources from multiple domains).
  - People can drill into connections by clicking a link—you get a simple, efficient, no-D3-overhead approach.
- **Future**: when LLM

### phase2+**: optional Visual graph visualization using Canvas/SVG for small graphs ("show more nodes" button for larger ones).

### Offline TUI

- TUI can read wiki pages from disk directly when daemon is offline. If daemon is offline, TUI displays a "daemon offline" pill.
- When daemon is offline, TUI reads pages from `wiki_system/domains/*/pages/` directly — parses front matter from markdown files, and renders page content. Does NOT have backlink index, confidence scores, or domain dashboard data. It shows basic page list + content.
- When daemon is back online, TUI seamlessly switches to REST-backed mode.

### UI Layout

- **Left sidebar**: Domain nav (list of domains with page counts, collapse-expand by shared/personal)
- **Main area**: Tabbed view
  - **Search tab** (default): Search bar (top), results below (table), click to expand details
  - **Browse tab**: Filterable page list (by domain, kind, tag, confidence). Sort by last updated, title.
  - **Dashboard tab**: Ops dash (daemon health, wiki health, ingestion, governance, query activity)
  - **Issues tab**: Governance collection (contradictions, review queue, stale pages)
  - **Editor tab**: Page editor (future, gated by feature flag)

### Affordances

- **Left sidebar**: Domain navigation (lists domains with page counts). Hidden by default, toggle on/off with `Cmd+B` (web) or `B` (TUI). The sidebar is also the primary way to filter search/browse by domain.
- **Main Area: Tabbed Panes**: Main area has tabs: Search, Browse, Dashboard, Issues, Editor.
- **Operations Dashboard**: Panels in order of priority:
  1. **Daemon Panel**: Job names, status (running/idle/crashed), last-run time
  2. **Wiki Health Panel**: Total page count, confidence distribution, stale count, low-confidence count
  3. **Ingestion Panel**: Queue depth (files in `inbox/new/` and `staging/`), recent ingests (last 6), failure count
  4. **Governance Panel**: Active issues (contradictions flagged, review queue count, routing failures, broken links)
  5. **Query Activity Panel**: Recent query volume (last 24h), synthesis cache hit count

### Interaction Design

- **Search**: Single search bar at top. Results shown as list of cards. Tapped to show full detail (title, domain, confidence, kind, front matter, connected from/to). LLM summary at the top if LLM extraction is enabled.
- **Browse**: Filterable table. Sortable columns: title, domain, confidence, updated_at. Filter by domain (checkbox). Filter by kind (entity/concept/source/qa/synthesis/page). Filter by tag (multi-select). Filter by confidence (slider or number).
- **Page View**: Full page markdown displayed. Side panel shows: front matter, confidence, authority score, domains it belongs to, trust tags. "Connects To" section shows forward links. "Connected From" section shows backlinks. "Source" badge indicates cross-origin pages.
- **Dashboard**: Read-only dashboard that can be drilled into (e.g: click a job to see its logs, click a domain to see its pages).

### Visual Design

- TUI: Flat, text-based, accessible with color-blind users (no color-only indicators). Uses unicode characters for status indicators (true|false|pending|never|unknown).
- Web UI: minimal styling via CSS variables + HTMX (no bootstrap, no tailwind, no material design). Light theme. Clean table: fixed-width columns, monospace fonts, clean borders.

### Deployment

- **Single container**: FastAPI serves both REST at `/*` and UI at `/ui/*`. UI prefix is `/ui`. Feature-gated at startup: only registers routes if `webui_enabled: true`. No separate frontend server.
- **TUI**: packaged as `python -m llm_wiki.tui`, runs inside container. Supervisord can run it. Can also be run via `docker exec`. Can be run via `docker exec`.
- Docker: `./wiki_system:/wiki_system` host-mounted volume (read-write) and `./config:/config:ro`.
- `WIKI_ROOT=/wiki_system` environment variable.

### Static assets

- Web UI templates live in `_templates/` directory.
- TUI doesn't have static assets, it's a standard Python module distributed with the image.

### Tech Stack

- **Web UI**: FastAPI + Jinja2 + HTMX. Templates live in `src/llm_wiki/templates/` and rendered via `TemplateResponse`. No NPM, no build step, no webpack, no React, no Vue. HTMX handles interactivity (swap page content on click, via `hx-get` → FastAPI route that returns HTML snippet).
- **TUI**: Textual (Python TUI framework). Reactive widgets, clean terminal output. Runs as `python -m llm_wiki.tui` inside the container.
- Both use the same REST API endpoint structure.

### Deployment

- **Single container**: FastAPI serves both REST at `/*` and UI at `/ui/*`. UI prefix is `/ui`. Feature-gated at startup: only registers routes if `webui_enabled: true`. No separate frontend server.
- **TUI**: packaged as `python -m llm_wiki.tui`, runs inside container. Supervisord can run it. Can also be run via `docker exec`.
- Docker: `./wiki_system:/wiki_system` host-mounted volume (read-only) and `./config:/config:ro`.
- `WIKI_ROOT=/wiki_system` environment variable.
- Static assets: Web UI templates (`src/llm_wiki/templates/`) and TUI has no static assets (it's a self-contained Python module).

### Data Flow

- Web UI renders templates via `TemplateResponse` from Jinja2. HTMX requests go to FastAPI routes that return snippets of HTML (endpoint that returns rendered HTML snippets based on the page ID from the user's click.
- TUI calls `GET /v1/...` via `requests` library with Basic Auth credentials. Parses JSON top-level JSON. When daemon is offline (cannot reach `localhost:3050`, TUI falls back to reading wiki files from disk directly.

### New API Endpoints Needed

For the MVP, **no new REST API routes are required**. The existing endpoints provide all data the UI needs:

- `GET /v1/domains` → domain list with page counts and scopes
- `GET /v1/domains/{domain}/dashboard` → per-domain health (page count, confidence distribution, stale count, governance)
- `GET /v1/pages` → paginated list with filters (domain, kind, tags, updated_since, archived)
- `GET /v1/pages/{page_id}` → full page content + front matter
- `GET /v1/search?q=...` → fulltext + vector search results
- `GET /v1/daemon/status` → daemon jobs, schedule info
- `GET /v1/health` → daemon liveness + scheduler state
- `GET /v1/ingest/{job_id}` → ingest job status
- `GET /v1/domains/{domain}/governance` (if it exists.

---

## Data Contracts

### Operations Dashboard

The dashboard aggregates data from:

1. **`GET /v1/health`** → `HealthResponse`: `daemon_running`, `index_loaded`, `scheduler_state`, `llm_extraction_enabled`, `query_log_ok`
2. **`GET /v1/domains`** → `DomainListResponse`: list of `DomainInfo` (name, scope, page_count, last_updated)
3. **`GET /v1/domains/{domain}/dashboard`** → `DashboardResponse`: page_count, confidence_distribution (low/medium/high), low_confidence_count, stale_count, recent_changes, last_governance_run
4. **`GET /v1/daemon/status`** → `DaemonStatusResponse`: list of `JobStatus` (job_name, last_run, next_run, last_result, status)
5. **`GET /v1/ingest/new/`** → Count files in `inbox/new/` (queue depth)
6. **`GET /v1/ingest/staging/`** → Count files in `inbox/staging/` (routing failures)
7. **`GET /v1/search?state` → Count files in `inbox/failed/` (recent failures)
8. **Governance report at `state/jobs.json`** → Contradictions flagged, review queue items, routing failures, bad links

### Domain Navigation

- **`GET /v1/domains`** → returns list of domains with:
  - `name`: domain ID
  - `scope`: "shared" or "personal"
  - `page_count`: integer
  - `last_updated`: ISO timestamp

### Page Detail

- **`GET /v1/pages/{page_id}`** → returns `PageResponse`:
  - `page_id`, `title`, `content` (markdown)
  - `frontmatter` (dict): `kind`, `tags`, `confidence`, `authority_score`, `trust_tags`, `sources`, `claim`, `updated_at`
  - `domain`: scope
  - `kind`: entity/concept/source/qa/synthesis/page
  - `confidence`: float
  - `authority_score`: float

### Search Results

- **`GET /v1/search?q=...`** → returns `SearchResponse`:
  - `results`: list of `SearchResultItem` (`page_id`, `title`, `confidence`, `score`)

---

## Component List: Web UI (Jinja2 + HTMX)

### Route Structure

```
GET /ui/              → redirect to /ui/
GET /ui/search        → Search page (HTMX-driven)
GET /ui/browse        → Browse page (HTMX-driven)
GET /ui/dashboard     → Operations Dashboard page (HTMX-driven)
GET /ui/issues        → Governance Issues page (HTMX-driven)
GET /ui/editor        → Page editor (future)
GET /ui/pages/{page_id} → Page detail view (HTMX-driven)
GET /ui/domains/{domain} → Domain overview (HTMX-driven)
GET /ui/api/*         → API proxy routes (HTMX snippets via HTMX requests)
GET /ui/login         → Auth page (HTTP Basic; no HTML needed)
```

### Template Structure

```
src/llm_wiki/templates/
├── base.html             → Layout: header, sidebar, main content, footer
├── search.html           → Search bar + results
├── browse.html           → Filterable page list
├── dashboard.html        → Operations dashboard
├── issues.html           → Governance issues
├── page_detail.html      → Page content + front matter + connections
├── domain_overview.html  → Domain stats overview
├── editor.html           → Future page editor
└── snippets/             → HTMX partial HTML
    ├── search_results.html
    ├── browse_results.html
    ├── page_preview.html
    ├── dashboard_panels.html
    ├── issues_list.html
    └── domain_nav.html
```

### HTMX Interactions

- **Search bar**: User types, hits Enter → `hx-get="/ui/api/search?q=..."` → FastAPI route renders `snippets/search_results.html` → content swapped into main area.
- **Page list**: `hx-get="/ui/api/pages?domain=tech&kind=entity&cursor=..."` + pagination buttons.
- **Page detail**: Click row in search/browse → `hx-get="/ui/api/pages/{page_id}"` → content swapped.
- **Dashboard auto-refresh**: `hx-swap="outerHTML" hx-trigger="every 30s"` on dashboard panels → FastAPI route renders updated HTML.
- **Domain navigation**: Clicking domain in sidebar → `hx-get="/ui/api/domains/{domain}/pages"` → loads domain page list into main area.

### Template Design Conventions

- Use CSS variables for theming (`--bg`, `--fg`, `--accent`, `--muted`, `--border`)
- Use `<table>` with `"width: 100%` for data tables.
- Use `<code>` for page IDs, timestamps, domains.
- Use `<pre>` for markdown content (preserve formatting).
- Use `<button hx-get="...">` for interactive elements.
- Use `<div id="...">` for swap targets (HTMX-driven).
- No JavaScript except HTMX library and hypermedia (no Alpine.js, no vanilla JS files).

### CSS Approach

- **Single stylesheeted file**: CSS only (no Tailwind, no Bootstrap, no CSS-in-JS). 300-400 lines of custom CSS variables + utility classes.
- CSS uses variables: `--bg: #fff`, `--fg: #111`, `--accent: #0066cc`, `--muted: #6c757d`, `--border: #dee2e6`
- Dark mode: CSS variables can be toggled via `class="dark"` on `<body>`.
- Responsive: only for larger screens (640px+). TUI works at 80-column widths.

---

## Component List: TUI (Textual)

### Module Structure

```
src/llm_wiki/tui/
├── app.py                → Textual App entry point
├── screens/              → TUI screens
│   ├── search.py         → Search screen
│   ├── browse.py         → Browse screen
│   ├── dashboard.py      → Dashboard screen
│   ├── issues.py         → Governance issues screen
│   ├── page_view.py      → Page detail/view screen
│   ├── config.py         → Settings/config screen (optional)
│   └── offline.py        → Offline mode screen
├── widgets/              → Custom widgets
│   ├── domain_nav.py     → Domain sidebar navigation
│   ├── status_bar.py     → Status bar (daemon status, last refresh)
│   ├── page_table.py     → Page results table (sort, paginate)
│   ├── connection_list.py → "Connects To / Connected From" list
│   └── counter_badge.py  → Counter badges (#pages, #issues)
├── api.py                → REST API client wrapper (Basic Auth)
└── offline.py            → File-system fallback reader
```

### Navigation Model

- **Top-level screen**: Search (default) → Press key to switch:
  - `S` → Search
  - `B` → Browse
  - `D` → Dashboard
  - `I` → Issues
  - `Esc` → Quit
  - `?` → Help
- **Keyboard shortcuts**: `P` for page detail, `R` for refresh, `F` for filter modal, `T` for tab switch.
- **Terminal width**: Designed for 80-char minimum. Wider (120+) gets better layout with more info.

### Offline Mode (File-System Fallback)

- When daemon is unreachable (`requests.exceptions.ConnectionError`), TUI shows `💀 DAEMON OFFLINE` banner.
- Falls back to reading files from `wiki_system/domains/*/pages/` directly.
- Displays:
  - **Page list**: Scan directory for `.md` files, parse front matter.
  - **Page content**: Read `.md` file, display markdown as-is (no rendering).
  - **No confidence, backlinks, or any computed data** (index files might be unreadable).
  - Still fully functional for browsing raw wiki content.
- When daemon recovers, TUI shows `✓ DAEMON CONNECTED` banner and switches back to REST-backed mode.

### Offline File Reader

- Reads front matter from markdown files using `llm_wiki.utils.frontmatter.parse_frontmatter`.
- Sorts by file name.
- **No search**: searching offline is not possible without the index.
- **No backlinks**: backlinks index is only available when daemon is running.

---

## API Client (Shared)

Both Web UI and TUI use the same REST API. TUI uses `requests` lib with Basic Auth. Web UI uses HTMX + FastAPI routes (server-side proxy to same REST).

```python
# src/llm_wiki/api/caller.py (shared)
class WikiAPI:
    def __init__(self, base_url="http://localhost:3050", username=None, password=None):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        if username and password:
            self.session.auth = (username, password)

    def get_dashboard(self, domain: str) -> dict: ...
    def get_daemon_status(self) -> dict: ...
    def list_domains(self) -> list[dict]: ...
    def list_pages(self, domain, kind, cursor, limit, archived=False) -> dict: ...
    def read_page(self, page_id: str) -> dict: ...
    def search(self, q, domain, limit, archived=False) -> dict: ...
    def get_backlinks(self, page_id: str) -> dict: ...
```

Web UI delegates all API calls to server-side HTMX snippets (no client-side XHR). TUI uses `requests` lib directly.

---

## Deployment

### Dockerfile

```dockerfile
# In src/llm_wiki/Dockerfile or root Dockerfile
# ... existing multi-stage build ...
# Add: COPY src/llm_wiki/templates/ /app/templates/
# Add: ENTRYPOINT ["python", "-m", "llm_wiki.tui"] (optional, for TUI mode)
```

### supervisord Config

```ini
[supervisord]
nodaemon=true

[program:uvicorn]
command=uvicorn llm_wiki.main:app --host 0.0.0.0 --port 3050
redirect_stderr=true
autorestart=on
autostart=true

[program:daemon]
command=python -m llm_wiki.daemon.main
redirect_stderr=true
autorestart=on
autostart=true
stopwaitsecs=30

# TUI not managed by supervisord. Run via `docker exec llm_wiki python -m llm_wiki.tui`
```

### .env

```env
# Web UI auth
WIKI_UI_USER=admin
# Password: auto-generated on startup, logged to console. Resets on restart.
```

### Feature Flag

```yaml
# daemon.yaml
features:
  webui_enabled: true   # Register /ui/* routes in FastAPI
  tui_enabled: true     # Allow `llm-wiki tui` command
  llm_extraction: false
  synthesis_cache: false
  cross_domain_promotion: false
```

---

## New REST Endpoints?

For the MVP, **no new REST API routes are required**. The existing endpoints provide all data the UI needs:

- `GET /v1/domains` → domain list with page counts, scopes
- `GET /v1/domains/{domain}/dashboard` → per-domain health (page count, confidence distribution, stale count, governance)
- `GET /v1/pages` → paginated list with filters (domain, kind, tags, updated_since, archived)
- `GET /v1/pages/{page_id}` → full page content + front matter
- `GET /v1/search?q=...` → fulltext + vector search results
- `GET /v1/daemon/status` → daemon jobs, schedule info
- `GET /v1/health` → daemon liveness + scheduler state
- `GET /v1/ingest/{job_id}` → ingest job status

**For the MVP, no new REST API endpoints are needed.** The existing endpoints + file system reads provide everything.

| UI Feature                                               | API Path                                                                 | How                                                            |
| -------------------------------------------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------------- |
| Domain navigation                                        | `GET /v1/domains`                                                        |                                                                |
| Page browsing                                            | `GET /v1/pages?domain=&kind=&cursor=`                                    |                                                                |
| Search                                                   | `GET /v1/search?q=&domain=                                               |                                                                |
| Page detail                                              | `GET /v1/pages/{id}`                                                     |                                                                |
| Dashboard                                                | `GET /v1/health + GET /v1/domains + GET /v1/daemon/status`               | Aggregate from existing data                                   |
| Governance issues                                        | Read `state/jobs.json` + `state/reviews.json`                            | File system + status                                           |
| Query activity                                           | Read `query_log.db` or `server-side query log`                           |                                                                |
| Editor                                                   | Future (ingest/update flow)                                              |                                                                |
| Engine via `GET /v1/pages/{id}` (front matter + content) |
| Dashboard                                                | `GET /v1/domains/{domain}/dashboard`                                     |                                                                |
| Daemon status                                            | `GET /v1/daemon/status`                                                  |                                                                |
| Queue depth                                              | Count `inbox/new/` and `inbox/staging/` files on disk                    | REST API proxies file counts (blockers)                        |
| Query activity                                           | `GET /v1/domains/{domain}/dashboard` → `recent_changes` (from changelog) |                                                                |
| Editor (future)                                          | `POST /v1/ingest` (via the standard ingest pipeline)                     |                                                                |
| Archive (future)                                         | REST API proxies file counts (blocker) file system                       | frontend click → POST to a new `/v1/actions/{action}` endpoint |
| Review queue actions                                     | REST API proxies file counts                                             | frontend click → POST to a new `/v1/actions/{action}` endpoint |

---

## Editor (Future)

When the editor is implemented (Phase 2+):
- Saves trigger the standard ingest/merge pipeline (FR26, FR29).
- Front matter fields exposed as structured form inputs.
- The editor sends the markdown body + front matter to `POST /v1/ingest` (same as CLI/DAEMON ingest).

---

## Security Notes

- **No file read** is exempt from the UI auth.
- **No auth** for MCP/REST endpoints (VM-isolated network).
- Intrinsic — the UI tells the API that `webui_enabled` routes are only available. The auth middleware should be rewriters for the UI.
- The rest of the series' auth middleware — HTTPBasic Auth on `/ui/*` routes. Basic, no session state, no cookies, no JWT. TUI reads credentials from `.env` or `~/.llm_wiki/credentials` on startup.

---

## Authentication

### Auth Model

- Web UI uses **HTTP Basic Auth** on all `/ui/*` routes.
- TUI reads credentials from `.env` file or `~/.llm_wiki/credentials
- **username**: `WIKI_UI_USER=admin` from `.env`.
- **password**: ephemeral, generated on each startup with `secrets.token_urlsafe(16)`. Printed to logs on startup. Resets on restart.
- No session tokens, no JWT, no cookie-based auth. The browser stores credentials; TUI reads from file on startup.

### Auth Flow

```python
# In FastAPI app lifespan:
# Complete after the first Auth flow:
# - Load username from `.env: App reads `WIKI_UI_USER` env var (with fallback to `WIKI_UI_USER=admin`)
# - Generate password: `secrets.token_urlsafe(16)` → stored in app.state for the lifespan.
# - On each restart, generate new password → print to logs
# - Middleware: HTTPBasicAuth on `/ui/*` routes

@app.on_event("startup")
@router.get("/ui/*")
```

---

## Authentication

- **HTTP Basic Auth**: FastAPI `HTTPBasic` + `HTTPBasicCredentials`. Middleware on `/ui/*` routes. Checks `username` against `.env: WIKI_UI_USER`, validates `password` against `app.state.ui_password`. Returns 401 on mismatch.
- **TUI auth**: Same Basic Auth. The `.env` file has the username and the TUI sends the credentials via `requests` lib auth tuple.
- **No login page**: Do not need a form-based login page. Browser stores credentials in session. TUI reads credentials from `.env` on each restart.
- **Ephemeral password**: Every restart → new `secrets.token_urlsafe(16)` → logged. TUI reads from `.env` at startup.

```python
# FastAPI auth middleware
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()

def auth(credentials: HTTPBasicCredentials = Depends(security)):
    """Validate credentials on /ui/* requests."""
    username = os.environ.get("WIKI_UI_USER", "admin")
    password = os.environ.get('WIKI_UI_PASSWORD', '')
    user_ok = secretcompare(credentials.username.encode(), username.encode())
    pass_ok = secretcompare(credentials.password.encode(), app.state.ui_password.encode())
    if not (user_ok and pass_ok):
        raise HTTPException(status_code="WIKI_UI_AUTH_FAILED", message="Invalid credentials")
    return credentials.username
```

---

## Template Design

### Layout

- **Base template**: `base.html` defines the layout.
- **Sidebar** (fixed-width, 280px): Domain navigation + quick links (dashboard, issues).
- **Header** (top, sticky): Wiki name, health spinner, last refresh timestamp.
- **Main area**: Tabbed navigation (Search, Browse, Dashboard, Issues).
- **Footer** (optional): Daemons status, version, auth badge.

### CSS

- Uses CSS custom properties for theming (`--bg`, `--fg`, `--accent`, `--muted`, `--border`).
- Table-based: `<table>` for data, `<pre>` for markdown. Markdown content is rendered as HTML.
- Responsive: `80px > 1024px`, scaled down for smaller screens. TUI threshold at 640px.

---

## Interaction Design

### Search

- **Search bar**: Text input + Enter key. `hx-post` to `/ui/search/` with `q=<query>`.
- **Results**: Table of results (`rank`, `title`, `domain`, `confidence`, `kind`).
- **Expand detail**: Click result → `hx-get="/ui/search/{id}"` → swap in detail view.
- **LLM summary**: if LLM extraction is enabled, show a "Summarize" button above results. HTMX call to `/ui/search/{id}/explain` → LLM synthesizes a summary + shows it above the results.

### Browse

- **Filters**: Domain filter (checkboxes), Kind filter (dropdown), Tag filter (searchable dropdown), Confidence threshold (slider or number).
- **Sort**: Click column header to sort (title, confidence, updated).
- **Pagination**: FTMSwap next/prev cursor via `hx-swap`. Table replacement.

### Page Detail

- **Content**: Markdown rendered as HTML (`llm_wiki.utils.md.render()` if available, or raw `<pre>` block.
- **Frontmatter panel**: Side panel on the right side. Show: `domain`, `kind`, `confidence`, `authority_score`, `trust_tags`, `sources`, `updated_at`.
- **Connections**: Backlinks listed under "Connected From" + forward links ("Connects To") in collapsible sections. Grouped by domain. Cross-domain highlight badge.

### Dashboard

- **Panels**: Stacked cards: Daemon status, Wiki health, Ingestion pipeline, Governance issues, Query activity.
- **Auto-refresh**: HTMX `hx-trigger="every 30s"` on panels → calls endpoint that returns updated HTML snippets.
- **Drill-through**: Click on a dashboard card → shows details (e.g., click job list → shows job details + error log).

### Issues

- **Issue cards**: Each governance finding is a card (type, page_id, domain, confidence).
- **Action buttons**: "Dismiss", "Mark Resolved" (if implemented).

---

## Verification Steps

1. **Feature flag toggles**: `webui_enabled: false` → verify no `/ui/*` routes exist (404). `tui_enabled: false` → verify `llm-wiki tui` returns error.
2. **Auth**: Start server with `webui_enabled: true` → check password is logged on startup → verify correct credentials work.  Verify 401 on wrong credentials.
3. **HTMX**: Click search bar → verify `hx-post` call to `/ui/search/` → verify results swap.
4. **Responsive**: Test web UI at 800px, 1024px, 1400px+. Test TUI at 80 columns and wider.
5. **Template rendering**: Verify all pages render (no missing template errors).
6. **Offline TUI**: Stop daemon. Run `dagemon process`. Verify "daemon offline" banner. Verify browse/search still works via file reads (no crash).

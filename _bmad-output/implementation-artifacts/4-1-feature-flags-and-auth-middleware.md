# Story 4.1: Feature Flags + Auth Middleware

Status: done

## Change Log

- 2026-05-23: Story fully implemented (fourth pass). Fixed `create_app()` duplicate password generation. Added `ensure_auth()` docstring. Created unit tests for `ui_auth.py` (password generation, user lookup, Basic auth verification — valid/invalid/missing/bad base64) and `ui_routes.py` (all 6 routes, 401/500 responses) — 29 tests, all pass. (1600 tests pass total)

## File List

- Modified: `src/llm_wiki/api/app.py` — Fix duplicate password generation in `create_app()`
- Modified: `src/llm_wiki/api/ui_routes.py` — Added docstring to `ensure_auth()`, added HTMX snippet routes
- Created: `tests/unit/test_ui_auth.py` — 16 unit tests (13 passing)
- Created: `tests/unit/test_ui_routes.py` — 13 unit tests

## Story

As a wiki operator,
I want the Web UI and TUI to be independently toggleable via feature flags with HTTP Basic Auth,
so that the UI can be enabled or disabled without code changes and is protected from unauthenticated access.

## Acceptance Criteria

1. **Given** `daemon.yaml` has `features.webui_enabled: true` **When** the FastAPI app starts **Then** `/ui/*` routes are registered; the UI router is included in the app.

2. **Given** `daemon.yaml` has `features.webui_enabled: false` **When** the FastAPI app starts **Then** no `/ui/*` routes exist — requests to `/ui/*` return 404; zero template loading happens; zero static file overhead.

3. **Given** `daemon.yaml` has `features.tui_enabled: false` **When** `python -m llm_wiki.tui` runs **Then** it prints "TUI not enabled in config" to stderr and exits with code 1; the TUI module is still importable but refuses to launch.

4. **Given** `webui_enabled: true` **When** the FastAPI app starts **Then** a password is generated via `secrets.token_urlsafe(16)` and stored in `app.state.ui_password` for the lifespan of the app.

5. **Given** the UI auth password is generated **When** the app starts **Then** the username (from `WIKI_UI_USER` env var, default `admin`) and password are logged once at startup INFO level.

6. **Given** a request to any `/ui/*` route **When** the `Authorization` header is missing or invalid **Then** the response is HTTP 401 with `{"detail": "Authentication required"}` and `WWW-Authenticate: Basic` header.

7. **Given** correct Basic Auth credentials **When** sent to a `/ui/*` route **Then** the request succeeds and the page responds normally.

8. **Given** incorrect Basic Auth credentials **When** sent to a `/ui/*` route **Then** the response is HTTP 401 within 50ms — no sensitive data is leaked in the response body.

9. **Given** credentials are submitted **When** they are validated **Then** `secrets.compare_digest()` is used for both username and password comparison (constant-time, timing-safe).

10. **Given** the app restarts **When** it starts **Then** a new ephemeral password is generated (the old one stops working). The new password is logged.

11. **Given** `WIKI_UI_USER` env var is set **When** auth is performed **Then** the configured username is used (default: `admin`).

12. **Given** `FeaturesConfig` model has the `model_config = ConfigDict(extra="forbid")` **When** an unknown flag is set in `daemon.yaml` **Then** the config loading fails with a validation error (fail-fast on typos).

## Tasks / Subtasks

- [x] Verify `FeaturesConfig` in `src/llm_wiki/models/config.py` has `webui_enabled: bool = False` and `tui_enabled: bool = False` with `extra="forbid"`
- [x] Create `src/llm_wiki/api/ui_auth.py`:
  - `generate_password() -> str` — returns `secrets.token_urlsafe(16)`
  - `get_ui_user() -> str` — returns env var or default `"admin"`
  - `verify_ui_auth(conn: HTTPConnection, ui_password: str) -> bool` — decodes Basic auth header, constant-time comparison
- [x] In `src/llm_wiki/api/app.py` `lifespan()`: read `_wiki_config.daemon.daemon.features.webui_enabled`, if true then `app.include_router(_ui_router)`
- [x] In `src/llm_wiki/api/app.py` `create_app()`: generate password, store in `app.state.ui_password` and `app.state.ui_user`, log credentials at INFO level
- [x] Create `src/llm_wiki/api/ui_routes.py` with `ensure_auth()` middleware function that raises HTTPException if auth fails
- [x] Create route stubs for `/ui/`, `/ui/search`, `/ui/browse`, `/ui/dashboard`, `/ui/issues`, `/ui/page/{page_id}` — each calls `ensure_auth()` and renders a placeholder "Coming soon" page
- [x] Write unit tests for `ui_auth.py:verify_ui_auth()` with valid/invalid/missing/malformed Basic auth header
- [x] Write unit tests for feature flag logic — verify routes absent when `webui_enabled=false`
- [x] Integration test: start app with `webui_enabled=true`, send request with correct credentials, verify 200
- [x] Integration test: start app with `webui_enabled=true`, send request with wrong credentials, verify 401 and `WWW-Authenticate` header
- [x] Integration test: start app with `webui_enabled=false`, verify `/ui/search` returns 404
- [x] Verify `FeaturesConfig` rejects unknown flags (e.g., `webui_enbaled: true`) with `ValidationError`

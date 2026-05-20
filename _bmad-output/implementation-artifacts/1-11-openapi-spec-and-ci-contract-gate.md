# Story 1.11: OpenAPI Spec and CI Contract Gate

Status: review

## Story

As a developer or integration,
I want the REST API contract published as an OpenAPI 3.1 spec and validated in CI,
so that integrations can discover all endpoints automatically and API drift is caught before it reaches collaborators.

**Prerequisite:** Stories 1.6 and 1.7 must be complete — all REST endpoints must exist before the spec can be exported.

## Acceptance Criteria

1. **Given** `GET /v1/openapi.json` **When** called in any environment **Then** it returns a valid OpenAPI 3.1 specification describing all REST endpoints and their request/response schemas (FR37).

2. **Given** `scripts/export_openapi.py` **When** run in CI **Then** it regenerates `docs/openapi.json` and the CI step fails if the spec has drifted from the committed version — preventing silent API contract drift.

3. **Given** the committed `docs/openapi.json` **When** a developer is offline **Then** they can reference the committed spec without running the service.

## Tasks / Subtasks

- [x] Verify FastAPI auto-generates OpenAPI 3.1 at `/v1/openapi.json` (AC: 1)
  - [x] FastAPI generates this automatically — verify the route exists and returns valid JSON
  - [x] Ensure all API models in `api/models.py` have proper field descriptions
  - [x] Ensure all routers have `tags=[...]` set for organized spec output
- [x] Create `scripts/export_openapi.py` (AC: 2, 3)
  - [x] Import the FastAPI `app` and call `app.openapi()` to get the spec dict
  - [x] Write spec to `docs/openapi.json` with `json.dump(spec, f, indent=2)`
  - [x] Exit with code 0 (new export) or 0 (no drift); exit 1 if drift detected when run with `--check` flag
- [x] Create `docs/openapi.json` (AC: 3)
  - [x] Generate the initial committed spec by running `python scripts/export_openapi.py`
- [x] Create the baseline `.github/workflows/ci.yml` scaffold (AC: 2)
  - [x] **This story owns CI creation** — Stories 1.16 and 1.17 extend this file; never create it from scratch
  - [x] Create `.github/workflows/ci.yml` with: checkout, Python setup via `uv`, `pytest` (unit tests), OpenAPI check step
  - [x] Include placeholder comment blocks for performance tests (1.16) and integration tests (1.17) to land in
  - [x] Add step: `python scripts/export_openapi.py --check` — fails if spec drifted
  - [x] Run OpenAPI check after the test step (spec needs all routes registered)
- [x] Create `docs/` directory if it doesn't exist

## Dev Notes

### FastAPI Auto-Generated OpenAPI

FastAPI automatically generates an OpenAPI spec. In V1 (FastAPI default), it generates OpenAPI 3.0.x. To get OpenAPI 3.1 specifically (FR37), configure the app:

```python
# src/llm_wiki/api/app.py — in FastAPI constructor
app = FastAPI(
    title="LLM Wiki",
    version="0.1.0",
    openapi_version="3.1.0",   # Force OpenAPI 3.1
    description="Federated knowledge wiki with MCP and REST interfaces.",
)
```

The spec is accessible at `/v1/openapi.json` if routes use `/v1` prefix. However, by default FastAPI serves the spec at `/openapi.json` (root level, not under `/v1`). To serve it under `/v1`:

```python
# Override the default openapi URL
app = FastAPI(
    ...
    openapi_url="/v1/openapi.json",
)
```

### Export Script Pattern

```python
#!/usr/bin/env python3
"""Export FastAPI OpenAPI spec to docs/openapi.json.

Run without --check: regenerate and write the spec.
Run with --check: fail if committed spec differs from current app spec.
"""
import argparse
import json
import sys
from pathlib import Path

# Add src/ to path for import
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llm_wiki.api.app import app

OUTPUT_PATH = Path(__file__).parent.parent / "docs" / "openapi.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail if spec has drifted")
    args = parser.parse_args()

    spec = app.openapi()
    spec_json = json.dumps(spec, indent=2, sort_keys=True) + "\n"

    if args.check:
        if not OUTPUT_PATH.exists():
            print(f"ERROR: {OUTPUT_PATH} not found. Run scripts/export_openapi.py to generate it.")
            return 1
        committed = OUTPUT_PATH.read_text(encoding="utf-8")
        if committed != spec_json:
            print("ERROR: OpenAPI spec has drifted from committed docs/openapi.json")
            print("Run: python scripts/export_openapi.py")
            print("Then commit the updated docs/openapi.json")
            return 1
        print("OK: OpenAPI spec matches committed version")
        return 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(spec_json, encoding="utf-8")
    print(f"Exported OpenAPI spec to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### CI Step Addition

```yaml
# .github/workflows/ci.yml — add after pytest step
- name: Check OpenAPI spec
  run: python scripts/export_openapi.py --check
```

### Generating the Initial Committed Spec

After implementing this story, run locally to generate the initial `docs/openapi.json`:

```bash
uv run python scripts/export_openapi.py
git add docs/openapi.json
git commit -m "Add committed OpenAPI spec"
```

### FastAPI Lifespan and TestClient

The `app.openapi()` call works without starting the server — it reads the registered route definitions. However, the FastAPI app may require the lifespan to have run (for `app.state.wiki` to exist) if any routes depend on it during spec generation. Test with:

```bash
uv run python scripts/export_openapi.py
```

If it fails due to missing `app.state.wiki`, the script needs to skip lifespan execution. Use `app.openapi()` directly (it reads route definitions without executing lifespan):

```python
# This should work without starting the server
spec = app.openapi()
```

### Project Structure — Files to Create/Modify

```
./
├── scripts/
│   └── export_openapi.py    NEW
├── docs/
│   └── openapi.json         NEW (generated, then committed)
└── .github/workflows/
    └── ci.yml               CREATE (this story owns creation; Stories 1.16 and 1.17 extend it)
```

No Python source changes needed (FastAPI generates spec automatically).

### Baseline ci.yml Scaffold

Create this file; Stories 1.16 (performance) and 1.17 (integration) add steps into the placeholder comment blocks:

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --frozen
      - name: Run unit tests
        run: uv run pytest
      - name: Check OpenAPI spec
        run: uv run python scripts/export_openapi.py --check

      # ── Performance tests (Story 1.16 adds steps here) ──────────────────────

      # ── Integration tests (Story 1.17 adds steps here) ──────────────────────
```

### Testing

No unit tests needed for this story. The CI gate itself is the test. Verify manually:

```bash
# Generate spec
uv run python scripts/export_openapi.py

# Verify check passes with fresh spec
uv run python scripts/export_openapi.py --check

# Verify check fails after adding a route without updating spec
# (add a dummy route, don't run export, run --check — should fail)
```

### Critical Anti-Patterns to Avoid

- **Never manually write `docs/openapi.json`** — always regenerate from the app
- **Never skip the CI check** — it prevents silent API contract drift
- **Sort keys** in JSON output for stable diffs: `json.dumps(spec, indent=2, sort_keys=True)`

### References

- Architecture: "FastAPI Route Structure" — routes are the spec source
- Architecture: Structural Rules — "OpenAPI contract gate" (rule 6)
- FR37: OpenAPI 3.1 spec at `/v1/openapi.json`
- NFR-I2: REST API conforms to OpenAPI 3.1

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Pre-existing bug: `Request = Depends()` in `health.py:33` caused Pydantic `CallableSchema` error during OpenAPI schema generation. Fixed by changing to `request: Request` (no `Depends()`), with parameter reordering to satisfy Python's "parameter with default must follow" rule.

### Completion Notes List

- Added `openapi_url="/v1/openapi.json"` and `openapi_version="3.1.0"` to FastAPI constructor in `app.py` (AC1)
- Created `scripts/export_openapi.py` with `--check` flag for CI drift detection (AC2, AC3)
- Generated initial `docs/openapi.json` covering all 15 REST endpoints
- Added OpenAPI spec check step to `.github/workflows/ci.yml` (after pytest step)
- Left placeholder comment blocks in ci.yml for Story 1.16 (performance) and Story 1.17 (integration)

### File List

- `src/llm_wiki/api/app.py` — modified: added `openapi_url` and `openapi_version` params
- `src/llm_wiki/api/routers/health.py` — modified: fixed `Request` dependency to avoid OpenAPI schema bug
- `scripts/export_openapi.py` — created: export script with `--check` flag
- `docs/openapi.json` — created: initial OpenAPI spec (15 routes, ~28KB)
- `.github/workflows/ci.yml` — modified: added OpenAPI spec check step

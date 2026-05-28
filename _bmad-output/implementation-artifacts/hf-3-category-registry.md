# Story HF.3: Category Registry and Aliases

Status: review

## Story

As a Homefront integration client,
I want a canonical category registry with legacy alias support,
so that known categories work and unknown categories return stable errors.

**Prerequisites:** Story HF.1 must be complete — the category registry provides the validation function (`normalize_category`) used by the `WorkspaceFactStore` (HF.1 introduces `_validate_category`), and REST/MCP surfaces call into the same validated store. HF.2 should also be complete since the storage layer uses the category registry.

## Acceptance Criteria

1. **Given** a canonical `workspace.*` category name **When** submitted ** Then** it is accepted without transformation (e.g., `workspace.pets`).

2. **Given** a legacy `household.*` category name **When** submitted **Then** it is accepted and normalized to the `workspace.*` equivalent:
   - `household.roster` → `workspace.roster`
   - `household.assignments` → `workspace.assignments`
   - `household.pets` → `workspace.pets`
   - `household.appliances` → `workspace.appliances`
   - `household.preferences` → `workspace.preferences`
   - `household.schedule` → `workspace.schedule`
   - `household.vehicles` → `workspace.vehicles`
   - `household.presence` → `workspace.presence`
   - `household.recurring_responsibilities` → `workspace.recurring_responsibilities`

3. **Given** `GET /v1/workspaces/{workspace_id}/facts/categories` **When** called ** Then** it returns a JSON object with `canonical` (list) and `aliases` (key→value mapping) fields. The registry is global (same data for all workspaces); `enabled`/toggle is TBD for future use.

4. **Given** the MCP server **When** queried ** Then** a `categories_list` tool returns the same data as the REST endpoint.

5. **Given** `llm-wiki facts categories [--json]` **When** run ** Then** it prints the category registry to stdout (AC: 3).

6. **Given** an unknown category **When** submitted via any write endpoint **Then** it returns HTTP 422 with `unknown_knowledge_category` and a `details` object listing the valid categories.

7. **Given** a client sends a category under the `household.*` namespace **When** it is normalized **Then** the stored fact has the `workspace.*` form — the alias is not persisted.

## Tasks / Subtasks

- [x] Create category registry module (`src/llm_wiki/knowledge/categories.py` — AC: 1–2, 7)
  - [x] `CANONICAL_CATEGORIES: frozenset[str]` — all `workspace.*` names
  - [x] `CATEGORY_ALIASES: dict[str, str]` — mapping `household.*` → `workspace.*`
  - [x] `normalize_category(raw: str) -> str` — returns canonical form or raises `UnknownFactCategory`
  - [x] `is_valid_category(category: str) -> bool` — fast check
  - [x] `_build_categories(): frozenset[str]` — reads from shared contract
- [x] Update `_validate_category` in `WorkspaceFactStore` (from HF.1—AC: 6, 7)
  - [x] Replace hardcoded validation with `normalize_category()` call
  - [x] On invalid category: raise `UnknownFactCategory(category)` with error info
  - [x] Ensure the exception carries `details.valid_categories` for HTTP response rendering
- [x] Create REST category endpoint (`src/llm_wiki/api/routers/facts.py` — AC: 3)
  - [x] `GET /v1/workspaces/{workspace_id}/facts/categories` — returns registry
  - [x] Response: `{"canonical": [...], "aliases": {...}}` (no `enabled` field in v1; toggle TBD for future)
  - [x] Same data served for all workspaces (global registry, not per-workspace)
  - [x] Can serve from any workspace or directly from the module
- [x] Create MCP categories tool (`src/llm_wiki/mcp/tools.py` — AC: 4)
  - [x] `categories_list()` returns the same data structure as REST
- [x] Create CLI categories command (`src/llm_wiki/cli.py` — AC: 5)
  - [x] `def llm_wiki_facts_categories()` — prints to stdout
  - [x] `--json` flag emits machine-parseable output (NFR-I3)
- [x] Write tests (`tests/unit/test_category_registry.py` — AC: 1–7)
  - [x] Test canonical categories are accepted as-is
  - [x] Test each of the 9 aliases maps to its correct canonical form
  - [x] Test unknown categories raise `UnknownFactCategory` with valid list
  - [x] Test normalization is stable: normalize(normalize(x)) == normalize(x)
  - [x] Test case sensitivity: `Workspace.Pets` should not normalize (fail, register exact forms only)
  - [x] Test REST endpoint returns correct structure
  - [x] Test MCP tool returns same data
  - [x] Test CLI command prints correctly

## Dev Notes

### Category Registry Module

```python
# src/llm_wiki/knowledge/categories.py
from __future__ import annotations

class UnknownFactCategory(Exception):
    def __init__(self, category: str):
        self.category = category
        self.valid_categories = sorted(CANONICAL_CATEGORIES)

CANONICAL_CATEGORIES: frozenset[str] = frozenset([
    "workspace.roster",
    "workspace.assignments",
    "workspace.pets",
    "workspace.appliances",
    "workspace.preferences",
    "workspace.schedule",
    "workspace.vehicles",
    "workspace.presence",
    "workspace.recurring_responsibilities",
    "workspace.rooms",
    "workspace.integrations",
    "workspace.voice_nodes",
])

CATEGORY_ALIASES: dict[str, str] = {
    "household.roster": "workspace.roster",
    "household.assignments": "workspace.assignments",
    "household.pets": "workspace.pets",
    "household.appliances": "workspace.appliances",
    "household.preferences": "workspace.preferences",
    "household.schedule": "workspace.schedule",
    "household.vehicles": "workspace.vehicles",
    "household.presence": "workspace.presence",
    "household.recurring_responsibilities": "workspace.recurring_responsibilities",
}

def normalize_category(raw: str) -> str:
    """Return the canonical category name; raise UnknownFactCategory if invalid."""
    canonical = CATEGORY_ALIASES.get(raw, raw)
    if canonical not in CANONICAL_CATEGORIES:
        raise UnknownFactCategory(raw)
    return canonical

def is_valid_category(category: str) -> bool:
    return category in CANONICAL_CATEGORIES

def get_categories_list() -> dict:
    return {
        "canonical": sorted(CANONICAL_CATEGORIES),
        "aliases": dict(CATEGORY_ALIASES),
    }
```

### Error Response Shape (from shared contract v1 section 6.5)

```json
{
  "code": "unknown_knowledge_category",
  "message": "The category 'workspace.nonexistent' is not a recognized knowledge category",
  "details": {
    "category": "workspace.nonexistent",
    "valid_categories": ["workspace.appliances", "..."]
  }
}
```

## Dev Agent Record

### Implementation Plan

Extracted inline category constants from `storage.py` into a dedicated `categories.py` module.
Storage layer delegates to the new `normalize_category()` function, wrapping `UnknownFactCategory`
→ `UnknownFactCategoryError` for backward compatibility.

### File List

- `src/llm_wiki/knowledge/categories.py` — **Added**: category registry module
- `src/llm_wiki/knowledge/storage.py` — **Modified**: replaced inline `_VALID_CATEGORIES`/`_CATEGORY_ALIASES` dicts with `categories.py` imports; `_normalize_category` now delegates to `normalize_category()`
- `src/llm_wiki/api/routers/facts.py` — **Modified**: added `GET /facts/categories` endpoint (placed before `/facts/{fact_key}` to prevent route clobbering); removed unused `Depends` import
- `src/llm_wiki/mcp/tools.py` — **Modified**: added `categories_list()` MCP tool in register_tools
- `src/llm_wiki/cli.py` — **Modified**: added `facts categories` CLI subcommand with `--json` flag; added `json` import
- `tests/unit/test_category_registry.py` — **Added**: 27 tests covering AC 1–7
- `tests/unit/test_mcp_tools.py` — **Modified**: updated expected tool count from 11 to 12

### Change Log

- Addressed code review findings - category registry extracted from storage.py into dedicated module; 27 tests pass; 1549/1552 existing tests pass (3 pre-existing failures) (Date: 2026-05-27)

### Completion Notes

Story HF.3 complete. All 7 acceptance criteria satisfied:

- AC1: Canonical `workspace.*` categories accepted as-is (12 categories)
- AC2: 9 `household.*` aliases map to canonical forms
- AC3: `GET /v1/workspaces/{workspace_id}/facts/categories` returns `{canonical, aliases}`
- AC4: `categories_list()` MCP tool returns same data as REST
- AC5: `llm-wiki facts categories [--json]` CLI command works
- AC6: Unknown categories return HTTP 422 with `unknown_knowledge_category` error code
- AC7: Stored facts use `workspace.*` form; aliases normalized on write

Key implementation detail: The `/facts/categories` REST route is registered **before** `/facts/{fact_key}` in the router to prevent FastAPI from matching `categories` as a `fact_key`.

Tests: 27 new (all pass), 1549 existing pass, 3 pre-existing failures (unrelated).

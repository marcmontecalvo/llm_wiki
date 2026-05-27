# Story HF.3: Category Registry and Aliases

Status: backlog

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

- [ ] Create category registry module (`src/llm_wiki/knowledge/categories.py` — AC: 1–2, 7)
  - [ ] `CANONICAL_CATEGORIES: frozenset[str]` — all `workspace.*` names
  - [ ] `CATEGORY_ALIASES: dict[str, str]` — mapping `household.*` → `workspace.*`
  - [ ] `normalize_category(raw: str) -> str` — returns canonical form or raises `UnknownFactCategory`
  - [ ] `is_valid_category(category: str) -> bool` — fast check
  - [ ] `_build_categories(): frozenset[str]` — reads from shared contract
- [ ] Update `_validate_category` in `WorkspaceFactStore` (from HF.1—AC: 6, 7)
  - [ ] Replace hardcoded validation with `normalize_category()` call
  - [ ] On invalid category: raise `UnknownFactCategory(category)` with error info
  - [ ] Ensure the exception carries `details.valid_categories` for HTTP response rendering
- [ ] Create REST category endpoint (`src/llm_wiki/api/routers/facts.py` — AC: 3)
  - [ ] `GET /v1/workspaces/{workspace_id}/facts/categories` — returns registry
  - [ ] Response: `{"canonical": [...], "aliases": {...}}` (no `enabled` field in v1; toggle TBD for future)
  - [ ] Same data served for all workspaces (global registry, not per-workspace)
  - [ ] Can serve from any workspace or directly from the module
- [ ] Create MCP categories tool (`src/llm_wiki/mcp/tools.py` — AC: 4)
  - [ ] `categories_list()` returns the same data structure as REST
- [ ] Create CLI categories command (`src/llm_wiki/cli.py` — AC: 5)
  - [ ] `def llm_wiki_facts_categories()` — prints to stdout
  - [ ] `--json` flag emits machine-parseable output (NFR-I3)
- [ ] Write tests (`tests/unit/test_category_registry.py` — AC: 1–7)
  - [ ] Test canonical categories are accepted as-is
  - [ ] Test each of the 9 aliases maps to its correct canonical form
  - [ ] Test unknown categories raise `UnknownFactCategory` with valid list
  - [ ] Test normalization is stable: normalize(normalize(x)) == normalize(x)
  - [ ] Test case sensitivity: `Workspace.Pets` should not normalize (fail, register exact forms only)
  - [ ] Test REST endpoint returns correct structure
  - [ ] Test MCP tool returns same data
  - [ ] Test CLI command prints correctly

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

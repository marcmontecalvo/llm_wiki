# Story HF.5: Homefront Contract Test Harness

Status: backlog

## Story

As an integration verifier,
I want contract tests covering all Homefront-required endpoints,
so that future changes don't break Homefront integration.

**Prerequisites:** Stories HF.1–HF.4 must be complete — this story tests the API, storage, categories, and conflict surfaces these stories provide.

## Acceptance Criteria

1. **Given** `pytest -m contract` (or the appropriate marker) **When** run **Then** all contract tests execute against a temporary wiki base.

2. **Given** a contract test run **When** it covers facts CRUD **Then** all of GET, PUT, DELETE, list, batch are tested with valid and invalid inputs.

3. **Given** a contract test run **When** it covers conflict behavior **Then** optimistic concurrency failures, conflict listing, and resolution are tested.

4. **Given** a contract test run **When** it covers workspace isolation **Then** facts for one workspace are not visible from another.

5. **Given** a contract test run **When** it covers category aliases **Then** `household.*` aliases are accepted and normalized to `workspace.*` equivalents.

6. **Given** the contract test file **When** committed ** Then** CI pipelines can be configured to run these tests on every push (or as a required gate).

## Tasks / Subtasks

- [ ] Create contract test module (`tests/contract/test_homefront_facts_api.py`)
  - [ ] Mark with `@pytest.mark.contract` in `conftest.py` or `pyproject.toml`
  - [ ] Test client setup: `TestClient(facts_router)` or `TestClient(app)` with a temp wiki base
  - [ ] `@pytest.fixture` for workspace ID (create/teardown via `tmp_path`)
  - [ ] _All asserts should be on HTTP status codes and response body structure — test the contract, not internal behavior_
- [ ] Write CRUD tests (AC: 2)
  - [ ] `test_put_fact_creates_new` — PUT with fresh key → 200, status: "written"
  - [ ] `test_put_fact_updates_existing` — PUT same key twice → 200, version incremented
  - [ ] `test_get_fact_returns_full_model` — GET after PUT → all fields present
  - [ ] `test_get_fact_missing_key` — GET nonexistent key → 404
  - [ ] `test_delete_fact_tombstones` — DELETE → 200, fact.status == "deleted"
  - [ ] `test_list_facts_paginated` — PUT 20 facts → GET with limit=5 → pagination works
  - [ ] `test_batch_put_mixed_results` — batch PUT 3 facts (2 new, 1 conflict expected) → per-result responses
  - [ ] `test_put_unknown_category_returns_422` — PUT with invalid category → 422
- [ ] Write conflict tests (AC: 3)
  - [ ] `test_version_conflict_detected` — PUT with expected_version mismatch → conflict status
  - [ ] `test_list_conflicts` — After conflict detected → GET conflicts returns entry
  - [ ] `test_resolve_conflict_canonical` — After conflict → PUT resolve → fact updated
  - [ ] `test_resolve_conflict_reject` — After conflict → reject candidate, version unchanged
  - [ ] `test_resolve_conflict_stale` — After conflict → mark existing as stale, write new value
  - [ ] `test_conflict_on_value_change` — PUT new value with matching version but different data → conflict detected
- [ ] Write workspace isolation tests (AC: 4)
  - [ ] `test_workspace_isolation_read` — PUT ws1/fact1, GET ws2/fact1 → 404
  - [ ] `test_workspace_isolation_list` — PUT facts in ws1 + ws2, list ws2 → ws2 facts only
  - [ ] `test_same_key_different_values_across_workspaces` — Same key in ws1 and ws2 → different values visible
  - [ ] `test_cross_workspace_delete` — DELETE ws1/fact, ws2/fact still exists
- [ ] Write category alias tests (AC: 5)
  - [ ] `test_alias_household_roster_normalized` — PUT household.roster → GET workspace.roster
  - [ ] `test_alias_household_schedule_normalized` — PUT household.schedule → GET workspace.schedule
  - [ ] `test_alias_household_pets_normalized` — PUT household.pets → GET workspace.pets
  - [ ] `test_all_aliases_normalized` — Loop through all 9 aliases, verify all normalize correctly
  - [ ] `test_alias_not_persisted` — Store household.appliances → GET shows workspace.appliances in category field
  - [ ] `test_invalid_category_fails` — PUT nonexistent.category → 422
- [ ] Write stability regression tests (AC: 1)
  - [ ] `test_pages_still_accessible` — GET `/v1/pages` after HF endpoints wired → still works as before (AC: 1)
  - [ ] `test_query_still_works` — POST `/v1/query` → still returns results without fact store (AC: 1)
  - [ ] `test_health_includes_facts_ready` — `GET /v1/health` returns `facts_ready: true` after setup — no unhandled `UnexpectedError` (AC: 1)
- [ ] Write MCP tool contract tests (AC: 7)
  - [ ] `test_mcp_facts_tools_listed` — `tools/list` returns all 6 fact tools (`fact_get`, `fact_list`, `fact_put`, `fact_delete`, `fact_history`, `fact_batch_put`)
  - [ ] `test_mcp_fact_get_works` — `fact_get` returns same data as REST GET
  - [ ] `test_mcp_fact_put_works` — `fact_put` creates/updates same as REST PUT
  - [ ] `test_mcp_categories_list_works` — `categories_list` returns same structure as REST
- [ ] Register test marker in `pyproject.toml` (AC: 1, 6)
  - [ ] Add `[tool.pytest.ini_options]` section: `markers = ["contract: Homefront contract tests"]`

## Dev Notes

### Test Client Setup

```python
# tests/contract/test_homefront_facts_api.py
import pytest
import tempfile, os, shutil
from fastapi.testclient import TestClient

from llm_wiki.api.app import create_app

@pytest.fixture
def wiki_base(tmp_path):
    return str(tmp_path)

@pytest.fixture
def client(wiki_base):
    app = create_app(wiki_root=wiki_base)
    yield TestClient(app)

@pytest.fixture
def workspace_id():
    return "homefront:0190013f-contract-test"

@pytest.fixture
def data(client, workspace_id):
    """Helper: create a fact and return its key."""
    key = "workspace.pets.dog_name"
    client.put(f"/v1/workspaces/{workspace_id}/facts/{key}", json={
        "category": "workspace.pets",
        "key": key,
        "value": {"name": "Rex", "species": "dog"},
        "source": {"type": "manual_admin", "id": "test-1"},
        "provenance": [],
    })
    yield key
    # Teardown: delete the fact
    client.delete(f"/v1/workspaces/{workspace_id}/facts/{key}")

def test_put_fact_creates_new(client, workspace_id):
    ...
```

### Test Data Factory

```python
def make_fact(workspace_id: str, fact_key: str, category: str,
              value: dict, source_type: str = "manual_admin") -> dict:
    return {
        "category": category,
        "key": fact_key,
        "value": value,
        "source": {"type": source_type},
        "provenance": [],
    }
```

### Contract Test Naming Convention

Each test name encodes the contract element:
- `test_<surface>_<operation>_<expected_result>`
- Examples: `test_facts_put_creates_new`, `test_workspace_isolation_read`, `test_conflict_version_mismatch_detected`

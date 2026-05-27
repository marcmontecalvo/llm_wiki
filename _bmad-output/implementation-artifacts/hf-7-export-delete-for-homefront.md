# Story HF.7: Export/Delete for Homefront

Status: backlog

## Story

As a Homefront integration client,
I need structured export and profile-scoped delete for a workspace,
so that profile data can be exported and deleted per Homefront's privacy contract.

**Prerequisites:** Stories HF.1–HF.6 must be complete — this story extends the facts API (HF.1), review queue (HF.4), and knowledge scoping (HF.6) with export and deletion abilities for Homefront's privacy compliance requirements.

## Acceptance Criteria

1. **Given** `GET /v1/workspaces/{workspace_id}/facts/export` **When** called **Then** it returns all active facts for the workspace in JSON, with `schema_version: "homefront-export-v1"` and `workspace_id` included in the response body.

2. **Given** `GET /v1/workspaces/{workspace_id}/facts/export?profile_id=<pid>` **When** called with a profile_id **Then** it returns facts with `visibility == "profile_private"` scoped to that profile_id (matched via `provenance[].source_id` matching the profile or fact value containing a profile reference), plus any other facts with `visibility == "profile_private"` for the workspace (case where no exact profile match exists).

3. **Given** a profile-scoped export is returned **When** examined **Then** it includes `schema_version: "homefront-export-v1"`, `workspace_id`, and each fact carries its `provenance` list.

4. **Given** `POST /v1/workspaces/{workspace_id}/facts/delete-by-profile` with `"profile_id": "<pid>"` **When** called **Then** only facts with `visibility == "profile_private"` for that profile are deleted or tombstoned — shared workspace facts (`visibility == "workspace"`) are not affected.

5. **Given** the fact store has corrupted or unreadable data **When** an export is requested **Then** it returns HTTP 503 with `"error_code": "FACT_EXPORT_FAILED"` and a human-readable error message — never an empty successful bundle that looks correct.

6. **Given** the LLM-Wiki export as part of a full Homefront export bundle per contract v1 section 9.1 ** When** assembled ** Then** the LLM-Wiki portion contains `"llm_wiki": {"facts": [...], "pages": [...], "provenance": [...]}`. The honcho and homefront sections are assembled by the calling service (Homefront), not by this story.

## Tasks / Subtasks

- [ ] Create export service (`src/llm_wiki/knowledge/export.py` — AC: 1–5)
  - [ ] `export_facts(workspace_id: str, profile_id: str | None = None) -> dict`
    - [ ] When `profile_id` given: filter to `visibility == "profile_private"` facts matching that profile (via `provenance[].source_id` == profile_id, or fact `value` containing a tracked profile reference)
    - [ ] When `profile_id` not given: return all active facts for workspace
    - [ ] Response includes `schema_version: "homefront-export-v1"`, `workspace_id`, `facts` list, `provenance` list
    - [ ] Each fact entry includes `provenance` (source references for all facts/pages in export)
  - [ ] `tombstone_profile_facts(workspace_id: str, profile_id: str) -> int`
    - [ ] Finds all facts with `visibility == "profile_private"` AND matching the given profile_id (via `provenance[].source_id` == profile_id, or fact `value` containing a profile reference the application tracks)
    - [ ] Sets `status: "deleted"` on each fact via existing `delete_fact()` method
    - [ ] Returns count of tombstoned facts
- [ ] Create REST export/delete routes (`src/llm_wiki/api/routers/facts.py` — AC: 1–5)
  - [ ] `GET /v1/workspaces/{workspace_id}/facts/export` — workspace facts export (AC: 1)
  - [ ] `GET /v1/workspaces/{workspace_id}/facts/export?profile_id=<pid>` — profile-scoped export (AC: 2, 3)
  - [ ] `POST /v1/workspaces/{workspace_id}/facts/delete-by-profile` — body `{"profile_id": str}` → tombstones profile-private facts (AC: 4)
  - [ ] Error handling: if workspace not found or export fails, raises `FactExportFailed` → HTTP 503 with clear message (AC: 5)
  - [ ] Note: AC:6 (full Homefront bundle with honcho/homefront sections) is assembled by the caller (Homefront), not by this route.
- [ ] Wire into FastAPI app
  - [ ] `app.include_router` adds the export delete router
- [ ] Write tests (`tests/unit/test_facts_export.py` — AC: 1–6)
  - [ ] `test_export_workspace_returns_all_active_facts` — no profile_id → all active facts
  - [ ] `test_export_with_profile_id_returns_only_private` — profile_id → only profile-private facts matching that profile (matched via provenance[] or value)
  - [ ] `test_export_includes_schema_version` — response has `schema_version == "homefront-export-v1"`
  - [ ] `test_export_includes_provenance` — each fact has provenance list
  - [ ] `test_tombstone_profile_private_facts_only` — tombstone doesn't touch `visibility == "workspace"` facts
  - [ ] `test_error_on_corrupt_data` — corrupted store → HTTP 503 with error code
  - [ ] `test_full_homefront_export_bundle_structure` — export contains all top-level keys from contract v1 section 9.1

## Dev Notes

### Export Response Shape (from shared contract v1 section 9.1)

```json
{
  "schema_version": "homefront-export-v1",
  "workspace_id": "...",
  "generated_at": "...",
  "llm_wiki": {
    "facts": [/* list of KnowledgeFact with provenance */],
    "pages": [/* list of workspace pages */],
    "provenance": [/* root references */]
  }
}
```

### Tombstone Strategy

```python
def tombstone_profile_facts(workspace_id: str, profile_id: str) -> int:
    """Tombstone all facts visible only to the given profile.
    Shared facts (visibility=workspace) are NOT affected.
    Profile match is via provenance[].source_id or tracked profile field in fact value.
    Returns count of tombstoned facts.
    """
    count = 0
    for fact in store.list_facts(workspace_id):
        if fact.get("visibility") != "profile_private":
            continue
        # Match profile via provenance refs
        provenance_ids = {ref.source_id for ref in fact["provenance"]}
        if profile_id in provenance_ids:
            store.delete_fact(workspace_id, fact["key"])
            count += 1
    return count
```

### Provenance Reconstruction

```python
def get_provenance(workspace_id: str, fact_key: str) -> list[ProvenanceRef]:
    fact = store.get_fact(workspace_id, fact_key)
    if fact is None:
        return []
    provenance = []
    for ref in fact.provenance:
        provenance.append(ref)
    return provenance
```

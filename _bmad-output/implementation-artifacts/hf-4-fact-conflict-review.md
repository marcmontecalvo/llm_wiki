# Story HF.4: Fact Conflict and Review Queue

Status: backlog

## Story

As a wiki operator,
I want conflicting fact writes to be detected and queued for review,
so that incompatible facts don't silently overwrite each other.

**Prerequisites:** Stories HF.1–HF.3 must be complete — conflict detection operates on facts with history (HF.2) and validates against categories (HF.3).

## Acceptance Criteria

1. **Given** a `PUT /v1/workspaces/{workspace_id}/facts/{fact_key}` with `expected_previous_version` **When** the stored version differs **Then** it returns `conflict_detected` status with `candidates` and their `version` fields.

2. **Given** no `expected_previous_version` is provided **When** the write occurs **Then** it updates the fact but checks if the old value conflicts with the new value (different data in the same slot).

3. **Given** a conflict is detected **When** it is recorded **Then** the fact is tagged with `status: "conflicted"` and the conflict is added to the review queue.

4. **Given** a review queue item for a fact conflict **When** listed **Then** it shows the workspace, fact_key, conflicting candidates with values and source types, and current status.

5. **Given** `llm-wiki facts review list [--workspace <id>]` or the MCP `conflict_list` tool **When** called ** Then** it returns workspace-scoped list of pending conflicts (AC: 4).

6. **Given** an admin resolves a conflict **When** `POST /v1/workspaces/{workspace_id}/facts/{fact_key}/resolve` is called with a resolution choice **Then** the chosen candidate becomes canonical, the conflict is marked resolved, and the fact version is incremented.

7. **Given** a `KnowledgeSource.type` of `honcho_conclusion` ** When** a fact is first written ** Then** it defaults to `status: "pending_review"` for safety.

8. **Given** REST/MCP/CLI surfaces ** When** conflicts are listed ** Then** conflict responses include `requires_review: true` and the structured conflict data.

## Tasks / Subtasks

- [ ] Implement conflict detection in `WorkspaceFactStore` (AC: 1–3, 7)
  - [ ] `put_fact()` option: `expected_previous_version: int | None` — when set, compare with current version
  - [ ] If versions don't match: return `KnowledgeFactWriteResponse(status="conflict_detected", conflict={...})`
  - [ ] Add `value_conflict_check()`: compares old value vs new value for semantic conflict (not just version)
  - [ ] If values differ for the same key: create conflict entry in review queue
  - [ ] `class FactConflict(BaseModel)`: `key`, `category`, `workspace_id`, `candidates` (list), `requires_review: bool`
  - [ ] Add conflict entries to `wiki_system/workspaces/{workspace_id}/facts/conflicts.jsonl`
  - [ ] Persist conflict with timestamp, source types, values, and versions
- [ ] Implement review queue storage (AC: 3–6, 8)
  - [ ] `ReviewQueue` module at `src/llm_wiki/knowledge/review.py`
  - [ ] `_conflicts_path(workspace_id) -> str` returns path to `facts/conflicts.jsonl`
  - [ ] `list_conflicts(workspace_id) -> list[FactConflict]` — reads unresolved conflicts, sorted by timestamp desc
  - [ ] `resolve_conflict(workspace_id, fact_key, choice: Literal["canonical", "reject", "stale"]) -> KnowledgeFactWriteResponse`
    - [ ] `canonical`: pick the accepted candidate, write as latest version
    - [ ] `reject`: reject the new candidate, keep existing
    - [ ] `stale`: mark existing as stale, write the new value
  - [ ] Conflict entries: `{"key": "...", "candidates": [...], "resolved": bool, "resolved_at": "..." | null}`
  - [ ] Mark as resolved: set `resolved: true`, `resolved_at: now`, store resolution choice
- [ ] Create REST conflict endpoints (AC: 4–5, 8)
  - [ ] `GET /v1/workspaces/{workspace_id}/facts/conflicts` — list unresolved conflicts
  - [ ] `POST /v1/workspaces/{workspace_id}/facts/{fact_key}/resolve` — accepts `{"choice": "canonical" | "reject" | "stale", "candidate_index": int | None}`
  - [ ] Return resolved conflict with updated status
- [ ] Create MCP conflict tools (AC: 5)
  - [ ] `conflict_list(workspace_id: str)` — calls review queue
  - [ ] `conflict_resolve(workspace_id: str, fact_key: str, choice: str, candidate_index: int | None)` — resolves
- [ ] Create CLI conflict commands (AC: 5)
  - [ ] `llm-wiki facts review list [--workspace <id>] [--json]`
  - [ ] `llm-wiki facts review resolve <fact_key> --choice <canonical|reject|stale> [--index <n>] [--workspace <id>] [--json]`
- [ ] Implement `pending_review` default for honcho sources (AC: 7)
  - [ ] In `put_fact()`: if `write_req.source.type == "honcho_conclusion"` and workspace policy requires review:
  - [ ] Set `status: "pending_review"` — the fact is written but not active
  - [ ] Configurable: `review_policy: {honcho_conclusion: "pending_review", ...}` in `daemon.yaml`
  - [ ] Non-honcho sources default to `status: "active"` (instant trust for manual/hardware/social/calendars)
- [ ] Write tests (`tests/unit/test_fact_conflicts.py` — AC: 1–8)
  - [ ] Test version conflict detection: expected_version mismatches current
  - [ ] Test value conflict: same version (optimistic concurrency), different value
  - [ ] Test conflict creation and storage
  - [ ] Test conflict listing (resolved vs unresolved)
  - [ ] Test resolution: canonical choice
  - [ ] Test resolution: reject choice
  - [ ] Test resolution: stale choice
  - [ ] Test honcho_conclusion defaults to pending_review
  - [ ] Test other source types default to active
  - [ ] Test conflict_delete/cleanup after resolution

## Dev Notes

### Conflict Detection Logic

```python
def put_fact(self, write_req: KnowledgeFactWriteRequest) -> KnowledgeFactWriteResponse:
    # ... validation, lock acquisition ...

    current = self._latest_entry(workspace_id, fact_key)
    current_version = current.version if current else 0

    if write_req.expected_previous_version is not None and current:
        if write_req.expected_previous_version != current_version:
            # Version mismatch — return conflict
            return KnowledgeFactWriteResponse(
                key=fact_key,
                status="conflict_detected",
                fact=None,
                conflict=KnowledgeConflict(
                    key=fact_key,
                    workspace_id=workspace_id,
                    candidates=[
                        {"value": current.value, "source": current.source,
                         "confidence": current.confidence, "version": current_version},
                        {"value": write_req.value, "source": write_req.source,
                         "confidence": write_req.confidence, "version": current_version + 1},
                    ],
                    requires_review=True,
                ),
            )

    # No version conflict — proceed with write
    new_version = current_version + 1
    fact = KnowledgeFact(...)
    self._write_entry(workspace_id, fact_key, fact)
    return KnowledgeFactWriteResponse(key=fact_key, status="written", fact=fact)
```

### Conflict JSONL Entry

```jsonl
{"key": "workspace.schedule.school_start_time", "workspace_id": "homefront:0190...", "candidates": [
  {"value": {"time": "08:00"}, "source": {"type": "google_calendar"}, "confidence": 0.92, "version": 5},
  {"value": {"time": "08:15"}, "source": {"type": "manual_admin"}, "confidence": 0.88, "version": 5}
], "requires_review": true, "resolved": false, "created_at": "2026-05-27T10:00:00Z"}
```

### Conflict Resolution Flow

```
operator/agent calls POST /facts/{key}/resolve
  → lookup conflict in conflicts.jsonl for this key
  → pick candidate at index N → write as new version
  → mark conflict as resolved: {resolved: true, resolved_at: now, choice: "canonical"}
  → return updated KnowledgeFactWriteResponse
```

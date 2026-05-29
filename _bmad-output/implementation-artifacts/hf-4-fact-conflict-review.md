# Story HF.4: Fact Conflict and Review Queue

Status: done

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

- [x] Implement conflict detection in `WorkspaceFactStore` (AC: 1–3, 7)
  - [x] `put_fact()` option: `expected_previous_version: int | None` — when set, compare with current version
  - [x] If versions don't match: return `KnowledgeFactWriteResponse(status="conflict_detected", conflict={...})`
  - [x] Add `value_conflict_check()`: compares old value vs new value for semantic conflict (not just version)
  - [x] If values differ for the same key: create conflict entry in review queue
  - [x] `class FactConflict(BaseModel)`: `key`, `category`, `workspace_id`, `candidates` (list), `requires_review: bool`
  - [x] Add conflict entries to `wiki_system/workspaces/{workspace_id}/facts/conflicts.jsonl`
  - [x] Persist conflict with timestamp, source types, values, and versions
- [x] Implement review queue storage (AC: 3–6, 8)
  - [x] `ReviewQueue` module at `src/llm_wiki/knowledge/review.py`
  - [x] `_conflicts_path(workspace_id) -> str` returns path to `facts/conflicts.jsonl`
  - [x] `list_conflicts(workspace_id) -> list[FactConflict]` — reads unresolved conflicts, sorted by timestamp desc
  - [x] `resolve_conflict(workspace_id, fact_key, choice: Literal["canonical", "reject", "stale"]) -> KnowledgeFactWriteResponse`
    - [x] `canonical`: pick the accepted candidate, write as latest version
    - [x] `reject`: reject the new candidate, keep existing
    - [x] `stale`: mark existing as stale, write the new value
  - [x] Conflict entries: `{"key": "...", "candidates": [...], "resolved": bool, "resolved_at": "..." | null}`
  - [x] Mark as resolved: set `resolved: true`, `resolved_at: now`, store resolution choice
- [x] Create REST conflict endpoints (AC: 4–5, 8)
  - [x] `GET /v1/workspaces/{workspace_id}/facts/conflicts` — list unresolved conflicts
  - [x] `POST /v1/workspaces/{workspace_id}/facts/{fact_key}/resolve` — accepts `{"choice": "canonical" | "reject" | "stale", "candidate_index": int | None}`
  - [x] Return resolved conflict with updated status
- [x] Create MCP conflict tools (AC: 5)
  - [x] `conflict_list(workspace_id: str)` — calls review queue
  - [x] `conflict_resolve(workspace_id: str, fact_key: str, choice: str, candidate_index: int | None)` — resolves
- [x] Create CLI conflict commands (AC: 5)
  - [x] `llm-wiki facts review list [--workspace <id>] [--json]`
  - [x] `llm-wiki facts review resolve <fact_key> --choice <canonical|reject|stale> [--index <n>] [--workspace <id>] [--json]`
- [x] Implement `pending_review` default for honcho sources (AC: 7)
  - [x] In `put_fact()`: if `write_req.source.type == "honcho_conclusion"` and workspace policy requires review:
  - [x] Set `status: "pending_review"` — the fact is written but not active
  - [x] Configurable: `review_policy: {honcho_conclusion: "pending_review", ...}` in `daemon.yaml`
  - [x] Non-honcho sources default to `status: "active"` (instant trust for manual/hardware/social/calendars)
- [x] Write tests (`tests/unit/test_fact_conflicts.py` — AC: 1–8)
  - [x] Test version conflict detection: expected_version mismatches current
  - [x] Test value conflict: same version (optimistic concurrency), different value
  - [x] Test conflict creation and storage
  - [x] Test conflict listing (resolved vs unresolved)
  - [x] Test resolution: canonical choice
  - [x] Test resolution: reject choice
  - [x] Test resolution: stale choice
  - [x] Test honcho_conclusion defaults to pending_review
  - [x] Test other source types default to active
  - [x] Test conflict_delete/cleanup after resolution

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

## File List

- `src/llm_wiki/knowledge/models.py` — Modified: added `workspace_id`, `resolved`, `resolved_at`, `resolution_choice` to `KnowledgeConflict`; added `KnowledgeConflictResolutionRequest` model
- `src/llm_wiki/knowledge/review.py` — New: ReviewQueue module with add_conflict, list_conflicts, resolve_conflict
- `src/llm_wiki/knowledge/storage.py` — Modified: conflict detection in `_put_fact_internal`, `_value_conflict_check` static method, `review_queue` property
- `src/llm_wiki/api/routers/facts.py` — Modified: added GET /facts/conflicts and POST /facts/{fact_key}/resolve endpoints
- `src/llm_wiki/mcp/tools.py` — Modified: added `conflict_list` and `conflict_resolve` MCP tools
- `src/llm_wiki/cli.py` — Modified: added `facts review list` and `facts review resolve` CLI commands
- `tests/unit/test_fact_conflicts.py` — New: 20 tests covering AC 1–8
- `tests/unit/test_facts_api.py` — Modified: updated `test_put_returns_stale_rejected_on_version_mismatch` to expect `conflict_detected`

## Change Log

- Addressed fact conflict detection and review queue implementation (Date: 2026-05-28)
  - Conflict detection: version mismatch and value diff detection in put_fact
  - Review queue: JSONL-backed storage and resolution (canonical/reject/stale)
  - REST, MCP, CLI interfaces for conflict listing and resolution
  - honcho_conclusion sources default to pending_review status
- Code review completed 2026-05-29 — all findings addressed, 20 new tests pass, status updated to done

## Dev Agent Record

### Implementation Plan

Implemented conflict detection pipeline across 6 layers:
1. Models: Extended KnowledgeConflict with workspace_id/resolved fields; added KnowledgeConflictResolutionRequest
2. ReviewQueue: File-backed module at knowledge/review.py with atomic JSONL writes
3. Storage: Modified _put_fact_internal to detect version conflicts (expected_previous_version mismatch) and value conflicts (different values for same key), added _value_conflict_check for recursive dict comparison
4. REST: GET /facts/conflicts and POST /facts/{key}/resolve endpoints
5. MCP: conflict_list and conflict_resolve tools
6. CLI: `llm-wiki facts review list` and `llm-wiki facts review resolve`

### Debug Log

- **datetime.UTC bug**: Initially used `datetime.now(tz=datetime.UTC)` but `datetime` is imported as class, not module. Fixed to `from datetime import UTC, datetime` and `datetime.now(tz=UTC)`.
- **stale_rejected vs conflict_detected**: Existing test expected `stale_rejected` for version mismatch, now correctly expects `conflict_detected` per new contract.
- **zip B95 lint**: Added `strict=True` to zip() call per ruff B95 rule.

### Completion Notes

- All 20 new conflict tests pass
- All 58 existing fact tests pass
- Full unit suite: 1588 passed (1 pre-existing failure in test_observability due to WIKI_UI_PASSWORD env var)
- Ruff lint: all checks pass on modified files

### Code Review

**Date:** 2026-05-29
**Reviewer:** Claude Code (code-review skill)

#### Findings Addressed
- [x] Conflict listing endpoint (`/facts/conflicts`) registered before catch-all `{fact_key}` — verified route order in facts.py router
- [x] Resolution endpoints similarly unreachable before fix — confirmed resolution via store-API tests
- [x] `pending_review` default applies only to `honcho_conclusion` type — verified in conflict detection logic
- [x] JSONL write atomicity in ReviewQueue — `os.replace` + temp file confirmed

### Status

Story complete. All acceptance criteria satisfied:
- AC1: Version conflict detection with conflict_detected response
- AC2: Value conflict detection without explicit version check
- AC3: Conflicts tagged with status='conflicted' and added to review queue
- AC4: Conflict listing with workspace/fact_key/candidates/status
- AC5: REST/MCP/CLI all surface conflict listing
- AC6: Resolution with canonical/reject/stale choices
- AC7: honcho_conclusion defaults to pending_review
- AC8: Conflict responses include requires_review and structured data

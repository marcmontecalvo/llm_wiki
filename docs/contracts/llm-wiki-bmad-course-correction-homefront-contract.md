# LLM-Wiki BMAD Course Correction — Homefront Workspace Facts Contract

Status: input for `/bmad-correct-course` or equivalent BMAD change workflow
Repo: `marcmontecalvo/llm_wiki`
Basis: full uploaded `_bmad-output` archive review

---

## Problem

LLM-Wiki is currently planned and implemented as a daemon-governed page/domain/wiki service with MCP, REST, CLI, governance, search, exports, UI/TUI, and Honcho bridge features.

That is useful, but it does **not** yet satisfy Homefront's needed deterministic fact contract.

Homefront needs LLM-Wiki to be:

```text
structured exact facts service + governed wiki/document knowledge service
```

Current LLM-Wiki BMAD artifacts mostly define:

```text
domain/page/query/search/ingest/export service
```

The missing piece is a first-class Workspace Facts API.

---

## Required Direction

Add a Homefront-compatible contract layer without throwing away existing work.

LLM-Wiki keeps:

- domains
- pages
- markdown source of truth where appropriate
- MCP / REST / CLI parity
- query/search/read/list/export
- contradiction detection
- confidence scoring
- authority scoring
- synthesis cache
- dashboards
- archive lifecycle
- Honcho detect/push/pull bridge
- WebUI/TUI, though not required by Homefront integration

LLM-Wiki adds:

- `workspace_id` scoping
- exact structured facts API
- fact history/versioning
- fact source/provenance/visibility/status
- conflict/review behavior at fact level
- Homefront contract tests

---

## Object Model

Adopt the shared contract names:

| Object | Meaning in LLM-Wiki |
|---|---|
| `Workspace` | Top-level isolated Homefront cell/household boundary |
| `Peer` | Person/assistant/support/system actor referenced in provenance or personal scoping |
| `Session` | Source interaction context when content came from Honcho/Homefront |
| `Message` | Source message/utterance/event reference |
| `Fact` | Deterministic structured key/value knowledge item |
| `Page` | Existing governed markdown/wiki artifact |
| `Domain` | Organizational/search/routing label, not a security boundary |

Do not use Domain as the primary isolation object for Homefront. Domain is categorization. Workspace is isolation.

---

## Required API

### Exact Facts REST API

```http
GET    /v1/workspaces/{workspace_id}/facts
GET    /v1/workspaces/{workspace_id}/facts/{fact_key}
PUT    /v1/workspaces/{workspace_id}/facts/{fact_key}
DELETE /v1/workspaces/{workspace_id}/facts/{fact_key}
GET    /v1/workspaces/{workspace_id}/facts/{fact_key}/history
POST   /v1/workspaces/{workspace_id}/facts:batch
```

### Exact Facts MCP Tools

```text
fact_get
fact_list
fact_put
fact_delete
fact_history
fact_batch_put
```

### Knowledge API

Existing endpoints may remain, but Homefront-scoped equivalents are needed:

```http
POST /v1/workspaces/{workspace_id}/knowledge/inbox
POST /v1/workspaces/{workspace_id}/knowledge/search
POST /v1/workspaces/{workspace_id}/knowledge/query
GET  /v1/workspaces/{workspace_id}/knowledge/pages/{page_id}
GET  /v1/workspaces/{workspace_id}/knowledge/review
GET  /v1/workspaces/{workspace_id}/knowledge/conflicts
GET  /v1/workspaces/{workspace_id}/knowledge/stale
POST /v1/workspaces/{workspace_id}/knowledge/export
```

---

## Fact Schema

```python
class KnowledgeFact(BaseModel):
    id: UUID
    workspace_id: str
    category: str
    key: str
    value: dict[str, Any]

    source: KnowledgeSource
    provenance: list[ProvenanceRef] = []
    confidence: float | None = None
    authority_score: float | None = None

    status: Literal[
        "active",
        "pending_review",
        "conflicted",
        "archived",
        "deleted",
    ]

    visibility: Literal[
        "workspace",
        "adults_only",
        "profile_private",
        "support_redacted",
        "system_internal",
    ] = "workspace"

    valid_from: datetime | None = None
    valid_until: datetime | None = None

    created_at: datetime
    updated_at: datetime
    version: int
```

```python
class KnowledgeSource(BaseModel):
    type: Literal[
        "manual_admin",
        "assistant_suggestion",
        "google_calendar",
        "home_assistant",
        "honcho_conclusion",
        "document_ingest",
        "system_import",
    ]
    id: str | None = None
    observed_at: datetime | None = None
```

```python
class ProvenanceRef(BaseModel):
    source_type: str
    source_id: str | None = None
    workspace_id: str | None = None
    peer_id: str | None = None
    session_id: str | None = None
    message_id: str | None = None
    page_id: str | None = None
    excerpt: str | None = None
    captured_at: datetime | None = None
```

---

## Storage Decision

The current LLM-Wiki architecture says filesystem/plain markdown is the source of truth and no external database is required.

This course correction can preserve that by using a file-backed structured facts store.

Recommended layout:

```text
wiki_system/
  workspaces/
    {workspace_id}/
      facts/
        index.json
        categories/
          workspace.pets.jsonl
          workspace.schedule.jsonl
          workspace.assignments.jsonl
        history/
          {fact_key_hash}.jsonl
      pages/
      inbox/
      exports/
```

Rules:

- Fact current state must be machine-readable without parsing markdown prose.
- Fact history must be append-only.
- Writes must be atomic using temp file + `os.replace`.
- Concurrent writes must use a workspace/fact-key lock.
- Pages may reference facts, but pages are not the canonical fact state.
- Existing markdown/page exports can be generated from facts, not vice versa.

Postgres may be considered later, but the immediate correction should not require introducing a database if the project wants to preserve file-backed ownership.

---

## Category Registry

Initial categories:

```text
workspace.roster
workspace.assignments
workspace.pets
workspace.appliances
workspace.preferences
workspace.schedule
workspace.vehicles
workspace.presence
workspace.recurring_responsibilities
workspace.rooms
workspace.integrations
workspace.voice_nodes
```

Legacy aliases accepted during transition:

```text
household.roster -> workspace.roster
household.assignments -> workspace.assignments
household.pets -> workspace.pets
household.appliances -> workspace.appliances
household.preferences -> workspace.preferences
household.schedule -> workspace.schedule
household.vehicles -> workspace.vehicles
household.presence -> workspace.presence
household.recurring_responsibilities -> workspace.recurring_responsibilities
```

Unknown categories should return a stable error shape:

```json
{
  "error_code": "unknown_knowledge_category",
  "message": "The category '[X]' is not recognized",
  "valid_categories": ["..."]
}
```

Homefront will also validate before calling LLM-Wiki.

---

## Conflict and Review

Fact writes must detect conflicts when a new source attempts to overwrite an active value from another source without expected version/timestamp.

Write result statuses:

```text
written
unchanged
stale_rejected
pending_review
conflict_detected
```

Conflict response:

```json
{
  "key": "workspace.schedule.school_start_time",
  "status": "conflicted",
  "canonical_value": null,
  "candidates": [
    {
      "value": {"time": "08:00"},
      "source": {"type": "google_calendar"},
      "confidence": 0.92
    },
    {
      "value": {"time": "08:15"},
      "source": {"type": "manual_admin"},
      "confidence": 0.88
    }
  ],
  "requires_review": true
}
```

Existing contradiction detection should be reused, but exact fact conflict handling must not depend solely on page-level contradiction reports.

---

## Honcho Bridge Clarification

Epic H is useful but must be clarified.

### Honcho Push

Pushing LLM-Wiki exports to Honcho makes wiki knowledge available as context/source material for Honcho-enabled agents.

It does not mean:

- Honcho owns facts.
- Honcho becomes the source of truth for LLM-Wiki pages.
- Homefront can skip LLM-Wiki exact fact reads.

### Honcho Pull

Harvesting Honcho conclusions into LLM-Wiki inbox creates candidate source material.

It does not mean:

- Honcho conclusions are automatically trusted facts.
- Conversation-derived facts bypass review.
- LLM-Wiki should promote sensitive household facts without Homefront policy/confirmation.

Add review gates for harvested Honcho conclusions:

- `honcho_conclusion` source type
- default `pending_review` for safety-sensitive categories
- conflict detection against active facts
- provenance references to workspace/peer/session/message where available

---

## Epic Corrections

Add a new Homefront Integration epic or insert these stories before claiming Homefront compatibility.

### Story HF.1 — Workspace Facts API Foundation

As a Homefront integration client, I need exact structured facts scoped by workspace so that Homefront can run simulations from deterministic knowledge.

Acceptance criteria:

1. REST endpoints under `/v1/workspaces/{workspace_id}/facts` exist.
2. MCP tools `fact_get`, `fact_list`, `fact_put`, `fact_delete`, `fact_history`, and `fact_batch_put` exist.
3. Facts include `workspace_id`, `category`, `key`, `value`, `source`, `provenance`, `status`, `visibility`, `version`, and timestamps.
4. Writes are atomic and versioned.
5. Unknown categories return `unknown_knowledge_category`.
6. Existing page/query/search behavior is not broken.

### Story HF.2 — Workspace Fact Storage and History

Acceptance criteria:

1. Current facts are machine-readable without markdown parsing.
2. Fact history is append-only.
3. Writes use temp file + `os.replace`.
4. Per-workspace and per-fact locks prevent concurrent write races.
5. Startup integrity check detects corrupt fact indexes.

### Story HF.3 — Category Registry and Aliases

Acceptance criteria:

1. `workspace.*` categories are canonical.
2. `household.*` aliases are accepted and normalized.
3. Category registry is exposed through REST/MCP/CLI.
4. Unknown categories are stable errors.
5. Tests cover aliases and invalid categories.

### Story HF.4 — Fact Conflict and Review Queue

Acceptance criteria:

1. Conflicting writes produce `conflict_detected`.
2. Conflicted reads return candidates and require review.
3. Admin/operator can list fact conflicts.
4. Review can choose canonical value, reject candidate, or mark stale.
5. Sensitive Honcho-harvested conclusions default to pending review.

### Story HF.5 — Homefront Contract Test Harness

Acceptance criteria:

1. A contract test file verifies Homefront-required endpoints.
2. Tests cover read/write/list/history/delete/batch.
3. Tests cover conflict behavior.
4. Tests cover workspace isolation.
5. Tests cover category aliases.
6. Tests run in CI.

### Story HF.6 — Workspace-Scoped Knowledge API

Acceptance criteria:

1. Existing query/search/page/export endpoints support workspace scoping.
2. Domain remains categorization, not isolation.
3. `X-Profile-Id`/peer scoping is advisory from Homefront and does not replace workspace scoping.
4. Personal domains cannot leak across workspace boundaries.

### Story HF.7 — Export/Delete for Homefront

Acceptance criteria:

1. LLM-Wiki can export facts/pages for a workspace and optionally a peer/profile.
2. Export includes schema version and provenance.
3. Profile-private facts can be deleted/tombstoned.
4. Shared workspace facts are not deleted by profile deletion unless explicitly profile-private.
5. Unavailable/corrupt export returns failure, not an empty successful bundle.

---

## Planning Doc Changes

Update:

```text
_bmad-output/planning-artifacts/prd.md
_bmad-output/planning-artifacts/architecture.md
_bmad-output/planning-artifacts/epics.md
_bmad-output/implementation-artifacts/sprint-status.yaml
```

Add or update normal docs outside `_bmad-output` as appropriate:

```text
docs/HOMEFRONT_CONTRACT.md
docs/API_FACTS.md
docs/CONFIG.md
docs/GOVERNANCE.md
README.md
```

---

## BMAD Story Creation Prompt

Use inside `marcmontecalvo/llm_wiki`:

```text
Run BMAD Correct Course for LLM-Wiki.

We need an immediate architecture and epic/story correction to support Homefront as a first-class integration target.

Use the shared contract:
Homefront / Honcho / LLM-Wiki Shared Memory + Knowledge Contract v1.

Do not remove existing page/domain/wiki functionality.

Add a Workspace Facts API:
- Workspace is the technical top-level object aligned with Honcho.
- Fact is deterministic structured knowledge.
- Page remains governed markdown/wiki/document knowledge.
- Domain remains a routing/search/categorization label, not an isolation boundary.

Required changes:
1. Update PRD.
2. Update architecture.
3. Update epics.
4. Add a Homefront Integration epic or equivalent stories.
5. Add REST and MCP contract definitions for `/v1/workspaces/{workspace_id}/facts`.
6. Add fact schema, category registry, aliases, history, conflict/review, export/delete, and contract tests.
7. Clarify Honcho push/pull as source/context bridge only, not fact authority.
8. Preserve file-backed operation if possible; facts must still be machine-readable and atomic.

Do not stop until planning docs and implementation artifacts are internally consistent.
```

---

## Acceptance Criteria for the Course Correction

- LLM-Wiki planning docs explicitly support `workspace_id`.
- Facts are distinct from pages.
- Workspace scoping is distinct from domain scoping.
- Domain is not described as the Homefront security boundary.
- Homefront exact facts API is defined.
- Category aliases preserve compatibility with existing Homefront stories.
- Honcho bridge is clarified as non-authoritative source/context flow.
- Contract tests exist as planned stories.
- Existing MCP/REST/CLI parity remains.

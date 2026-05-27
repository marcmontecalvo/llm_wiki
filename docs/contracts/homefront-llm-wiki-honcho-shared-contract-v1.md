# Homefront / Honcho / LLM-Wiki Shared Memory + Knowledge Contract v1

Status: proposed for immediate BMAD course correction
Applies to: `marcmontecalvo/Homefront`, `marcmontecalvo/llm_wiki`
External dependency: `plastic-labs/honcho`
Review basis: full uploaded `_bmad-output` archives for Homefront and LLM-Wiki

---

## 1. Decision

Homefront, Honcho, and LLM-Wiki must use a shared object model and clear ownership boundaries.

**Homefront remains the household operating runtime.**
**Honcho owns conversational/profile memory.**
**LLM-Wiki owns governed structured facts and knowledge.**

Do not collapse Homefront into Honcho. Do not treat LLM-Wiki as a dumb key/value cache. Do not let Homefront duplicate canonical memory or canonical knowledge.

---

## 2. Naming Model

Use Honcho-aligned names in the technical contract.

| Contract Object | Meaning | Homefront UX Language | Honcho Mapping | LLM-Wiki Mapping |
|---|---|---|---|---|
| `Workspace` | Top-level isolated household/cell boundary | Household | `workspace` / `workspace_id` | `workspace_id` |
| `Peer` | Human, assistant, pet proxy, support/operator, or system participant | Person / assistant / support user | `peer` / `peer_id` | `peer_id` where personal scoping is needed |
| `AssistantPeer` | AI assistant assigned to a person/profile | Personal assistant | peer representing assistant | optional source/observer peer |
| `Session` | Conversation, routine run, voice interaction, or support interaction context | Chat / routine run / voice session | `session` / `session_id` | source/session provenance |
| `Message` | Atomic utterance, event, or interaction record written to memory | Message/event | `message` | source material if harvested |
| `Fact` | Deterministic structured knowledge item used by routines/simulation/policy context | Household fact | not canonical | canonical LLM-Wiki exact fact |
| `Page` | Governed markdown/wiki knowledge artifact | Knowledge page/document | optional uploaded context only | canonical wiki/document artifact |
| `ContextSnapshot` | Point-in-time assembled context for assistant/simulation | Routine context | may include Honcho representation/context | may include fact versions and query results |

### Required ID Names

Use these names in contracts and new code:

```text
workspace_id
peer_id
assistant_peer_id
session_id
message_id
fact_key
fact_version
context_snapshot_id
```

Homefront may keep the word **Household** in user-facing UI and product copy. New technical contracts should prefer `Workspace`. Existing `household_id` fields should be treated as legacy aliases for `workspace_id` until migrated.

---

## 3. Ownership Boundaries

### 3.1 Homefront Owns Runtime Authority

Homefront owns:

- workspace/cell provisioning and isolation
- profile/peer registry and role mapping
- assistant assignment and assistant permission boundaries
- rules, policies, approvals, action risk evaluation
- routines, routine definitions, routine runs, prompt state, escalation state
- Home Assistant, room-node, calendar, voice, and notification orchestration
- activity ledger, action ledger, audit records, correction records
- support-access grants, redacted diagnostics, control-plane metadata
- context snapshot assembly and visibility filtering

Homefront must **not** own:

- canonical long-term conversational memory
- canonical stable household facts
- unmanaged broad semantic knowledge search internals
- unfiltered memory/knowledge exposure to assistants

### 3.2 Honcho Owns Memory

Honcho owns:

- peer/session/message memory
- profile/assistant representations
- peer cards
- session context/summaries
- conclusions derived from conversation and events
- memory search over messages/conclusions
- durable cross-session conversational continuity

Honcho must **not** own:

- Homefront policy decisions
- action authorization
- routine state
- canonical household facts
- device/integration side effects
- approval routing

Homefront may ask Honcho for memory/context. Homefront must still filter the output by policy before it reaches an assistant or UI.

### 3.3 LLM-Wiki Owns Facts and Governed Knowledge

LLM-Wiki owns:

- deterministic structured facts
- fact history/versioning
- fact source/provenance/confidence/status
- exact fact reads for routines and simulation
- governed pages/documents
- source ingestion
- contradiction/staleness/review queues
- knowledge search/query over pages and facts
- exports for AI and user portability

LLM-Wiki must **not** own:

- Homefront action policy
- live routine execution
- profile authorization
- household action ledger
- Honcho-style profile memory

### 3.4 pgvector / Retrieval Indexing

Homefront BMAD artifacts currently keep pgvector as a cell-local retrieval/indexing layer. This should be narrowed.

For the next course correction:

- Homefront should not introduce pgvector as a product memory layer.
- Homefront should not introduce pgvector as a duplicate LLM-Wiki knowledge layer.
- Homefront may keep pgvector only for Homefront-owned artifacts if a later story proves a concrete need.
- Honcho search covers memory.
- LLM-Wiki search covers facts, pages, documents, and knowledge.

---

## 4. Deployment and Isolation

Each production family workspace runs as an isolated cell. The cell contains:

```text
Homefront cell runtime
Homefront cell Postgres
Honcho service
LLM-Wiki service
NATS / Hatchet / runtime dependencies
Home Assistant / room-node integrations as configured
```

Control plane contains only:

- account metadata
- workspace deployment metadata
- entitlements/billing
- version/update state
- redacted health
- support grants and redacted support bundle metadata

Raw transcripts, private memory, child data, integration credentials, raw action history, and routine content stay inside the workspace cell by default.

---

## 5. Homefront ↔ Honcho Contract

### 5.1 Mapping

```text
Homefront Workspace      -> Honcho workspace
Homefront Human Peer     -> Honcho peer
Homefront AssistantPeer  -> Honcho peer
Homefront interaction    -> Honcho session
Homefront utterance/event-> Honcho message
```

Recommended ID format:

```text
workspace_id = "homefront:{uuid}"
peer_id = "peer:{profile_uuid}" | "assistant:{assistant_uuid}" | "support:{support_uuid}" | "system:{name}"
session_id = "{surface}:{workspace_id}:{context_id}"
```

Examples:

```text
workspace_id = homefront:0190013f-d3b5-7c3a-824b-324df12a76f2
peer_id = peer:marc
assistant_peer_id = assistant:vera-marc
session_id = routine-run:homefront:0190013f:run-2026-05-26-morning
session_id = voice-room:homefront:0190013f:office:2026-05-26
```

### 5.2 Write Path

Homefront writes to Honcho after interactions and significant runtime events.

Memory writes are normally non-blocking:

```text
User/assistant interaction completes
→ Homefront persists operational result/ledger
→ Homefront submits memory message/event to Honcho
→ Failure is logged and counted
→ Repeated failure creates an integration_warning ledger record
```

Memory write failures must not block normal low-risk interaction completion unless the user explicitly requested memory export/delete/review behavior that requires Honcho availability.

### 5.3 Read Path

Use reads differently by latency need:

| Need | Preferred Honcho Surface |
|---|---|
| Low-latency prompt hydration | representation / peer card / bounded session context |
| “What do you remember about me?” | peer chat / conclusions |
| Search prior interactions | memory/message search |
| Export/delete | explicit export/delete wrapper in Homefront |

### 5.4 Safety Rules

- Honcho memory may inform assistant context.
- Honcho memory must not directly authorize actions.
- Policy decisions use Homefront operational state, rules, roles, approvals, and deterministic facts.
- Assistant proposals using Honcho context must still go through Homefront policy evaluation before side effects.
- Child/private memory must never be exposed across peers without explicit policy permission.

---

## 6. Homefront ↔ LLM-Wiki Contract

LLM-Wiki must expose two separate surfaces:

1. **Exact Structured Facts API** — deterministic, versioned, policy/simulation-safe.
2. **Knowledge API** — semantic/generative/governed wiki search, ingestion, review, and exports.

### 6.1 Exact Facts API

Required REST endpoints:

```http
GET    /v1/workspaces/{workspace_id}/facts
GET    /v1/workspaces/{workspace_id}/facts/{fact_key}
PUT    /v1/workspaces/{workspace_id}/facts/{fact_key}
DELETE /v1/workspaces/{workspace_id}/facts/{fact_key}
GET    /v1/workspaces/{workspace_id}/facts/{fact_key}/history
POST   /v1/workspaces/{workspace_id}/facts:batch
```

Optional MCP tools:

```text
fact_get
fact_list
fact_put
fact_delete
fact_history
fact_batch_put
```

### 6.2 Fact Schema

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
    session_id: str | None = None
    message_id: str | None = None
    page_id: str | None = None
    excerpt: str | None = None
    captured_at: datetime | None = None
```

### 6.3 Fact Write Request

```python
class KnowledgeFactWriteRequest(BaseModel):
    category: str
    key: str
    value: dict[str, Any]
    source: KnowledgeSource
    provenance: list[ProvenanceRef] = []
    confidence: float | None = None
    visibility: str = "workspace"
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    expected_previous_version: int | None = None
    expected_previous_updated_at: datetime | None = None
```

### 6.4 Fact Write Response

```python
class KnowledgeFactWriteResponse(BaseModel):
    key: str
    status: Literal[
        "written",
        "unchanged",
        "stale_rejected",
        "pending_review",
        "conflict_detected",
    ]
    fact: KnowledgeFact | None = None
    conflict: KnowledgeConflict | None = None
```

### 6.5 Category Registry

Initial Homefront categories:

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

Legacy aliases that must be accepted during transition:

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

Homefront should validate categories before calling LLM-Wiki and return:

```json
{
  "code": "unknown_knowledge_category",
  "message": "The category '[X]' is not a recognized knowledge category",
  "details": {
    "category": "[X]",
    "valid_categories": ["..."]
  }
}
```

### 6.6 Conflict and Review Behavior

LLM-Wiki must not silently pick a value when two authoritative sources conflict.

Possible fact read response for a conflict:

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

Homefront simulation must treat conflicted deterministic facts as unresolved unless a policy explicitly allows fallback behavior.

### 6.7 Knowledge API

Required endpoints:

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

This surface may use existing LLM-Wiki page/domain/search/query/export capabilities, but must be scoped by `workspace_id`.

### 6.8 Exact Facts vs Semantic Knowledge

| Use Case | Allowed Source |
|---|---|
| Routine simulation condition | Exact fact API only |
| Policy precondition | Exact fact API and Homefront state only |
| Assistant explanation | Exact facts + knowledge query + Honcho memory, all visibility-filtered |
| “What do we know about X?” | LLM-Wiki knowledge query |
| “What did I say last time?” | Honcho |
| Imported manual/warranty/school document | LLM-Wiki page/document layer |
| Stable recurring responsibility | LLM-Wiki fact |
| Personal preference learned from conversation | Honcho memory, optionally promoted to LLM-Wiki only after confirmation/review |

---

## 7. Context Snapshot Contract

Homefront owns context snapshot assembly.

```python
class ContextSnapshot(BaseModel):
    id: str
    workspace_id: str
    requester_peer_id: str
    assistant_peer_id: str | None
    session_id: str | None
    purpose: Literal[
        "assistant_interaction",
        "routine_simulation",
        "live_routine_run",
        "what_happened_explanation",
        "support_diagnostic",
    ]

    operational_state: dict[str, Any]
    policy_context: dict[str, Any]
    honcho_context: HonchoContext | None
    facts: list[KnowledgeFactSnapshot]
    knowledge_results: list[KnowledgeResult] = []
    integration_states: list[IntegrationStateSnapshot]
    degraded_signals: list[DegradedContextSignal]
    influence_refs: list[InfluenceRef]

    created_at: datetime
```

```python
class KnowledgeFactSnapshot(BaseModel):
    key: str
    category: str
    value: dict[str, Any] | None
    version: int | None
    status: str
    source: str
    visibility: str
    degraded: bool = False
```

```python
class DegradedContextSignal(BaseModel):
    source: Literal[
        "honcho",
        "llm_wiki",
        "google_calendar",
        "home_assistant",
        "voice",
        "notification",
        "workflow",
    ]
    severity: Literal["info", "warning", "blocking"]
    message: str
    retryable: bool
    occurred_at: datetime
```

### Snapshot Rules

- Snapshot assembly is point-in-time.
- No live queries during simulation after snapshot is built.
- All unavailable sources produce `DegradedContextSignal`, not unhandled 500 errors.
- Fact versions used in a simulation must be recorded.
- Memory/knowledge influence must be logged without leaking protected content.

---

## 8. Promotion from Memory to Knowledge

Conversation-derived memory can become a stable fact only through a promotion path.

```text
User says a durable household fact
→ Homefront writes conversation to Honcho
→ Assistant proposes fact candidate
→ Homefront classifies risk/sensitivity
→ LLM-Wiki writes pending_review or active fact based on policy
→ Homefront logs influence/change event
```

Rules:

- Assistant-suggested facts that affect children, safety, schedules, locks, alarms, cameras, privacy, purchases, credentials, integrations, or external communications require adult/admin confirmation.
- Low-risk facts may be stored as `pending_review` or `active` depending workspace policy.
- Conflicting facts must go to LLM-Wiki conflict/review state.
- Honcho conclusions harvested by LLM-Wiki must be treated as source material, not automatic truth.

---

## 9. Export and Delete Contract

### 9.1 Profile/Peer Export

Homefront export bundle for a peer/profile must include:

```json
{
  "schema_version": "homefront-export-v1",
  "workspace_id": "...",
  "peer_id": "...",
  "generated_at": "...",
  "honcho": {
    "sessions": [],
    "messages": [],
    "representations": [],
    "conclusions": []
  },
  "llm_wiki": {
    "facts": [],
    "pages": [],
    "provenance": []
  },
  "homefront": {
    "profile_settings": {},
    "routine_assignments": [],
    "ledger_refs": []
  }
}
```

### 9.2 Delete

- Honcho peer/session data is hard-deleted after optional export.
- LLM-Wiki profile-private facts/pages are hard-deleted or tombstoned according to visibility and audit policy.
- Shared facts are not deleted merely because one peer/profile is deleted unless the fact is explicitly profile-private.
- Deletion must be explainable through Homefront audit/ledger metadata.
- If Honcho or LLM-Wiki is unavailable during export, Homefront must fail with a clear 503 and must not produce an incomplete export that looks successful.

---

## 10. Readiness Gates

Do not call the system ready for family rollout until these are true:

### Office Pilot Gate

- One adult user in one room/office.
- Full voice/chat/PWA interaction for routine-adjacent requests.
- Honcho write/read works or degrades visibly.
- LLM-Wiki facts write/read works or degrades visibly.
- No silent high-risk action execution.
- Activity ledger shows policy, memory/fact influence, degraded integrations, and assistant proposals.

### Family Production Rollout Gate

- Multiple peers, including children, are safe.
- Voice identity is not sole authorization.
- Unknown speakers default to limited guest mode.
- Adults can review memory/facts/influence.
- Facts used by routines are deterministic and versioned.
- Context snapshots are policy-filtered.
- Notifications are relevant by location/context.
- “What happened?” explanation works for failed or degraded runs.
- Redaction and support boundaries are enforced.
- Wife/kids can use the system without understanding internals.

Do not use `MVP` as the readiness frame for this product. Use `Office Pilot` and `Family Production Rollout`.

---

## 11. Required BMAD Course Corrections

### Homefront

1. Rename technical contracts from `household_id` to `workspace_id`, with migration aliases.
2. Revise ADR-014 around Workspace/Peer/Session/Message/Fact/Page.
3. Rewrite LLM-Wiki integration spec to this contract.
4. Rewrite Honcho integration spec to Honcho V3 naming.
5. Rewrite Epic 5 so:
   - Honcho = profile/assistant/session memory.
   - LLM-Wiki = stable routine facts and governed knowledge.
   - Homefront = context assembler and policy runtime.
6. Replace `MVP`, `Phase 1`, and rough partial-release language with `Office Pilot` and `Family Production Rollout`.
7. Add stories for fact promotion, conflict review, scoped export/delete, and influence visibility.

### LLM-Wiki

1. Add Homefront-compatible Workspace/Fact API.
2. Add `workspace_id` scoping independent from page domains.
3. Add exact fact storage/history/versioning.
4. Preserve existing page/domain/wiki behavior as the knowledge layer.
5. Add fact conflict/review status.
6. Update Honcho bridge docs to clarify push/pull is source/context integration, not runtime authority.
7. Add contract tests for Homefront exact facts API.

---

## 12. Non-Goals

- Do not build a top-level controller/conductor AI above users.
- Do not put raw private household data in the control plane by default.
- Do not use Honcho memory as policy authority.
- Do not use semantic search as deterministic routine truth.
- Do not create a Homefront `household_facts` mirror table.
- Do not expose LLM-Wiki personal domains as a security boundary; Homefront enforces authorization.
- Do not launch family-wide until the Family Production Rollout gate is met.

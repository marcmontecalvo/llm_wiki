# Homefront BMAD Course Correction — Memory / Knowledge / Workspace Contract

Status: input for `/bmad-correct-course` or equivalent BMAD change workflow
Repo: `marcmontecalvo/Homefront`
Basis: full uploaded `_bmad-output` archive review

---

## Problem

Homefront planning and implementation artifacts evolved over multiple passes and no longer line up cleanly with the target memory/knowledge architecture.

The main inconsistencies are:

1. Technical contracts use `household_id` everywhere, while the stack should align with Honcho-style `workspace_id`.
2. Honcho naming is mixed: older Homefront stories use `app_id` / `user_id`, while Honcho V3 uses `workspace` / `peer` / `session` / `message`.
3. LLM-Wiki is specified by Homefront as a structured facts API, but LLM-Wiki's own BMAD artifacts and implementation focus on domains/pages/query/search/export.
4. Epic 5 currently treats too many stable facts as Honcho-backed “memory.”
5. Some artifacts still use `MVP`, `Phase 1`, and “founder household live-use validation” language. The product target is not a rough MVP. It is an office pilot followed by polished family production rollout.
6. pgvector appears in older memory/knowledge planning as a retrieval/indexing layer, but it should not become a third product memory/knowledge source during the family rollout path.

---

## Required Direction

Adopt the shared contract:

- `Workspace` = technical top-level isolated cell/household boundary.
- `Peer` = human, assistant, support/operator, or system participant.
- `Session` = chat, voice, routine run, support session, or other interaction context.
- `Message` = atomic memory/event unit.
- `Fact` = deterministic structured fact owned by LLM-Wiki.
- `Page` = governed markdown/wiki/document knowledge owned by LLM-Wiki.
- `ContextSnapshot` = point-in-time Homefront-assembled context packet.

Homefront may still use “household” in UI copy. New technical contracts should use `workspace_id`; old `household_id` is a compatibility alias.

---

## Architecture Corrections

### Homefront remains runtime authority

Homefront owns:

- workspace/cell isolation
- profiles/peers and roles
- assistant assignment and permission boundaries
- policy/rule evaluation
- approvals
- routine definitions/runs/prompts/escalations
- device/integration side effects
- activity/action ledger
- context snapshot assembly
- support/redaction boundaries

### Honcho owns conversational memory

Honcho owns:

- peer/session/message memory
- profile/assistant representations
- session context
- conclusions
- memory search

Honcho does not authorize actions.

### LLM-Wiki owns deterministic facts and governed knowledge

LLM-Wiki owns:

- stable facts
- fact version/history/conflict/review status
- governed pages/documents
- source/provenance/confidence
- knowledge search/query/export

LLM-Wiki does not run Homefront policy or routines.

---

## Replace Readiness Language

Replace:

- MVP
- Phase 1
- founder household live-use validation
- “minimal” in the sense of rough/incomplete

With:

- Office Pilot
- Family Production Rollout
- home-production-ready
- family-safe
- polished enough for daily household use

Office Pilot is a narrow deployment scope, not a reduced quality bar.

---

## Required Planning Doc Changes

### 1. Revise ADR-014

Create or update ADR:

```text
docs/adrs/ADR-014-memory-knowledge-and-retrieval-revised.md
```

Required changes:

- Rename technical object model around Workspace/Peer/Session/Message/Fact/Page.
- Clarify that Homefront UI may say Household, but technical contracts use Workspace.
- Keep Homefront as context assembler and policy runtime.
- Remove/soften pgvector as a required MVP/family-rollout retrieval layer.
- State pgvector is optional/deferred for Homefront-owned artifacts only.
- State Honcho search covers memory and LLM-Wiki search covers knowledge.
- State stable routine facts belong in LLM-Wiki, not Honcho.

### 2. Replace LLM-Wiki integration spec

Update:

```text
docs/integrations/llm-wiki.md
```

Required changes:

- Replace `/knowledge/{household_id}` with `/v1/workspaces/{workspace_id}/facts`.
- Keep aliases for old `household.*` category keys during transition.
- Add fact schema:
  - `workspace_id`
  - `category`
  - `key`
  - `value`
  - `source`
  - `provenance`
  - `confidence`
  - `authority_score`
  - `status`
  - `visibility`
  - `valid_from`
  - `valid_until`
  - `version`
- Add conflict/review behavior.
- Add fact history endpoint.
- Add deterministic exact-fact vs semantic knowledge separation.
- Preserve “no Homefront mirror table” rule.

### 3. Create Honcho integration spec

Create:

```text
docs/integrations/honcho.md
```

Required content:

- Honcho V3-style mapping:
  - Homefront Workspace → Honcho workspace
  - Homefront Peer → Honcho peer
  - AssistantPeer → Honcho peer
  - Interaction/routine/voice context → Honcho session
  - Utterance/event → Honcho message
- Non-blocking write behavior.
- Read behavior by latency:
  - representation/peer card for fast prompt hydration
  - search/chat/conclusions for deeper memory retrieval
- Export/delete behavior.
- Explicit statement that Honcho memory cannot authorize side effects.

### 4. Update PRD / Epics terms

Update PRD and Epics to align terms:

- FR1 can remain user-facing household creation, but add technical `Workspace`.
- FR53–FR63 need correction:
  - profile-scoped conversational memory → Honcho
  - shared routine conversation memory → Honcho only when it is truly memory
  - stable recurring routine facts → LLM-Wiki exact facts
  - assistant context pipeline → Homefront context snapshot assembler
  - retrieval boundaries → Honcho memory search + LLM-Wiki knowledge search; Homefront pgvector deferred unless proven

---

## Epic/Story Corrections

### Epic 3 Corrections

#### Story 3.2 — Replace with Workspace Facts Contract

Rewrite Story 3.2 around:

- `workspace_id`, not `household_id`.
- LLM-Wiki exact fact API.
- Fact version/history/conflict/review states.
- Strict category registry with `workspace.*` categories and `household.*` aliases.
- No Homefront mirror table.
- Graceful degraded context behavior.

Acceptance criteria should include:

1. Homefront can read/write exact facts through LLM-Wiki `/v1/workspaces/{workspace_id}/facts`.
2. Homefront rejects unknown categories before calling LLM-Wiki.
3. Fact read response includes version/status/source/provenance/visibility.
4. Conflicted facts produce unresolved/degraded simulation state.
5. LLM-Wiki unavailability creates `DegradedContextSignal(source="llm_wiki")`.
6. No Homefront migration may add a facts mirror table.

#### Story 3.3 — Rewrite Honcho Mapping to V3 Terms

Current story is directionally right, but old `app_id/user_id` terms and stub endpoints must be removed.

Use:

- `workspace_id`
- `peer_id`
- `assistant_peer_id`
- `session_id`
- `message_id`

Acceptance criteria should include:

1. Each Homefront workspace maps to an isolated Honcho workspace.
2. Each human profile maps to a Honcho peer.
3. Each assistant maps to a Honcho peer.
4. Sessions are scoped to interaction/routine/voice/support context.
5. Memory writes are non-blocking and failure-counted.
6. Memory reads are policy-filtered before prompt injection.
7. Honcho memory is never policy authority.

#### Story 3.13 — Rename Household Facts to Workspace Facts Internally

Keep UI label “Household Facts” if desired, but implementation uses Workspace Facts.

Add:

- fact conflict display
- fact source/provenance display
- fact version/history display
- workspace.* category mapping
- adult confirmation for assistant-suggested sensitive facts

### Epic 5 Corrections

Epic 5 should be reframed as:

```text
Epic 5: Context, Memory, and Knowledge Assembly
```

Replace current story intent:

- Do not say stable routine facts are stored as Honcho memory.
- Do not say shared deterministic facts are Honcho shared memory.
- Separate conversational memory from deterministic facts.

Recommended story set:

#### 5.1 Profile and Assistant Memory with Honcho

- Profile/assistant conversation memory.
- Peer/session/message mapping.
- Fire-and-forget writes.
- Fast context reads.
- Cross-peer permission filtering.

#### 5.2 Shared Session Memory with Honcho

- Shared routine/run conversation context only.
- Not stable household facts.
- Used for “what happened in this run/session,” not “what is the dishwasher rotation?”

#### 5.3 Stable Workspace Facts with LLM-Wiki

- Recurring routine facts.
- Pets, dishwasher rotation, wake/departure times, vehicles, responsibilities.
- Fact versioning/history.
- Provenance/confidence/status.
- Conflict handling.

#### 5.4 Fact and Memory Review

- Unified admin review surface.
- Separate tabs/sections:
  - Honcho memory
  - LLM-Wiki facts
  - LLM-Wiki pages/documents
  - influence records
- Permissions/redaction enforced.

#### 5.5 Influence Tracking

- Tracks when memory/facts/calendar/integration/policy influenced an outcome.
- Stores references and summaries, not protected raw content.

#### 5.6 Context Snapshot Assembler

- Builds policy-filtered point-in-time context packets.
- Reads:
  - Homefront operational state
  - Honcho representations/context
  - LLM-Wiki exact facts
  - optional LLM-Wiki knowledge query results
  - integration state
  - policy constraints
- Produces degraded signals and influence refs.

#### 5.7 Future Retrieval Boundary

- Keeps Homefront pgvector deferred.
- Defines where retrieval can attach later without becoming a second source of truth.

### Epic 6 Corrections

Story 6.10 should explicitly reference:

- Honcho memory influence
- LLM-Wiki fact influence
- LLM-Wiki knowledge/page influence
- Calendar/integration/policy influence
- unauthorized redaction behavior

### Epic 7 Corrections

Update user-facing language so adults/kids do not see internal names:

- UI says Household, Family, Assistant, Memory, Facts.
- Technical docs/contracts say Workspace/Peer/Session/Fact/Page.

Add notification relevance to context rules:

- location at office vs home
- driving/on-route notifications
- no irrelevant appliance noise when away
- explain why a notification was sent

---

## BMAD Story Creation Prompt

Use this prompt inside the Homefront repo with the appropriate BMAD course-correction skill:

```text
Run BMAD Correct Course for Homefront.

We need an immediate architecture and epic/story correction for the memory/knowledge stack.

Use the uploaded/shared contract:
Homefront / Honcho / LLM-Wiki Shared Memory + Knowledge Contract v1.

Do not implement code.

Update planning artifacts and create/revise stories so Homefront uses:
- Workspace as the technical tenant/cell object, with Household retained only as user-facing language.
- Peer, AssistantPeer, Session, Message, Fact, Page, and ContextSnapshot as shared object names.
- Honcho for conversational/profile/assistant/session memory only.
- LLM-Wiki for deterministic structured facts and governed knowledge.
- Homefront as the policy/runtime/context-snapshot authority.
- No Homefront facts mirror table.
- No Honcho memory as policy authority.
- No semantic search as deterministic routine truth.
- No MVP/rough partial-release language. Replace with Office Pilot and Family Production Rollout readiness gates.

Required outputs:
1. Revised ADR-014.
2. Updated docs/integrations/llm-wiki.md.
3. New docs/integrations/honcho.md.
4. Updated PRD terminology where needed.
5. Updated epics.md, especially Epic 3 and Epic 5.
6. Updated implementation artifacts for affected stories.
7. A concise change log listing every artifact changed and why.

Do not stop until planning docs and story artifacts are internally consistent.
```

---

## Acceptance Criteria for the Course Correction

- All new technical contracts use `workspace_id`.
- Existing `household_id` is documented as a migration/compatibility alias only.
- Honcho stories use Workspace/Peer/Session/Message terminology.
- LLM-Wiki stories use Workspace/Facts/Pages terminology.
- Stable routine facts are assigned to LLM-Wiki, not Honcho.
- Context snapshot assembly is owned by Homefront.
- Family Production Rollout readiness is explicit.
- Office Pilot is documented as a narrow test gate, not a lower quality bar.
- Epics and implementation artifacts no longer contradict ADR-014.

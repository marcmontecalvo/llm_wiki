# Sprint Change Proposal — Homefront Integration Course Correction

**Date:** 2026-05-26
**Author:** Marc (trigger) + AI assistance
**Classification:** Major — Fundamental replan with PM/Architect involvement
**Trigger:** `docs/contracts/homefront-llm-wiki-honcho-shared-contract-v1.md` and associated correction documents

---

## Section 1: Issue Summary

LLM-Wiki was originally scoped and planned as a daemon-governed page/domain/wiki search service — useful for agent harnesses that need structured knowledge. However, the Homefront integration has revealed that LLM-Wiki serves a fundamentally different primary role:

**LLM-Wiki must be a structured exact facts service + governed wiki knowledge service.**

Homefront requires deterministic, versioned, categorized facts scoped by workspace for routine execution, simulation, and policy decisions. The current LLM-Wiki artifacts describe a page/wiki/search service with domain-scoped markdown pages. These are complementary layers, not a replacement.

The shared contract (`docs/contracts/homefront-llm-wiki-honcho-shared-contract-v1.md`) defines a 3-layer architecture:
- **Homefront**: household operating runtime (policy, routines, context assembly)
- **Honcho**: conversational/profile memory (sessions, messages, peer cards)
- **LLM-Wiki**: deterministic structured facts + governed wiki knowledge (facts, pages, provenance)

This is not a bug fix or feature addition — it is a strategic pivot that affects the PRD, architecture, epics, naming model, and product readiness language.

---

## Section 2: Impact Analysis

### Epic Impact

| Epic | Impact | Required Change |
|------|--------|-----------------|
| Epic 1 (Docker Service) | Minor | Integrate workspace facts into the service layer; add facts API routes alongside existing wiki routes; add workspace directory layout |
| Epic 2 (Trust & Verification) | Minor-Moderate | Trust tags apply to both facts and pages; fact confidence is a first-class field |
| Epic 3 (Cross-Domain) | Minor | Knowledge search API must be workspace-scoped; domain remains categorization only |
| Epic H (Honcho Integration) | **Major** | Rewrite to clarify Honcho = memory, not facts; push/pull are source/context bridge, not runtime authority |
| **Epic HF (NEW: Homefront Integration)** | **New** | 7 stories: Workspace Facts API, storage/history, category registry, conflict/review, contract tests, workspace-scoped knowledge, export/delete |

### Artifact Conflicts

| Artifact | Conflict | Resolution |
|----------|----------|------------|
| PRD | No `workspace_id` concept; no Fact model; no category registry | Add facts section, workspace scoping, rename `household_id` → `workspace_id` |
| PRD | Uses `MVP`, `Phase 1`, `Sprint 1-4` | Replace with `Office Pilot`, `Family Production Rollout` |
| Architecture | No 3-layer model (Homefront/Honcho/LLM-Wiki) | Add ownership boundaries, file-backed facts storage layout |
| Architecture | Domain described as isolation boundary in parts | Clarify domain = categorization; workspace = isolation |
| Epics | Epic H conflates Honcho memory with facts | Correct to memory-only; add new HF epic |
| Epics | No structured facts API stories | Add HF.1-HF.7 |
| Sprint Status | No entries for HF epic | Add HF epic with stories HF.1-HF.7 |

### Technical Impact

- New REST endpoints under `/v1/workspaces/{workspace_id}/facts`
- New MCP tools: `fact_get`, `fact_list`, `fact_put`, `fact_delete`, `fact_history`, `fact_batch_put`
- New Knowledge API endpoints workspace-scoped
- New Fact model (Python Pydantic)
- New file-backed facts storage layout alongside existing wiki layout
- Category registry with canonical `workspace.*` and legacy `household.*` aliases
- Conflict detection at fact level (separate from page-level contradiction detection)
- Contract test harness for Homefront integration

---

## Section 3: Recommended Approach

**Selected:** Direct Adjustment + PRD Scope Correction

**Rationale:**
- Existing LLM-Wiki wiki/search/export/inject/governance work is **not thrown away** — it becomes the knowledge layer
- The workspace facts API is a **complementary layer** — facts are structured key/value; pages are markdown wiki documents
- File-backed storage is preserved (no database requirement)
- The pivot aligns LLM-Wiki with the shared contract without requiring a complete rebuild

**Timeline impact:** Adding Epic HF introduces an additional implementation phase beyond the original 4-step plan. The exact stories (HF.1-HF.7) are not yet assessed for story point sizing, but they are well-defined in the contract documents.

**Risk:**
- Medium — the interface change between services (Homefront → LLM-Wiki) is the risk surface, not internal LLM-Wiki rework
- Existing wiki infrastructure (governance, search, exports) is preserved and unaffected
- Honcho bridge clarification (Epic H correction) is low effort once Epic HF is defined

---

## Section 4: Detailed Change Proposals

### 4.1 PRD Changes

**Add new section: "Homefront Integration — Workspace Facts"** (after "AI Backend Specific Requirements")

The PRD must include:
- `workspace_id` as the top-level isolation object (replace `household_id` with migration aliases)
- Fact model: `KnowledgeFact` with category, key, value, source, provenance, confidence, authority_score, status, visibility, version, timestamps
- Exact Facts API: CRUD endpoints under `/v1/workspaces/{workspace_id}/facts`
- Category registry with canonical `workspace.*` names and legacy `household.*` aliases
- Conflict and review behavior at fact level
- Honcho bridge clarification: push/pull are source/context integration only
- Export/delete contract aligned with Homefront profile export schema
- Readiness gates: Office Pilot and Family Production Rollout

**Replace throughout:**
- `MVP` → `Office Pilot` (where referring to readiness, not defining MVP scope)
- `Phase 1` / `Phase 2` → `Office Pilot` phase / `Family Production Rollout` phase
- `founder household live-use validation` → `Office Pilot validation`

### 4.2 Architecture Changes

**Add new section: "Three-Layer Architecture — Ownership Boundaries"**

```
┌──────────────────────────────────────────────────┐
│              Homefront Runtime                    │
│  - Workspace provisioning                         │
│  - Policies, rules, approvals                     │
│  - Routines, routine runs                         │
│  - Context snapshot assembly                      │
│  - Activity/action ledger                         │
└──────────┬───────────────────────┬────────────────┘
           │ asks Honcho           │ asks LLM-Wiki
           │ for memory            │ for facts + knowledge
           ▼                       ▼
┌─────────────────────┐  ┌────────────────────────┐
│    Honcho Memory     │  │   LLM-Wiki Facts       │
│ - Peer/session/msg   │  │ - Deterministic facts  │
│ - Profile cards      │  │ - Fact history/v1      │
│ - Conversational     │  │ - Source/provenance    │
│   continuity         │  │ - Conflict/review      │
│ - Memory search      │  │                        │
│                    │  │ ┌────────────────────────┐ │
│                    │  │ │ Page Knowledge Layer   │ │
│                    │  │ │ - Governed markdown    │ │
│                    │  │ │ - Search/query         │ │
│                    │  │ │ - Exports              │ │
└─────────────────────┘  └────────────────────────┘
```

**Add facts storage layout:**

```
wiki_system/
  workspaces/
    {workspace_id}/
      facts/
        index.json
        categories/
          workspace.pets.jsonl
          workspace.schedule.jsonl
        history/
          {fact_key_hash}.jsonl
      pages/          (existing wiki pages, workspace-scoped)
      inbox/
      exports/
```

**Add file-backed facts storage rules:**
- Current fact state is machine-readable without markdown parsing
- Fact history is append-only
- Writes use temp file + `os.replace` (atomic)
- Per-workspace/per-fact locks prevent concurrent write races
- Pages may reference facts but are not the canonical fact state

### 4.3 Epics Changes

**Add new Epic HF: Homefront Integration — "Deterministic Household Knowledge"**

A system of structured facts scoped by workspace, with history, conflict detection, and review behavior, so that Homefront can run simulations from deterministic knowledge and assemble policy-filtered context snapshots.

**Stories:**
- HF.1 — Workspace Facts API Foundation (REST + MCP)
- HF.2 — Workspace Fact Storage and History (file-backed, atomic, locked)
- HF.3 — Category Registry and Aliases
- HF.4 — Fact Conflict and Review Queue
- HF.5 — Homefront Contract Test Harness
- HF.6 — Workspace-Scoped Knowledge API
- HF.7 — Export/Delete for Homefront

**Correct Epic H:**
- Rename/move to "Honcho Bridge — Context Integration"
- Clarify that Honcho = memory only; facts belong in LLM-Wiki
- Push = export wiki knowledge to Honcho context; Pull = harvest Honcho conclusions as wiki source material
- No runtime authority, no fact authority, no policy authority

---

## Section 5: Implementation Handoff

**Scope Classification:** Major — Needs fundamental replan

**Handoff recipients:**

| Role | Responsibility |
|------|----------------|
| **Product Manager / Architect** | Review and validate all artifact changes; ensure internal consistency across PRD, architecture, and epics |
| **Product Manager** | Size the HF epic stories; determine ordering relative to existing epics; confirm Office Pilot gate feasibility |
| **Developer** | Implement epic stories in architectural order: foundation (HF.1, HF.2) → features (HF.3-HF.6) → contract validation (HF.5, HF.7) |

**Deliverables from this change:**
1. This Sprint Change Proposal (above)
2. Updated `prd.md` with facts API and corrected readiness language
3. Updated `architecture.md` with 3-layer model and facts storage layout
4. Updated `epics.md` with Epic HF and corrected Epic H
5. Updated `sprint-status.yaml` with new epic entries

**Success criteria for implementation:**
- LLM-Wiki exposes a complete workspace-facts API conforming to the shared contract
- Facts are distinct from pages — two surfaces with clear boundaries
- Workspace scoping is distinct from domain scoping
- Domain is categorization, NOT a security boundary
- Honcho bridge is source/context only, not authority
- Existing wiki/invoke/search/export functionality preserved and tested
- Contract tests verify Homefront-required endpoints

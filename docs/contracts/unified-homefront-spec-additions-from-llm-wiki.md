# Unified Homefront Spec Additions From LLM-Wiki Review

**Purpose:** unify the Codex and Claude Code recommendations for what Homefront should add or clarify based on LLM-Wiki's existing capabilities.

**Scope:** additions to the Homefront LLM-Wiki integration spec and adjacent Homefront memory/knowledge architecture. This is not a request to expand Phase 1 beyond the morning routine unless explicitly marked MVP-critical.

**Core tension:** Homefront currently treats LLM-Wiki mostly as a disciplined typed facts cache. LLM-Wiki is closer to a governed, searchable, provenance-aware knowledge base. Homefront should either intentionally narrow the contract to exact facts only or expand the spec enough to use the parts of LLM-Wiki that matter for household reliability.

---

## Decision summary

| Area | Recommendation | MVP-critical? |
|---|---|---|
| Exact facts vs search/query | Explicitly define two surfaces: exact facts for runtime truth, search/query for optional retrieval | Yes |
| Provenance/confidence/staleness | Add first-class metadata fields, not just `value.source` | Yes |
| Contradictions/authority | Define canonical vs conflicting fact behavior | Yes |
| Read-after-write/index freshness | Exact reads strong; search/query eventual with freshness metadata | Yes |
| Profile/visibility scoping | Add `profile_id`, `visibility`, and permission semantics where needed | Yes |
| History/changelog | Add history reads or write response diffs | Yes for facts affecting routines |
| Ingestion lifecycle | Add optional inbox/review path for unstructured/conversation-derived facts | Soon, likely post-initial wire-up |
| Review queue | Add `pending_review` result for low-confidence/contradictory facts | Soon |
| Archive/retention | Define soft-delete/archive behavior | Yes for deletion safety |
| Export/support diagnostics | Define Homefront-shaped redacted export schema | Yes |
| MCP/tool surface | Decide REST-only vs MCP/direct assistant access | Not Phase 1-critical, but must be explicit |
| Honcho ↔ LLM-Wiki direct link | Decide cell-mediated only vs direct sync | Yes as an architecture boundary |
| OTel/metrics | Require observability for LLM-Wiki integration health | Yes |
| Adapter framework | Plan future ingest adapters without bespoke one-offs | Post-MVP |

---

## 1. Split exact facts from search/query

### Current gap

Homefront's current spec focuses on exact fact reads/writes through `/knowledge/{household_id}`. LLM-Wiki already has query/search/page/synthesis capabilities. The spec does not say whether Homefront will use those capabilities or intentionally avoid them.

### Why it matters

The two use cases have different correctness requirements:

- Routine execution needs exact, strongly consistent facts.
- Assistant exploration can tolerate semantic search, ranked results, and eventual consistency.
- Troubleshooting can use both.

Conflating them risks making live routines depend on stale or approximate search results.

### Add to Homefront spec

Homefront should define two LLM-Wiki access modes:

#### A. Exact facts mode

Used for routine execution, simulation, policy-relevant context, and deterministic assistant context assembly.

Requirements:

- Strong read-after-write.
- Category/key validated.
- Typed JSON value.
- Conflict-aware writes.
- Household/profile/visibility enforcement.
- Safe deletion semantics.

#### B. Retrieval/search mode

Used for assistant context expansion, troubleshooting, discovery, and optional knowledge recall.

Requirements:

- May be eventually consistent.
- Must return confidence/provenance/freshness metadata.
- Must never override exact facts silently.
- Must be filtered by household/profile visibility.
- Must expose stale-index metadata.

Recommended spec language:

```md
Homefront treats LLM-Wiki exact facts and LLM-Wiki retrieval as separate surfaces. Exact facts may influence routine execution and simulation. Search/query results may enrich assistant context only when confidence, provenance, visibility, and freshness meet policy. Search/query results must not silently override exact facts or policy decisions.
```

---

## 2. Add first-class provenance

### Current gap

The example Homefront facts encode source as a free string inside `value`, for example:

```json
{
  "value": {
    "source": "google_calendar"
  }
}
```

That is too weak for trust, troubleshooting, review, and conflict resolution.

### Add to Homefront schema

Add a first-class `provenance` object:

```json
{
  "provenance": {
    "source_system": "google_calendar",
    "source_type": "integration",
    "source_event_id": "evt_123",
    "captured_at": "2026-05-26T08:00:00Z",
    "observed_at": "2026-05-26T07:55:00Z",
    "ingest_method": "calendar_sync",
    "created_by_profile_id": null,
    "reviewed_by_profile_id": "profile_marc",
    "reviewed_at": "2026-05-26T08:10:00Z",
    "trust_tag": "third_party_mirrored"
  }
}
```

Minimum fields:

- `source_system`
- `source_type`
- `captured_at`
- `observed_at`
- `ingest_method`
- `trust_tag`

Optional fields:

- `source_event_id`
- `source_url`
- `source_record_hash`
- `created_by_profile_id`
- `reviewed_by_profile_id`
- `reviewed_at`
- `import_batch_id`

### Recommended trust tags

- `admin_asserted`
- `user_asserted`
- `child_asserted`
- `integration_mirrored`
- `third_party_mirrored`
- `derived_from_conversation`
- `derived_from_routine`
- `system_inferred`
- `support_imported`

---

## 3. Add confidence, authority, and staleness

### Current gap

Homefront currently models `value` and `updated_at`, but not whether the fact is reliable, stale, inferred, reviewed, or contested.

### Why it matters

Households produce messy facts. Calendar, parent, child, assistant inference, and device state may disagree. A morning routine should not silently choose the last write when authority differs.

### Add to `KnowledgeEntry`

```json
{
  "confidence": 0.92,
  "authority_score": 0.85,
  "staleness": {
    "state": "fresh",
    "stale_after": "2026-06-26T00:00:00Z",
    "last_verified_at": "2026-05-26T00:00:00Z"
  },
  "review_state": "accepted"
}
```

Recommended enums:

```text
review_state:
  accepted
  pending_review
  rejected
  archived
  conflicted

staleness.state:
  fresh
  aging
  stale
  expired
  unknown
```

### Recommended authority order

Homefront should explicitly rank source authority by fact category. Example baseline:

1. Adult/admin direct edit.
2. Approved structured rule/routine setup.
3. Authoritative integration record, such as Google Calendar for schedule.
4. Adult participant assertion.
5. Device state or Home Assistant entity state.
6. Child assertion.
7. Conversation-derived inference.
8. Assistant/system inference.

This should be category-sensitive. For example, a user's own preference may outrank an admin's guess, while a lock/device state should outrank a stale conversation memory.

---

## 4. Define contradiction behavior

### Current gap

The spec assumes a fact has one value. LLM-Wiki has concepts around contradictions, authority, promotion, and confidence.

### Why it matters

Common household conflicts:

- Calendar says practice is Tuesday; parent says Wednesday.
- Kid says homework is done; school email suggests it is not.
- Home Assistant says garage is open; last routine fact says closed.
- One adult says dog food was bought; another adds it to errands.

### Add to spec

Define whether exact fact reads return:

1. only canonical value,
2. canonical value plus conflict metadata,
3. ranked candidate values,
4. or `409/conflicted` for certain categories.

Recommended default:

- Exact fact reads return a canonical value **plus conflict metadata** when conflicts exist.
- Policy/routine-critical facts with unresolved high-impact conflict should surface `review_state: conflicted` and require clarification/review before use.

Example:

```json
{
  "entry": {
    "category": "household.schedule",
    "key": "soccer.practice_time",
    "value": {
      "day": "Tuesday",
      "time": "18:00"
    },
    "review_state": "conflicted",
    "confidence": 0.61,
    "provenance": {}
  },
  "conflicts": [
    {
      "value": {
        "day": "Wednesday",
        "time": "18:00"
      },
      "source_system": "adult_manual_entry",
      "authority_score": 0.9,
      "observed_at": "2026-05-25T20:00:00Z"
    }
  ]
}
```

Recommended spec language:

```md
LLM-Wiki must not hide known contradictions for facts used in routine simulation, live execution, policy decisions, or assistant context. Reads may return a canonical value, but must include conflict metadata when material contradictions exist. Homefront policy decides whether to proceed, degrade, ask for clarification, or require adult/admin review.
```

---

## 5. Add profile, subject, and visibility scoping

### Current gap

The spec uses `household_id`, but household knowledge is not always household-wide. Facts may be profile-specific, child-private, adults-only, routine-specific, or subject-specific for pets/devices.

### Add fields

```json
{
  "profile_id": "profile_annabella",
  "subject_id": "pet_bailey",
  "routine_id": "morning_routine",
  "visibility": "adults_only",
  "audience": ["profile_marc", "profile_lisa"]
}
```

Recommended `visibility` enum:

```text
household
adults_only
profile_private
profile_managed_by_adult
routine_only
support_redacted
hidden
```

### Rules

- `household_id` is always required.
- `profile_id` is optional but required for profile-scoped facts.
- `subject_id` is optional for pets, appliances, rooms, vehicles, and devices.
- `visibility` is required.
- Homefront policy remains the final authority on whether a user can read/write/delete a fact.
- LLM-Wiki must preserve visibility metadata and enforce coarse read filters.

---

## 6. Add history/changelog reads

### Current gap

Homefront has `updated_at`, but not fact history. LLM-Wiki has changelog concepts.

### Why it matters

Routine simulation and troubleshooting need to answer:

- What did Homefront know at the time of the routine?
- Did a delayed write change what should have happened?
- Which value did a routine use?
- Who changed a fact that affected a child prompt or high-risk action?

### Add route

```text
GET /knowledge/{household_id}/{category}/{key}/history
```

Response:

```json
{
  "household_id": "founder-household",
  "category": "household.schedule",
  "key": "lisa.departure_time",
  "history": [
    {
      "version": 3,
      "value": {
        "time": "06:30"
      },
      "changed_at": "2026-05-26T08:00:00Z",
      "changed_by": "profile_marc",
      "change_reason": "routine_setup_edit",
      "provenance": {},
      "superseded_by": null
    }
  ]
}
```

### Add to write response

Every write response should include at least:

```json
{
  "entry": {},
  "previous_entry": {},
  "change_type": "created|updated|unchanged|rejected|pending_review|conflicted",
  "history_version": 3
}
```

---

## 7. Add ingest lifecycle for unstructured/conversation-derived facts

### Current gap

Homefront only specifies structured writes. LLM-Wiki's core strength is ingesting unstructured content, classifying it, deduping it, and promoting it into knowledge.

### Why it matters

Homefront's core interaction is natural household language. Users will say:

- "We got a new dishwasher."
- "Remember Vincenzo needs gym clothes every Wednesday."
- "Bailey's vet is now Southbay Animal Clinic."
- "Annabella rides with Lisa tomorrow."

Not every statement should become an auto-accepted exact fact. Some should become drafts, review items, conflicts, or ignored observations.

### Add route

```text
POST /knowledge/{household_id}/inbox
```

Request:

```json
{
  "text": "Remember Vincenzo needs gym clothes every Wednesday.",
  "context": {
    "source": "assistant_conversation",
    "requester_profile_id": "profile_marc",
    "assistant_id": "assistant_marc",
    "routine_id": "morning_routine"
  }
}
```

Response options:

```text
created
updated
pending_review
conflicted
ignored
failed
```

Example response:

```json
{
  "status": "pending_review",
  "review_item_id": "review_123",
  "proposed_entries": [
    {
      "category": "household.recurring_responsibilities",
      "key": "vincenzo.gym_clothes.wednesday",
      "value": {
        "item": "gym clothes",
        "day": "Wednesday"
      },
      "confidence": 0.78,
      "provenance": {}
    }
  ]
}
```

### Recommendation

Make this a **designed-for near-term surface**, not necessarily the first wire-up. Exact facts should land first; inbox/review should follow before broader live household learning.

---

## 8. Add review queue semantics

### Current gap

The current Homefront spec is binary: write succeeds or fails. LLM-Wiki has concepts for low confidence, duplicates, contradictions, stale content, and review queues.

### Add review state to writes

A write may return:

```text
accepted
pending_review
rejected
conflicted
duplicate
archived
```

### Add route

```text
GET /knowledge/{household_id}/review
POST /knowledge/{household_id}/review/{review_item_id}/approve
POST /knowledge/{household_id}/review/{review_item_id}/reject
```

### Homefront behavior

- Adult/admin UI can surface pending review items.
- Low-risk facts may be accepted automatically based on policy.
- Child-affecting, privacy-affecting, schedule-critical, and high-risk-action-related facts require stricter review.
- Review actions create activity/history records.

---

## 9. Add archive/retention lifecycle

### Current gap

The spec mentions deletion, but not retention, archival, soft-delete, stale facts, or historical visibility.

### Why it matters

Household facts decay:

- appliance replaced
- pet no longer present
- kid changes school
- vehicle sold
- recurring responsibility ended
- old routine retired

Hard deletion can break history and routine explanations.

### Add lifecycle fields

```json
{
  "lifecycle": {
    "state": "active",
    "archived_at": null,
    "archived_reason": null,
    "expires_at": null,
    "retention_policy": "household_default"
  }
}
```

Recommended states:

```text
active
stale
archived
soft_deleted
hard_deleted
expired
```

### Rules

- Default deletion is soft-delete/archive.
- Historical routine explanations can still reference archived facts.
- Search/query should exclude archived facts by default unless requested.
- Exact current-fact reads exclude soft-deleted facts by default.
- Support export must honor retention/redaction policy.

---

## 10. Add failed-ingest visibility

### Current gap

Homefront mentions activity ledger failures, but not LLM-Wiki's own failed ingest queue.

### Add route

```text
GET /knowledge/{household_id}/failed
```

Response:

```json
{
  "failed_items": [
    {
      "id": "failed_123",
      "source": "assistant_conversation",
      "received_at": "2026-05-26T08:00:00Z",
      "error_code": "invalid_category",
      "safe_summary": "Could not classify recurring clothing reminder.",
      "retryable": true
    }
  ]
}
```

### Use

- Admin troubleshooting.
- Support diagnostics.
- Recovery of malformed writes.
- Visibility into degraded knowledge ingestion.

---

## 11. Define support/export diagnostics

### Current gap

Homefront mentions redacted diagnostics. LLM-Wiki has export capabilities, but the Homefront-safe export shape is not defined.

### Add to spec

Define support export modes:

```text
profile_export
household_admin_export
support_redacted_bundle
full_household_backup
```

Each mode must state:

- allowed fields
- redaction behavior
- whether values are included
- whether provenance is included
- whether child/private facts are included
- whether archived/deleted facts are included
- who can request it
- whether explicit adult/admin permission is required

### Minimum support-redacted behavior

- Include counts, schema versions, category summaries, health/freshness status, failed ingest summaries, and error codes.
- Exclude raw private values unless explicitly permitted.
- Include safe hashes/IDs where useful for diffing.
- Include index freshness and degraded reasons.

---

## 12. Define MCP/direct assistant access stance

### Current gap

LLM-Wiki exposes or plans MCP/tool surfaces. Homefront spec is REST-oriented.

### Decision needed

Choose one:

#### Option A: Cell-mediated only

Assistants never call LLM-Wiki directly. They call Homefront cell APIs, and the cell runtime queries LLM-Wiki after policy/visibility checks.

Pros:

- simpler auth
- central policy enforcement
- easier audit
- safer for child/privacy boundaries

Cons:

- less direct use of LLM-Wiki MCP features

#### Option B: Direct assistant MCP access allowed

Assistants may call LLM-Wiki MCP with scoped credentials.

Pros:

- powerful tool interface
- closer to LLM-Wiki native design

Cons:

- more complex auth, policy, and audit
- higher risk of cross-profile leakage

### Recommendation

For Phase 1, choose **cell-mediated only**.

Spec language:

```md
Phase 1 assistants do not call LLM-Wiki directly. The household cell runtime mediates LLM-Wiki reads, writes, search, review, and export so policy, visibility, child boundaries, activity history, and support redaction remain centralized. Direct MCP access may be introduced later only with scoped credentials, policy enforcement, and audit parity.
```

---

## 13. Define Honcho ↔ LLM-Wiki sync stance

### Current gap

Homefront architecture treats Honcho and LLM-Wiki as parallel memory/knowledge layers mediated by the cell runtime. LLM-Wiki may support direct Honcho push/pull.

### Decision needed

Choose whether direct Honcho ↔ LLM-Wiki sync is allowed.

### Recommendation

For Phase 1, keep sync **cell-mediated only**.

Reasons:

- Homefront owns household/profile visibility policy.
- Honcho memory and LLM-Wiki facts have different trust/authority semantics.
- Direct sync could bypass activity ledger and policy decisions.
- Support diagnostics need one explanation path.

Spec language:

```md
In Phase 1, Homefront mediates all Honcho ↔ LLM-Wiki movement through the household cell runtime. LLM-Wiki must not directly import from or export to Honcho unless a future ADR defines policy, visibility, conflict, provenance, and audit behavior for that path.
```

---

## 14. Add observability/SLO requirements

### Current gap

Homefront describes degraded behavior, but not enough metrics to explain why LLM-Wiki is degraded.

### Add required metrics

LLM-Wiki integration should expose metrics via `/metrics` or OpenTelemetry:

- request count by route/status
- read latency
- write latency
- search/query latency
- timeout count
- conflict count
- stale update rejection count
- unknown category rejection count
- pending review count
- failed ingest count
- index freshness age
- last successful ingest/index time
- export generation count/failure
- circuit breaker state as observed by Homefront

### Add trace fields

- `request_id`
- `household_id`
- `cell_id`
- `operation`
- `category`
- `key_hash` or redacted key when needed
- `result`
- `degraded_reason`

Avoid raw private values in traces.

---

## 15. Add adapter/ingest framework boundary

### Current gap

Homefront has integrations such as Google Calendar, Home Assistant, room nodes, and future device/service connectors. LLM-Wiki can ingest multiple formats, but Homefront does not define whether LLM-Wiki owns adapter ingestion or receives already-normalized facts.

### Recommendation

For Phase 1:

- Homefront connectors normalize operational facts.
- LLM-Wiki stores accepted structured facts and optionally receives inbox candidates.
- LLM-Wiki does not directly connect to Google/Home Assistant unless a future spec defines that adapter boundary.

For future:

- Add adapter contracts for ICS, Home Assistant entity dumps, appliance data, school emails, documents, and transcript/session imports.
- Each adapter must produce provenance, confidence, authority, review state, and visibility metadata.

---

## 16. Add synthesized/snapshot reads

### Current gap

Homefront says snapshot assembly hits LLM-Wiki once. Returning every fact may be too broad as households grow. LLM-Wiki has synthesis concepts.

### Add routes

```text
GET /knowledge/{household_id}/snapshot
GET /knowledge/{household_id}/snapshot/{routine_id}
GET /knowledge/{household_id}/{category}
```

### Requirements

- Snapshot reads are prefiltered by use case.
- Include freshness metadata.
- Include conflicts/staleness indicators.
- Exclude facts not visible to the requesting profile/context.
- Exact facts remain the underlying authority.

Example:

```json
{
  "snapshot_type": "routine",
  "routine_id": "morning_routine",
  "generated_at": "2026-05-26T08:00:00Z",
  "entries": [],
  "warnings": [
    {
      "code": "conflicted_fact",
      "category": "household.schedule",
      "key": "soccer.practice_time"
    }
  ]
}
```

---

## 17. Add profile export schema

### Current gap

The spec mentions `llm_wiki: []` but does not define the shape.

### Add schema

```json
{
  "llm_wiki": [
    {
      "id": "uuid",
      "category": "household.preferences",
      "key": "profile_marc.coffee",
      "value": {},
      "profile_id": "profile_marc",
      "visibility": "profile_private",
      "confidence": 1.0,
      "review_state": "accepted",
      "provenance": {},
      "lifecycle": {},
      "created_at": "2026-05-26T08:00:00Z",
      "updated_at": "2026-05-26T08:00:00Z"
    }
  ]
}
```

Define whether values are included for:

- self profile export
- adult/admin household export
- child profile managed export
- support-redacted export

---

## 18. Recommended revised `KnowledgeEntry`

This combines the highest-value additions without making the initial contract too broad.

```json
{
  "id": "uuid",
  "household_id": "household_123",
  "category": "household.schedule",
  "key": "lisa.departure_time",
  "value": {
    "time": "06:30",
    "timezone": "America/New_York"
  },
  "profile_id": "profile_lisa",
  "subject_id": null,
  "routine_id": "routine_morning",
  "visibility": "household",
  "confidence": 1.0,
  "authority_score": 0.95,
  "review_state": "accepted",
  "provenance": {
    "source_system": "routine_setup",
    "source_type": "admin_entry",
    "captured_at": "2026-05-26T08:00:00Z",
    "observed_at": "2026-05-26T08:00:00Z",
    "ingest_method": "structured_write",
    "created_by_profile_id": "profile_marc",
    "trust_tag": "admin_asserted"
  },
  "staleness": {
    "state": "fresh",
    "last_verified_at": "2026-05-26T08:00:00Z",
    "stale_after": null
  },
  "lifecycle": {
    "state": "active",
    "archived_at": null,
    "archived_reason": null,
    "expires_at": null
  },
  "conflicts": [],
  "created_at": "2026-05-26T08:00:00Z",
  "updated_at": "2026-05-26T08:00:00Z",
  "schema_version": "knowledge_entry.v1"
}
```

---

## 19. Recommended spec additions by phase

### Immediate / before LLM-Wiki wire-up

Add these before implementation starts:

1. Exact facts vs search/query boundary.
2. Revised `KnowledgeEntry` metadata fields:
   - provenance
   - confidence
   - authority_score
   - review_state
   - visibility
   - staleness
   - lifecycle
3. Category/key validation behavior.
4. Strong read-after-write for exact facts.
5. Conflict/stale write behavior.
6. Profile export `llm_wiki` schema.
7. Cell-mediated Honcho/LLM-Wiki stance.
8. Service-to-service auth stance.
9. Observability requirements.

### Near-term / after basic facts API

Add these once exact reads/writes work:

1. History/changelog route.
2. Review queue route.
3. Inbox/unstructured ingest route.
4. Failed ingest route.
5. Snapshot/routine-scoped read route.
6. Archive/retention lifecycle behavior.
7. Search/query confidence/freshness usage rules.

### Later / post-MVP or Phase 2

Add these after founder household validation unless a blocker appears:

1. Direct MCP access for assistants.
2. Direct Honcho ↔ LLM-Wiki sync.
3. Adapter framework for additional ingest formats.
4. Advanced synthesis/promotion engine integration.
5. Rich contradiction arbitration UI.
6. Broader semantic retrieval for non-routine household knowledge.

---

## 20. Bottom line

Do not reduce LLM-Wiki to only a key/value cache if Homefront wants trustworthy household knowledge over time. The minimum safe expansion is:

1. **Provenance**
2. **Confidence/authority**
3. **Contradiction handling**
4. **History/changelog**
5. **Visibility/profile scoping**
6. **Exact facts vs search/query boundary**
7. **Read-after-write/index freshness guarantees**

The first implementation can still be small. The schema and contract need to leave room for governed knowledge now, or Homefront will end up rewriting the integration as soon as household knowledge starts coming from conversations, integrations, kids, adults, devices, and calendar/document sources at the same time.

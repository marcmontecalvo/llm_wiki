# Unified LLM-Wiki ↔ Homefront Integration Gap Audit

**Purpose:** unify the Codex and Claude Code gap reviews into one implementation-facing audit.

**Scope:** LLM-Wiki integration with Homefront as described by `docs/integrations/llm-wiki.md`. LLM-Wiki TUI and WebUI are out of scope.

**Verdict:** LLM-Wiki is **not integration-ready for the Homefront facts contract as written**. The current repo appears to be a page-oriented, daemon-governed wiki/search system. Homefront expects a household-scoped, typed facts API with strict category/key semantics, update safety, deletion semantics, degradation behavior, and profile-export compatibility. Those can coexist, but they are not the same surface.

---

## Priority summary

| Priority | Gap | Why it matters |
|---|---|---|
| P0 | `/knowledge/{household_id}` read/write API is missing | Homefront's primary integration contract cannot call LLM-Wiki. |
| P0 | Runtime endpoint/port defaults do not match | Homefront default client assumptions will fail without manual override. |
| P0 | API startup depends on UI password | REST API may fail in a headless Homefront environment even though UI is out of scope. |
| P1 | Data model is page/wiki-centric, not household-fact-centric | Homefront needs typed JSON facts scoped by household/category/key. |
| P1 | No update-safety/concurrency semantics | Stale or out-of-order routine facts can overwrite newer state. |
| P1 | No deletion/routine-reference contract | Homefront needs safe deletion semantics tied to routine versioning and rollback. |
| P1 | No server-side category namespace validation | Buggy clients could pollute the knowledge store or silently store invalid categories. |
| P1 | No Homefront-compatible export/profile schema | `llm_wiki: []` remains undefined/unpopulated. |
| P1 | Auth/service boundary is underspecified | A shared host or future multi-cell topology needs scoped auth. |
| P2 | Index/read-after-write freshness is unclear | Writes through page paths may not become immediately queryable. |
| P2 | Degradation/SLA behavior is not aligned | Homefront expects bounded reads/writes and clear degraded states. |
| P2 | Existing health/export surfaces are reusable but not sufficient | They need Homefront-specific scoping/redaction/contracts. |

---

## 1. Missing Homefront facts API

### What Homefront expects

Homefront expects a facts API shaped around household-scoped knowledge entries, roughly:

- `GET /knowledge/{household_id}`
- `POST /knowledge/{household_id}`
- `KnowledgeEntry`
- `KnowledgeListResponse`
- `KnowledgeWriteResponse`

The expected entry shape is:

```json
{
  "id": "uuid",
  "household_id": "uuid-or-string",
  "category": "household.roster",
  "key": "dishwasher_rotation",
  "value": {},
  "updated_at": "2026-05-26T00:00:00Z"
}
```

### What LLM-Wiki currently exposes

The reports agree that the repo exposes wiki/search/page routes such as:

- `/v1/query`
- `/v1/search`
- `/v1/pages`
- `/v1/ingest`
- `/v1/domains`
- `/v1/export`
- `/v1/synthesis`
- `/v1/health`
- `/v1/honcho/status`

No `/knowledge/{household_id}` read/write surface was found.

### Impact

A naive Homefront `IntegrationClient` cannot use the service. The current LLM-Wiki API is not a missing field or minor mismatch; it is a different product surface.

### Fix

Add a dedicated `knowledge` router rather than trying to force Homefront through `/v1/pages`.

Minimum routes:

```text
GET    /knowledge/{household_id}
GET    /knowledge/{household_id}/{category}
GET    /knowledge/{household_id}/{category}/{key}
POST   /knowledge/{household_id}
DELETE /knowledge/{household_id}/{category}/{key}
GET    /knowledge/{household_id}/export
GET    /knowledge/{household_id}/health
```

Optional but likely needed:

```text
GET    /knowledge/{household_id}/{category}/{key}/history
POST   /knowledge/{household_id}/inbox
GET    /knowledge/{household_id}/failed
GET    /knowledge/{household_id}/review
```

---

## 2. Runtime endpoint and port mismatch

### Gap

Homefront expects LLM-Wiki at:

```text
http://localhost:5002
```

configurable through:

```text
LLM_WIKI_URL
```

The reports found LLM-Wiki defaults to port `3050`, exposes `3050`, and maps `${WIKI_PORT:-3050}:3050`.

### Impact

Default Homefront integration settings will fail unless every environment overrides the URL/port manually.

### Fix

Pick one of these and document it in both repos:

1. Make LLM-Wiki default to `5002` for the Homefront deployment profile.
2. Keep LLM-Wiki internal port `3050`, but set Homefront's default `LLM_WIKI_URL` to the actual compose service URL.
3. Add a dedicated Homefront compose/service profile that maps `5002 -> 3050`.

Recommended Homefront-aligned default:

```yaml
environment:
  LLM_WIKI_URL: http://llm-wiki:5002
ports:
  - "${LLM_WIKI_PORT:-5002}:5002"
```

If the app process still listens on `3050`, document that explicitly and keep the service-level URL stable.

---

## 3. API startup is coupled to UI password

### Gap

One report found that `create_app()` raises when `WIKI_UI_PASSWORD` is empty, while compose defaults it to empty. Since WebUI/TUI are out of scope for Homefront, REST startup should not depend on a UI password.

### Impact

A headless LLM-Wiki service embedded in a Homefront cell may fail to start because a UI-only credential is missing.

### Fix

Separate API auth/startup from UI auth/startup.

Recommended behavior:

- REST API starts without `WIKI_UI_PASSWORD` when UI is disabled.
- UI routes are disabled or return a clear configuration error when UI auth is missing.
- Homefront service-to-service auth uses its own variable, for example `LLM_WIKI_SERVICE_TOKEN`, not UI credentials.

---

## 4. Data model mismatch: pages/domains vs household facts

### Gap

Homefront needs typed household facts:

```text
household_id
category
key
value_json
updated_at
id
```

The repo appears to store pages as markdown files with frontmatter fields like:

```text
title
domain
kind
confidence
authority_score
content
tags
updated_at
```

### Impact

Using pages as facts creates multiple problems:

- No first-class `household_id`.
- No strict `category`.
- No stable `category + key` identity.
- No typed JSON `value`.
- No predictable round-trip for structured routine data.
- No clear boundary between normalized facts and unstructured wiki content.

### Fix

Add a dedicated structured facts store. Do not rely on markdown pages as the canonical Homefront facts source.

Minimum table/storage shape:

```sql
knowledge_entries (
  id uuid primary key,
  household_id text not null,
  category text not null,
  key text not null,
  value_json jsonb not null,
  updated_at timestamptz not null,
  created_at timestamptz not null,
  deleted_at timestamptz null,
  source text null,
  provenance_json jsonb null,
  confidence numeric null,
  authority_score numeric null,
  review_state text not null default 'accepted',
  unique (household_id, category, key)
)
```

If LLM-Wiki remains filesystem/SQLite-based, use the same logical shape in SQLite or JSON-per-key files, but preserve the contract.

---

## 5. Household isolation is absent or implicit

### Gap

The reports found no meaningful `household_id` concept in the LLM-Wiki repo. The current service appears single-tenant by directory/profile/domain assumptions.

### Impact

This is acceptable only if Homefront runs exactly one LLM-Wiki instance per isolated household cell and never asks the service to serve multiple households. Even then, the API contract still includes `household_id`, so the service must validate it.

### Fix

Pick the intended model explicitly:

### Recommended Phase 1 model

- One LLM-Wiki instance per household cell.
- API still requires `household_id`.
- Service validates that the requested `household_id` matches configured `HOUSEHOLD_ID`.
- Mismatches return `403` or `404`, not cross-household data.

Example:

```text
HOUSEHOLD_ID=founder-household
```

Response on mismatch:

```json
{
  "code": "household_mismatch",
  "message": "Requested household is not served by this LLM-Wiki instance.",
  "details": {}
}
```

---

## 6. Category namespace validation is missing

### Gap

Homefront expects categories such as:

- `household.roster`
- `household.assignments`
- `household.pets`
- `household.appliances`
- `household.preferences`
- `household.schedule`
- `household.vehicles`
- `household.presence`
- `household.recurring_responsibilities`

The reports found no server-side registry or `unknown_knowledge_category` behavior.

### Impact

Invalid categories can silently enter the store. That breaks assistant context assembly, routine simulation, support diagnostics, and future migrations.

### Fix

Add a shared category registry in Homefront contracts and mirror it in LLM-Wiki.

Minimum server behavior:

```json
{
  "code": "unknown_knowledge_category",
  "message": "Knowledge category is not recognized.",
  "details": {
    "category": "household.random"
  }
}
```

Also reject invalid keys with a stable error code such as `invalid_knowledge_key`.

---

## 7. Write/upsert semantics and stale-update safety are missing

### Gap

Homefront planned endgame behavior includes read-before-write timestamp checks and dropping older updates. Current page writes reportedly overwrite directly, set server time, and do not compare caller-provided `updated_at`.

### Impact

Out-of-order writes can corrupt household routine facts. Example: an older calendar sync event or delayed conversation extraction can overwrite a newer admin correction.

### Fix

Define Homefront facts writes as compare-and-set upserts.

Minimum request:

```json
{
  "category": "household.schedule",
  "key": "annabella_wake_time",
  "value": {
    "time": "05:00",
    "days": ["school_day"]
  },
  "observed_at": "2026-05-26T09:00:00Z",
  "expected_updated_at": "2026-05-26T08:30:00Z",
  "source": "routine_setup"
}
```

Minimum behavior:

- If no entry exists: create.
- If entry exists and `expected_updated_at` matches: update.
- If entry exists and incoming `observed_at` is older than stored `updated_at`: drop or return conflict.
- If entry exists and `expected_updated_at` does not match: return `409 knowledge_conflict`.
- Always return the resulting entry or conflict details.

Recommended error:

```json
{
  "code": "knowledge_conflict",
  "message": "Knowledge entry changed since caller last read it.",
  "details": {
    "category": "household.schedule",
    "key": "annabella_wake_time",
    "stored_updated_at": "2026-05-26T09:30:00Z",
    "expected_updated_at": "2026-05-26T08:30:00Z"
  }
}
```

---

## 8. Distributed/per-key locking is missing

### Gap

The reports found only local/in-process locking around job state, not a lock keyed by `(household_id, category, key)`.

### Impact

Concurrent writes to the same fact can race. This matters for routine facts touched by integrations, assistant interactions, admin edits, and scheduled syncs.

### Fix

For single-process Phase 1, an `asyncio.Lock` map keyed by:

```text
{household_id}:{category}:{key}
```

is sufficient.

For multi-worker or multi-process deployment, use a DB-backed lock/transaction pattern. If the facts store is Postgres, use row-level locking or advisory locks. If SQLite, use explicit transactions and unique constraints.

---

## 9. Deletion contract and routine-reference safety are missing

### Gap

Homefront expects atomic deletions coordinated with routine version increments. LLM-Wiki has lower-level index removal helpers but no Homefront facts delete endpoint, no transaction hook, and no routine-reference behavior.

### Impact

Deleting a fact used by active or draft routines can orphan routine references or silently change simulation behavior.

### Fix

Add a Homefront-facing delete contract.

Minimum behavior:

- Soft-delete by default.
- Return affected references or require caller-provided reference resolution.
- Support `dry_run=true`.
- Require a deletion reason.
- Emit an event/activity record.
- Preserve history.

Example:

```text
DELETE /knowledge/{household_id}/household.pets/dog.bailey?dry_run=true
```

Example response:

```json
{
  "would_delete": true,
  "entry": {},
  "affected_references": [
    {
      "type": "routine",
      "id": "morning-routine",
      "field": "dogs_out_step"
    }
  ],
  "requires_routine_version_increment": true
}
```

LLM-Wiki does not need to own Homefront routine mutation, but it does need either:

1. a hook/event that Homefront consumes before finalizing deletion, or
2. a strict contract saying Homefront owns reference checks before calling delete.

---

## 10. Read-after-write and index freshness are undefined

### Gap

Existing `/v1/pages` writes reportedly save markdown but do not immediately update search/query indexes. If Homefront writes a fact then immediately queries/searches it, behavior may be stale.

### Impact

Routine setup, simulation, assistant context assembly, and troubleshooting can disagree about what was just written.

### Fix

Define consistency by surface:

- `/knowledge/*` exact reads must be strongly read-after-write consistent.
- `/v1/search`, `/v1/query`, `/v1/synthesis` may be eventually consistent, but response metadata must expose index freshness.
- If search/query is stale, return `index_updated_at`, `entry_updated_at`, and optionally `stale_index: true`.

Minimum response metadata:

```json
{
  "entries": [],
  "consistency": {
    "exact_store": "strong",
    "search_index": "eventual",
    "index_updated_at": "2026-05-26T09:30:00Z"
  }
}
```

---

## 11. Timeouts/SLA/degradation behavior is not aligned

### Gap

Homefront expects tight budgets, including a short write timeout and a longer read timeout. Reports flagged that page reads can scan directories and query paths are heavier, so the budget may be unrealistic for current routes.

### Impact

Homefront needs predictable degraded behavior, not hanging or slow context assembly.

### Fix

Define server-side request budgets and explicit degradation responses.

Recommended behavior:

| Operation | Target |
|---|---|
| Exact fact read | fast, bounded, strongly consistent |
| Fact write | fast, bounded, conflict-aware |
| Search/query | longer budget, explicitly optional/degradable |
| Export | async or admin-only, not part of live routine budget |

When LLM-Wiki cannot meet a live request budget, return a clean `503` with stable problem shape:

```json
{
  "code": "llm_wiki_timeout",
  "message": "LLM-Wiki did not produce a response within the configured budget.",
  "details": {
    "operation": "knowledge_read",
    "budget_ms": 3000
  }
}
```

Homefront can then emit its own `DegradedContextSignal`.

---

## 12. Health/readiness is too generic

### Gap

LLM-Wiki has `/v1/health`, but not per-household/readiness semantics for Homefront.

### Impact

Homefront needs to know whether LLM-Wiki is ready for a specific household cell and whether exact facts, search index, ingestion, and export are usable.

### Fix

Add:

```text
GET /knowledge/{household_id}/health
```

Response:

```json
{
  "status": "ready",
  "household_id": "founder-household",
  "facts_store": "ready",
  "search_index": "ready",
  "ingest_daemon": "ready",
  "last_indexed_at": "2026-05-26T09:30:00Z",
  "degraded_reasons": []
}
```

---

## 13. Profile export / `llm_wiki: []` schema is missing

### Gap

Homefront mentions a profile export stub returning `llm_wiki: []`. LLM-Wiki has export surfaces, but they are wiki-wide and not shaped as Homefront profile/household exports.

### Impact

Support bundles, user data export, privacy review, and profile migration remain undefined.

### Fix

Define and implement a Homefront export shape.

Minimum route:

```text
GET /knowledge/{household_id}/export
```

Recommended response:

```json
{
  "household_id": "founder-household",
  "generated_at": "2026-05-26T10:00:00Z",
  "llm_wiki": [
    {
      "id": "uuid",
      "category": "household.preferences",
      "key": "marc.coffee",
      "value": {},
      "visibility": "adults_only",
      "provenance": {},
      "confidence": 1.0,
      "updated_at": "2026-05-26T09:00:00Z"
    }
  ],
  "redaction": {
    "mode": "profile_export",
    "private_fields_removed": []
  }
}
```

---

## 14. Auth between Homefront and LLM-Wiki is underspecified

### Gap

The repo has UI auth variables, but the Homefront integration spec is silent or insufficient on service-to-service auth. If each household cell runs one private LLM-Wiki, the risk is lower, but not zero.

### Impact

A future shared host, bad compose networking, or support tooling path could expose knowledge entries without a scoped token.

### Fix

Add service-to-service auth separate from UI auth.

Minimum:

- `LLM_WIKI_SERVICE_TOKEN`
- Bearer token required for `/knowledge/*`
- Optional `X-Household-Id` cross-check
- Request ID propagation
- Audit metadata for writes

Recommended headers:

```text
Authorization: Bearer <cell-local-service-token>
X-Request-Id: <request-id>
X-Homefront-Cell-Id: <cell-id>
```

---

## 15. Existing pages/query/synthesis stack is not a drop-in replacement

### Gap

Both reviews note that the current LLM-Wiki functionality is useful, but orthogonal to Homefront's narrow facts contract.

### Impact

Trying to treat `/v1/pages` or `/v1/query` as the Homefront facts API will create hidden bugs:

- weak consistency
- no category validation
- no typed JSON contract
- no concurrency control
- no deletion/reference semantics
- no household validation

### Fix

Keep two surfaces:

1. **Structured facts API** for Homefront runtime correctness.
2. **Wiki/search/synthesis API** for broader knowledge retrieval, diagnostics, review, and assistant context where explicitly allowed.

---

## Minimum implementation package

To satisfy the existing Homefront facts integration spec, LLM-Wiki needs:

1. `knowledge` router with `GET`, `POST`, `DELETE`, health, and export.
2. Structured facts storage keyed by `(household_id, category, key)`.
3. Category registry and server-side validation.
4. Strong exact read-after-write behavior.
5. Compare-and-set/write conflict behavior with stale update rejection.
6. Per-key write locking.
7. Soft-delete and deletion dry-run/reference handoff.
8. Homefront-shaped export/profile schema.
9. Service-to-service auth separate from UI auth.
10. Homefront deployment profile with aligned URL/port/startup behavior.
11. Stable problem/error shape compatible with Homefront.
12. Tests proving contract compatibility.

---

## Recommended tests

### API contract tests

- `GET /knowledge/{household_id}` returns `KnowledgeListResponse`.
- `POST /knowledge/{household_id}` creates a fact.
- `POST /knowledge/{household_id}` updates a fact when `expected_updated_at` matches.
- stale/out-of-order write is rejected or dropped by contract.
- unknown category returns `400 unknown_knowledge_category`.
- household mismatch returns `403` or `404`.
- delete dry-run returns affected references or defined empty list.
- export returns `llm_wiki` array shape.
- missing/invalid bearer token returns `401`.

### Consistency tests

- exact read sees a just-written fact immediately.
- search/query clearly reports stale or eventual-consistency metadata if index is behind.
- concurrent writes to same key do not corrupt the entry.

### Deployment tests

- REST API starts without UI password when UI is disabled.
- Homefront compose profile exposes the expected service URL.
- health/readiness reports facts store and index state separately.

---

## Bottom line

Treat this as **net-new Homefront integration surface beside the existing LLM-Wiki wiki/search system**, not as a small patch to existing page routes. The current repo provides useful building blocks: health, Docker packaging, exports, query/search, governance concepts, and potentially provenance/confidence metadata. It does **not** currently implement the Homefront facts contract.

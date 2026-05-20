# Story 1.9: Multi-User Domain Scoping

Status: done

## Story

As a household operator,
I want domains to carry a scope and optional owner field, and queries to be filterable by profile,
so that household knowledge stays separate from personal knowledge and each member only sees what they should.

**Prerequisite:** Stories 1.6, 1.7, and 1.8 must be complete — this story modifies both REST routes and MCP tools to pass profile scoping through to `WikiQuery.search()`.

## Acceptance Criteria

1. **Given** a `domains.yaml` entry with `scope: shared` **When** the config is loaded and validated by Pydantic **Then** it passes validation without error.

2. **Given** a `domains.yaml` entry with `scope: personal` and `owner: marc` **When** the config is loaded **Then** both fields are validated and accessible on the domain config object.

3. **Given** a `domains.yaml` entry with no `scope` field **When** loaded **Then** it defaults to `scope: shared` — backward compatible with all existing domain configs.

4. **Given** `WikiQuery.search()` is called with `scope_to_profile="marc"` **When** executed **Then** results are merged from the `household` domain and the `user-marc` domain only — all other personal domains are excluded.

5. **Given** `WikiQuery.search()` is called with `scope_to_profile=None` **When** executed **Then** it queries all configured domains — default behavior, no regression from current behavior.

6. **Given** `WikiQuery.search()` is called with an explicit `domain="household"` parameter **When** executed **Then** it queries only the `household` domain regardless of the `scope_to_profile` value.

7. **Given** any REST route or MCP tool that calls search **When** audited **Then** domain scope filtering logic is absent from route/tool code — it lives exclusively in `WikiQuery.search()`.

8. **Given** the calling harness sends `X-Profile-Id` (REST) or `profile_id` (MCP) **When** received **Then** llm-wiki trusts the value without validation — the calling harness is responsible for identity.

## Tasks / Subtasks

- [x] Add `scope` and `owner` fields to `DomainConfig` in `src/llm_wiki/models/config.py` (AC: 1, 2, 3)
  - [x] `scope: Literal["shared", "personal"] = "shared"` — default `shared` for backward compat
  - [x] `owner: str | None = None` — present only when `scope: "personal"`
  - [x] Validator: if `scope == "personal"` and `owner` is `None`, raise validation error
- [x] Update `config/domains.yaml` example to show both scope types (AC: 1, 2, 3)
- [x] Add `scope_to_profile: str | None` parameter to `WikiQuery.search()` (AC: 4, 5, 6, 7)
  - [x] When `scope_to_profile=None`: query all domains (current behavior)
  - [x] When `scope_to_profile="marc"`: include `household` (shared domains) + `user-marc` (owner=="marc" personal domains); exclude all other personal domains
  - [x] When explicit `domain` param is also set: honor `domain` exclusively; ignore `scope_to_profile`
  - [x] Filtering logic lives ONLY in `WikiQuery.search()` — verified by code audit
- [x] Update `GET /v1/query`, `GET /v1/search` routes to pass `profile_id` (AC: 7, 8)
  - [x] Both routes already use `Depends(get_profile_id)` from Story 1.4
  - [x] Pass `scope_to_profile=profile_id` to `wiki.search()` calls
- [x] Update MCP `query` and `search` tools to accept and pass `profile_id` (AC: 5, 8)
  - [x] Add `profile_id: str | None = None` parameter to both tools
  - [x] Pass to `wiki.search(scope_to_profile=profile_id)`
- [x] Write tests

## Dev Notes

### Current State of DomainConfig

`src/llm_wiki/models/config.py:10-30` — `DomainConfig` currently has `id`, `title`, `description`, `owners`, `promote_to_shared`. It has NO `scope` or `owner` fields for personal/shared distinction.

The existing `owners: list[str]` field is different from the new `owner: str | None` field:
- `owners` = list of people who manage the domain (existing)
- `owner` = the single profile_id this personal domain belongs to (new)

Both can coexist.

### Domain Scoping Logic in WikiQuery.search()

```python
# src/llm_wiki/query/search.py — modify search() signature and add filtering

def search(
    self,
    query: str,
    domain: str | None = None,
    scope_to_profile: str | None = None,
    ...
) -> tuple[list, bool]:
    # Determine which domains to search
    domains_to_search = self._resolve_search_domains(domain, scope_to_profile)
    # ... rest of search logic

def _resolve_search_domains(
    self,
    domain: str | None,
    scope_to_profile: str | None,
) -> list[str]:
    """Return list of domain IDs to search. Logic lives ONLY here."""
    if domain is not None:
        # Explicit domain always wins
        return [domain]

    all_domains = self.config.domains.domains
    if scope_to_profile is None:
        # No profile filter: search all domains
        return [d.id for d in all_domains]

    # Profile filter: shared domains + this profile's personal domain
    result = []
    for d in all_domains:
        scope = getattr(d, 'scope', 'shared')
        if scope == 'shared':
            result.append(d.id)
        elif scope == 'personal' and getattr(d, 'owner', None) == scope_to_profile:
            result.append(d.id)
    return result
```

### Backward Compatibility

All existing domain configs (no `scope` field) must continue to work. The `scope: Literal["shared", "personal"] = "shared"` default ensures this. After this story, `scope_to_profile=None` behavior is identical to pre-story behavior — no regression.

### REST Route Changes (Minimal)

Routes already receive `profile_id` from `Depends(get_profile_id)` (set up in Story 1.4). The change is just passing it through:

```python
# BEFORE Story 1.9 (from Story 1.7):
pages = await asyncio.to_thread(wiki.search, req.query, domain=req.domain)

# AFTER Story 1.9:
pages = await asyncio.to_thread(
    wiki.search, req.query, domain=req.domain, scope_to_profile=profile_id
)
```

### domains.yaml Example Update

```yaml
# config/domains.yaml
domains:
  - id: household
    title: Household Knowledge
    description: Shared knowledge visible to all household members
    scope: shared               # NEW: shared | personal

  - id: user-marc
    title: Marc's Personal Knowledge
    description: Personal domain scoped to Marc
    scope: personal             # NEW
    owner: marc                 # NEW: profile_id of the owner
```

### Project Structure — Files to Modify

```
src/llm_wiki/
├── models/config.py            UPDATE — add scope/owner to DomainConfig
├── query/search.py             UPDATE — add scope_to_profile param + _resolve_search_domains()
├── api/routers/query.py        UPDATE — pass scope_to_profile=profile_id
├── api/routers/search.py       UPDATE — pass scope_to_profile=profile_id
└── mcp/tools.py                UPDATE — add profile_id param to query/search tools

config/
└── domains.yaml                UPDATE — add scope/owner to example domains
```

### Testing

`tests/unit/test_domain_scoping.py` (new):

```python
def test_scope_defaults_to_shared():
    d = DomainConfig(id="test", title="T", description="D")
    assert d.scope == "shared"

def test_personal_scope_requires_owner():
    with pytest.raises(ValidationError):
        DomainConfig(id="test", title="T", description="D", scope="personal")

def test_search_returns_all_domains_when_no_profile(wiki_root):
    wiki = WikiQuery(wiki_root=wiki_root)
    domains = wiki._resolve_search_domains(domain=None, scope_to_profile=None)
    # Should return all configured domains
    assert len(domains) > 0

def test_explicit_domain_overrides_profile_filter(wiki_root):
    wiki = WikiQuery(wiki_root=wiki_root)
    domains = wiki._resolve_search_domains(domain="household", scope_to_profile="marc")
    assert domains == ["household"]

def test_profile_filter_includes_shared_and_personal_owner(wiki_root):
    # Requires wiki_root with config having household (shared) and user-marc (personal, owner=marc)
    wiki = WikiQuery(wiki_root=wiki_root)
    domains = wiki._resolve_search_domains(domain=None, scope_to_profile="marc")
    assert "household" in domains
    # user-marc should be included if config has it
```

### Critical Anti-Patterns to Avoid

- **Never filter domains in route/tool code** — filtering logic lives exclusively in `WikiQuery._resolve_search_domains()`
- **Never validate or reject profile_id** — llm-wiki trusts the calling harness
- **Never break existing behavior** when `scope_to_profile=None` — all domains must be searched

### References

- Architecture: "Multi-User Household Architecture" — domain YAML structure
- Architecture: "Domain Scope & Profile Scoping" — `X-Profile-Id` header, `profile_id` param
- Architecture: Enforcement Guidelines — rule 7: domain scope logic in WikiQuery.search() only
- `src/llm_wiki/models/config.py:10-30` — current DomainConfig
- `src/llm_wiki/query/search.py` — current search() signature

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

1. Added `scope` and `owner` fields to `DomainConfig` with `model_validator` ensuring `owner` is required when `scope="personal"`. Backward compatible — existing configs without these fields default to `scope="shared"`.
2. Implemented `_resolve_search_domains()` in `WikiQuery` — the exclusive domain resolution logic per story requirements. When no config exists, returns `None` to skip scoping (backward compatible).
3. Wired `scope_to_profile` through `WikiQuery.search()` — applies domain filtering using resolved domains set against page metadata domains.
4. Updated `GET /v1/search` REST route to accept and pass `profile_id` (POST `/v1/query` already did during Story 1.12).
5. Updated MCP `search` tool to accept `profile_id` parameter (MCP `query` tool already had it from a prior story).
6. Wrote 16 unit tests covering: config schema validation, domain resolution logic, profile filtering, and explicit domain override. All 1311 tests pass (0 regressions).

### File List

- `src/llm_wiki/models/config.py` — ADDED scope/owner fields, model_validator
- `src/llm_wiki/query/search.py` — ADDED wiki_config param, _resolve_search_domains(), scope filtering in search()
- `src/llm_wiki/api/routers/search.py` — UPDATED to pass scope_to_profile
- `src/llm_wiki/mcp/tools.py` — UPDATED search tool to accept/profile_id
- `config/domains.yaml` — UPDATED with scope/owner on all domains
- `tests/unit/test_domain_scoping.py` — CREATED: 16 tests for domain scoping

### Change Log

- Addressed code review findings - 0 items resolved (2026-05-19)
- Added multi-user domain scoping with profile-based filtering (Story 1.9)

# Story HF.6: Workspace-Scoped Knowledge API

Status: backlog

## Story

As a Homefront integration client,
I want all knowledge endpoints (query, search, pages, review, conflicts, export) scoped to a workspace,
so that domain remains categorization only and workspace is the isolation boundary.

**Prerequisites:** Stories HF.1–HF.4 must be complete — workspace facts API (HF.1), storage (HF.2), categories (HF.3), and conflicts (HF.4) define the facts surface. This story extends fact scoping, review, and export to workspace boundaries.

## Acceptance Criteria

1. **Given** `POST /v1/workspaces/{workspace_id}/knowledge/query` **When** called **Then** it queries wiki pages AND facts scoped to `workspace_id` — returns combined results from both surfaces.

2. **Given** `POST /v1/workspaces/{workspace_id}/knowledge/search` **When** called **Then** it searches fulltext and vector indexes scoped to the workspace and returns results.

3. **Given** `GET /v1/workspaces/{workspace_id}/knowledge/pages/{page_id}` **When** called **Then** it returns the page if it belongs to the workspace, or 404 if not.

4. **Given** domain filtering **When** a search or query operates on pages **Then** domain remains a categorization label only (not a security boundary).

5. **Given** `X-Profile-Id` or `profile_id` parameter **When** present **Then** extra scope filtering applies (for multi-user) AND workspace scoping takes precedence over domain scoping.

6. **Given** personal domain pages **When** queried from a different workspace ** Then** they do not leak across workspace boundaries (AC: 4).

7. **Given** `GET /v1/workspaces/{workspace_id}/knowledge/conflicts` **When** called ** Then** it returns conflicts for facts in the workspace (HF.4).

8. **Given** `GET /v1/workspaces/{workspace_id}/knowledge/review` **When** called ** Then** it returns pending review items for the workspace (facts with `pending_review` status).

9. **Given** `POST /v1/workspaces/{workspace_id}/knowledge/export` **When** triggered ** Then** it returns an export containing both wiki pages and facts scoped to the workspace.

10. **Given** `GET /v1/workspaces/{workspace_id}/knowledge/stale` **When** called ** Then** it returns pages or facts past their staleness threshold for the workspace.

## Tasks / Subtasks

- [ ] Create workspace-scoped knowledge service (`src/llm_wiki/knowledge/service.py` — AC: 1–10)
  - [ ] `class WorkspaceKnowledgeService`: orchestrates between wiki pages and workspace facts
  - [ ] `_scope_pages_by_workspace(wiki: WikiQuery, workspace_id: str, query: str, depth: str) -> list[result]` — pages scoped to workspace via domain scope metadata (Story 1.9): shared domains visible to all, personal domains scoped to owning workspace
  - [ ] `_scope_facts_by_workspace(store: WorkspaceFactStore, workspace_id: str, query_text: str) -> list[result]` — text search across fact values for the workspace
  - [ ] `query(workspace_id, query_text, depth: str, profile_id: str | None) -> KnowledgeQueryResult` — combines both
  - [ ] `search(workspace_id, query_text, profile_id: str | None) -> KnowledgeSearchResult` — fulltext + vector, domain as categorization only
  - [ ] `get_page(workspace_id, page_id) -> dict | None` — scoped page retrieval
  - [ ] `get_conflicts(workspace_id) -> list[dict]` — REST-equivalent of conflict listing
  - [ ] `get_review_items(workspace_id) -> list[dict]` — pending review items
  - [ ] `export(workspace_id, format: str = "json") -> dict` — combined export (AC: 9)
  - [ ] `list_stale(workspace_id) -> list[dict]` — stale pages and facts
- [ ] Create knowledge router (`src/llm_wiki/api/routers/knowledge.py` — AC: 1–10)
  - [ ] `router = APIRouter(prefix="/v1/workspaces/{workspace_id}/knowledge", tags=["knowledge"])`
  - [ ] `POST /knowledge/query` — combined query (AC: 1)
  - [ ] `POST /knowledge/search` — combined search (AC: 2)
  - [ ] `GET /knowledge/pages/{page_id}` — scoped page retrieval (AC: 3)
  - [ ] `GET /knowledge/conflicts` — conflicts listing (AC: 7)
  - [ ] `GET /knowledge/review` — review items listing (AC: 8)
  - [ ] `POST /knowledge/export` — trigger export (AC: 9)
  - [ ] `GET /knowledge/stale` — stale items (AC: 10)
  - [ ] Each route calls workspace knowledge service — no business logic in routes
  - [ ] Support `profile_id` via `X-Profile-Id` header (REST) and MCP parameter (MCP tools)
  - [ ] Domain filtering only applies to wiki pages, not to facts (domain = categorization, not isolation)
- [ ] Wire into FastAPI app (AC: 1–10)
  - [ ] `app.include_router(knowledge_router)`
  - [ ] Workspace scope applies by default to all knowledge endpoints
- [ ] Create MCP knowledge tools — Updated MCP tools: `query` + `search` + `read_page` + `export` now accept workspace scope
  - [ ] All existing MCP tools (query, search, read_page, list_pages, export) gain a `workspace_id` parameter
  - [ ] `workspace_id` is optional — when omitted, defaults to querying all workspaces (backward compatible)
  - [ ] When present, results are scoped to that workspace
- [ ] Enforce workspace domain as categorization only (AC: 4, 6)
  - [ ] Audit all search/query code: domain is used for ranking/labeling on wiki pages, not for filtering facts
  - [ ] Workspace isolation is always the primary filter: facts scanned by URL path `/{workspace_id}/`, pages scanned via domain scope metadata (Story 1.9)
  - [ ] Domain scoping via `scope_to_profile` (from Story 1.9) is subordinate to workspace filtering
- [ ] Write tests (`tests/unit/test_workspace_knowledge.py` — AC: 1–10)
  - [ ] `test_combined_query_pages_and_facts` — query returns both page and fact matches
  - [ ] `test_search_scoped_to_workspace` — search does not return facts or pages from other workspaces
  - [ ] `test_get_page_in_workspace_scoped` — 404 if page not in workspace
  - [ ] `test_domain_not_security_boundary` — pages from different domains within same workspace are all visible via search
  - [ ] `test_profile_scoping_subordinate_to_workspace` — profile scope applies within workspace, not instead of
  - [ ] `test_conflicts_scoped_to_workspace` — conflicts list only shows workspace facts
  - [ ] `test_review_items_scoped_to_workspace` — pending review only shows workspace items
  - [ ] `test_export_contains_pages_and_facts` — export contains both surface types
  - [ ] `test_get_stale_items` — returns stale pages and facts in workspace
  - [ ] `test_personal_domains_not_leaked_across_workspaces` — personal domain page A in WS1 is not returned when querying WS2
  - [ ] `test_workspace_pages_scoped_to_directory` — pages under `workspaces/{workspace_id}/` are only returned for that workspace

## Dev Notes

### Page Storage Scoping by Workspace

Wiki pages are stored as markdown (`wiki_system/pages/{domain}/`) with no workspace fields. Workspace scoping for the knowledge API works at the **API level**, not the storage level, by using the domain scope from Story 1.9 (`scope: shared|personal` + `owner: profile_id`). The `WorkspaceKnowledgeService._scope_pages_by_workspace` method filters pages as follows:

```python
def _scope_pages_by_workspace(self, wiki: WikiQuery, workspace_id: str, query: str, depth: str) -> list[result]:
    # Pages from shared domains are visible from all workspaces (categorization only)
    # Pages from personal domains are scoped to the workspace that owns them
    results = wiki.query(query, depth=depth)
    scoped = []
    for r in results:
        page_id = r["page_id"]
        # Resolve wiki page → domain → check workspace scope
        domain = self._page_to_domain(page_id)
        dc = self._domain_config(domain)
        if dc.scope == "shared":
            scoped.append(r)  # shared = visible to all workspaces
        elif dc.scope == "personal" and dc.owner_workspace == workspace_id:
            scoped.append(r)  # personal = only visible to owning workspace
    return scoped
```

This approach uses **existing domain scope metadata** (from Story 1.9) rather than restructuring page storage. The workspace acts as a policy filter on top of the knowledge surface.

### Knowledge API vs Facts API

| Surface | Scoping mechanism | Scope type |
|---|---|---|
| `PUT/GET /facts/...` | URL path `/{workspace_id}/facts/{key}` | Primary isolation boundary |
| `POST /knowledge/query` | Domain scope (`shared`/`personal` + workspace ownership) | Policy filter |
| `GET /knowledge/pages/{id}` | Domain scope lookup via page ID | Policy filter |

The workspace is the **primary** isolation boundary for facts (hard storage-level). For pages it's a **policy filter** atop domain scoping.

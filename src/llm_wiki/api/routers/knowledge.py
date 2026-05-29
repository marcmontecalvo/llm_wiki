"""Workspace-scoped knowledge router.

All routes live under::

    /v1/workspaces/{workspace_id}/knowledge/{...}

Each route delegates to :class:`WorkspaceKnowledgeService`.
No business logic lives in routes.

Endpoints (AC by # in story):
    - POST /knowledge/query          — AC 1
    - POST /knowledge/search         — AC 2
    - GET  /knowledge/pages/{page_id} — AC 3
    - GET  /knowledge/conflicts      — AC 7
    - GET  /knowledge/review         — AC 8
    - POST /knowledge/export         — AC 9
    - GET  /knowledge/stale          — AC 10
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from llm_wiki.api.models import (
    QueryRequest,
    QueryResponse,
    QueryResultItem,
    SearchResultItem,
)
from llm_wiki.deps import get_knowledge_store, get_profile_id, get_wiki
from llm_wiki.knowledge.service import WorkspaceKnowledgeService
from llm_wiki.knowledge.storage import WorkspaceFactStore
from llm_wiki.query.search import WikiQuery

router = APIRouter(prefix="/v1/workspaces/{workspace_id}/knowledge", tags=["knowledge"])


def _get_knowledge_service(wiki: WikiQuery, store: WorkspaceFactStore) -> WorkspaceKnowledgeService:
    """Build a service instance from FastAPI dependencies."""
    from llm_wiki.knowledge.service import WorkspaceKnowledgeService  # noqa: PLC0415

    return WorkspaceKnowledgeService(wiki=wiki, store=store)


def _resource_to_query_result(r: dict) -> dict:
    """Convert a knowledge result dict to a QueryResultItem-like format."""
    if r.get("source") == "fact":
        return {
            "page_id": r.get("fact_key", ""),
            "title": r.get("fact_key", ""),
            "confidence": r.get("confidence", 0.0),
            "provenance": [],
            "contradictions": [],
            "authority_score": 0.0,
        }
    return {
        "page_id": r.get("page_id", ""),
        "title": r.get("title", ""),
        "confidence": r.get("confidence", 0.0),
        "provenance": r.get("sources", []),
        "contradictions": r.get("contradictions", []),
        "authority_score": r.get("authority_score", 0.0),
    }


# ── Route handlers ──────────────────────────────────────────────────────


@router.post("/query", response_model=QueryResponse | dict)
async def knowledge_query(
    workspace_id: str,
    req: QueryRequest,
    profile_id: str | None = Depends(get_profile_id),
    store: WorkspaceFactStore = Depends(get_knowledge_store),
    wiki: WikiQuery = Depends(get_wiki),
) -> QueryResponse | dict:
    """Combined query across wiki pages and workspace facts. (AC 1)"""
    svc = _get_knowledge_service(wiki, store)
    result = await svc.query(workspace_id, req.query, req.depth, profile_id)

    items = [_resource_to_query_result(r) for r in result.results]
    return QueryResponse(
        results=[QueryResultItem(**i) for i in items],
        timed_out=result.timed_out,
        partial=False,
    )


@router.post("/search", response_model=dict)
async def knowledge_search(
    workspace_id: str,
    q: str = Query(..., description="Search query text"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results"),
    profile_id: str | None = Depends(get_profile_id),
    store: WorkspaceFactStore = Depends(get_knowledge_store),
    wiki: WikiQuery = Depends(get_wiki),
) -> dict:
    """Combined search across wiki pages and workspace facts. (AC 2)"""
    svc = _get_knowledge_service(wiki, store)
    result = await svc.search(workspace_id, q, profile_id, limit)

    items = [_resource_to_query_result(r) for r in result.results]
    return {
        "results": [SearchResultItem(**dict(i)).model_dump() for i in items],
        "total": result.total,
    }


@router.get("/pages/{page_id}", response_model=dict)
async def knowledge_get_page(
    workspace_id: str,
    page_id: str,
    store: WorkspaceFactStore = Depends(get_knowledge_store),
    wiki: WikiQuery = Depends(get_wiki),
) -> dict:
    """Return a page scoped to a workspace, or 404. (AC 3)"""
    svc = _get_knowledge_service(wiki, store)
    page = await svc.get_page(workspace_id, page_id)
    if page is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "PAGE_NOT_FOUND",
                "message": f"Page '{page_id}' not found in workspace '{workspace_id}'",
            },
        )
    return page


@router.get("/conflicts", response_model=list[dict])
async def knowledge_conflicts(
    workspace_id: str,
    store: WorkspaceFactStore = Depends(get_knowledge_store),
    wiki: WikiQuery = Depends(get_wiki),
) -> list[dict]:
    """Unresolved conflicts scoped to workspace facts. (AC 7)"""
    wiki_base = Path(getattr(store, "_wiki_base", "wiki_system"))
    svc = _get_knowledge_service(
        # Use a dummy wiki for conflict listing — it doesn't need it
        WikiQuery(wiki_base=wiki_base),
        store,
    )
    conflicts = await svc.get_conflicts(workspace_id)
    return conflicts


@router.get("/review", response_model=list[dict])
async def knowledge_review(
    workspace_id: str,
    store: WorkspaceFactStore = Depends(get_knowledge_store),
    wiki: WikiQuery = Depends(get_wiki),
) -> list[dict]:
    """Pending review items for the workspace. (AC 8)"""
    svc = _get_knowledge_service(wiki, store)
    return await svc.get_review_items(workspace_id)


@router.post("/export", response_model=dict)
async def knowledge_export(
    workspace_id: str,
    fmt: str = Query(default="json", description="Export format (json)"),
    store: WorkspaceFactStore = Depends(get_knowledge_store),
    wiki: WikiQuery = Depends(get_wiki),
) -> dict:
    """Export wiki pages and facts scoped to workspace. (AC 9)"""
    svc = _get_knowledge_service(wiki, store)
    return await svc.export(workspace_id, fmt)


@router.get("/stale", response_model=list[dict])
async def knowledge_stale(
    workspace_id: str,
    threshold_days: int = Query(default=90, ge=1, description="Staleness threshold in days"),
    store: WorkspaceFactStore = Depends(get_knowledge_store),
    wiki: WikiQuery = Depends(get_wiki),
) -> list[dict]:
    """Pages and facts past their staleness threshold. (AC 10)"""
    svc = _get_knowledge_service(wiki, store)
    return await svc.list_stale(workspace_id, threshold_days)

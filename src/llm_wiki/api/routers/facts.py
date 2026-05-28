"""Workspace Facts API — REST endpoints.

All route functions are ``async def`` wrapping I/O in ``asyncio.to_thread()``.
No business logic lives in routes — they delegate to the knowledge storage service.

Reference: ``docs/contracts/homefront-llm-wiki-honcho-shared-contract-v1.md``
section 6.1.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from llm_wiki.deps import get_knowledge_store
from llm_wiki.exceptions import (
    UnknownFactCategoryError,
)
from llm_wiki.knowledge.categories import get_categories_list
from llm_wiki.knowledge.models import (
    KnowledgeConflictResolutionRequest,
    KnowledgeFactWriteRequest,
    KnowledgeFactWriteResponse,
    KnowledgeListResponse,
)
from llm_wiki.knowledge.storage import WorkspaceFactStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["facts"])


@router.get("/facts/categories")
async def categories() -> dict:
    """Return the canonical category registry with aliases.

    Global registry served regardless of workspace parameter.
    Must be **before** /facts/{fact_key} to prevent FastAPI from
    matching "categories" as a fact_key.
    (AC: 3)
    """
    return get_categories_list()


@router.get("/facts/{fact_key}")
async def get_fact(
    workspace_id: str,
    fact_key: str,
    store: Annotated[WorkspaceFactStore, Depends(get_knowledge_store)],
) -> dict:
    """Return a single fact by key.

    Returns 200 when the fact exists, 404 when it does not.
    (AC: 2, 3)
    """
    fact = await asyncio.to_thread(store.get_fact, workspace_id, fact_key)
    if fact is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "FACT_NOT_FOUND",
                "message": f"Fact not found: {fact_key}",
            },
        )
    return fact.model_dump()


@router.put("/facts/{fact_key}")
async def put_fact(
    workspace_id: str,
    fact_key: str,
    body: KnowledgeFactWriteRequest,
    store: Annotated[WorkspaceFactStore, Depends(get_knowledge_store)],
) -> KnowledgeFactWriteResponse:
    """Create or update a fact.

    Returns ``written``, ``unchanged``, ``stale_rejected``, or
    ``conflict_detected`` per the contract. Category validation
    raises ``UnknownFactCategoryError`` → HTTP 422.
    (AC: 1, 8, 9, 10, 11)
    """
    # Validate that the fact_key in the request body matches the path segment
    if body.key != fact_key:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "INVALID_REQUEST",
                "message": f"Request body key '{body.key}' does not match path key '{fact_key}'",
            },
        )

    try:
        result = await asyncio.to_thread(store.put_fact, workspace_id, body)
        return result
    except UnknownFactCategoryError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "UNKNOWN_KNOWLEDGE_CATEGORY",
                "message": str(e),
                "details": {"category": e.category, "valid_categories": e.valid_categories},
            },
        ) from e


@router.delete("/facts/{fact_key}")
async def delete_fact(
    workspace_id: str,
    fact_key: str,
    store: Annotated[WorkspaceFactStore, Depends(get_knowledge_store)],
) -> dict:
    """Tombstone a fact — sets status to 'deleted'.

    Returns the deleted fact representation. Returns 204 No Content
    if no fact existed.
    (AC: 4)
    """
    result = await asyncio.to_thread(store.delete_fact, workspace_id, fact_key)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "FACT_NOT_FOUND",
                "message": f"Fact not found: {fact_key}",
            },
        )
    return result.model_dump()


@router.get("/facts")
async def list_facts(
    workspace_id: str,
    store: Annotated[WorkspaceFactStore, Depends(get_knowledge_store)],
    category: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> KnowledgeListResponse:
    """Paginated list of facts for the workspace.

    Supports filtering by ``category`` and cursor-based pagination.
    (AC: 5)
    """
    result = await asyncio.to_thread(
        store.list_facts,
        workspace_id,
        category=category,
        cursor=cursor,
        limit=limit,
    )
    return result


@router.post("/facts:batch")
async def batch_put(
    workspace_id: str,
    requests: list[KnowledgeFactWriteRequest],
    store: Annotated[WorkspaceFactStore, Depends(get_knowledge_store)],
) -> list[KnowledgeFactWriteResponse]:
    """Bulk write facts — each processed atomically.

    Returns a list of per-result statuses.
    (AC: 6)
    """
    results = await asyncio.to_thread(
        store.batch_put,
        workspace_id,
        requests,
    )
    return results


@router.get("/facts/{fact_key}/history")
async def get_fact_history(
    workspace_id: str,
    fact_key: str,
    store: Annotated[WorkspaceFactStore, Depends(get_knowledge_store)],
) -> list[dict]:
    """Return the append-only version history for a fact.

    Each entry is the full ``KnowledgeFact`` state at that version.
    (AC: 12)
    """
    history = await asyncio.to_thread(store.get_history, workspace_id, fact_key)
    return [f.model_dump() for f in history]


# ── Conflict endpoints ────────────────────────────────────────────────────


@router.get("/facts/conflicts")
async def list_conflicts(
    workspace_id: str,
    store: Annotated[WorkspaceFactStore, Depends(get_knowledge_store)],
) -> list[dict]:
    """List unresolved conflicts for a workspace.

    Returns workspace-scoped list of pending conflicts sorted by
    timestamp descending.
    (AC: 4, 8)
    """
    conflicts = await asyncio.to_thread(store.review_queue.list_conflicts, workspace_id)
    return conflicts


@router.post("/facts/{fact_key}/resolve")
async def resolve_conflict(
    workspace_id: str,
    fact_key: str,
    body: KnowledgeConflictResolutionRequest,
    store: Annotated[WorkspaceFactStore, Depends(get_knowledge_store)],
) -> dict:
    """Resolve a fact conflict: apply the chosen candidate as a new fact version.

    Args:
        choice: One of ``canonical``, ``reject``, ``stale``.
        candidate_index: Index of the winning candidate (for ``canonical``).

    Returns:
        Dict with conflict resolution result and applied fact.
    (AC: 6, 8)
    """
    result = await asyncio.to_thread(
        store.resolve_conflict,
        workspace_id,
        fact_key,
        body.choice,
        body.candidate_index,
    )

    error = result.get("error")
    if error == "conflict_not_found":
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "CONFLICT_NOT_FOUND",
                "message": f"No unresolved conflict found for fact '{fact_key}'",
            },
        )
    if error == "INVALID_CANDIDATE_INDEX":
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "INVALID_CANDIDATE_INDEX",
                "message": f"candidate_index must be 0..{result['candidate_count'] - 1}",
            },
        )
    return result

"""Search endpoint — GET /v1/search.

Merges full-text and vector (semantic) results via RRF (Reciprocal Rank
Fusion) through ``WikiQuery.search()``.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Query, Request

from llm_wiki.api.models import SearchResponse, SearchResultItem
from llm_wiki.deps import get_wiki
from llm_wiki.query.log import QueryLogEntry
from llm_wiki.query.search import WikiQuery

logger = logging.getLogger(__name__)
router = APIRouter(tags=["search"])


@router.get("/v1/search")
async def search(
    request: Request,
    q: str = Query(..., description="Search query text"),
    domain: str | None = Query(default=None, description="Optional domain filter"),
    limit: int = Query(default=10, ge=1, le=100, description="Max results"),
    wiki: WikiQuery = Depends(get_wiki),
) -> SearchResponse:
    """Search the wiki — merged full-text + vector results.

    Vector search is always active; there is no feature flag.
    """
    # Search runs synchronously inside the indexing libs -> offload to thread.
    pages = await asyncio.to_thread(
        wiki.search,
        q,
        domain=domain,
        limit=limit,
    )

    results = [
        SearchResultItem(
            page_id=p.get("page_id", p.get("id", "")),
            title=p.get("title", ""),
            confidence=p.get("confidence", 0.0),
            score=p.get("score", 0.0),
        )
        for p in pages
    ]

    # Log search to query log (non-blocking, fire-and-forget)
    store = getattr(request.app.state, "query_log", None)
    if store is not None:
        confidence_avg = (
            sum(r.confidence for r in results) / len(results) if results else None
        )
        try:
            entry = QueryLogEntry(
                query_text=q,
                depth="standard",
                domains=[domain] if domain else [],
                result_count=len(results),
                confidence_avg=confidence_avg,
            )
            asyncio.create_task(asyncio.to_thread(store.log, entry))
        except Exception:
            pass

    return SearchResponse(results=results)

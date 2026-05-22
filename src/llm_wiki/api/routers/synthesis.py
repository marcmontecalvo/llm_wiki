"""Synthesis cache API router.

Provides endpoints for:
  - GET /v1/synthesis — list all synthesis cache pages (with cache hit detection)
  - GET /v1/synthesis/{query_hash} — look up a specific synthesis page by hash
  - GET /v1/pages?kind=synthesis — already handled via the pages router's list endpoint

The synthesis cache page listing checks current queries for potential cache hits.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from llm_wiki.deps import get_wiki
from llm_wiki.query.search import WikiQuery

logger = logging.getLogger(__name__)

router = APIRouter(tags=["synthesis"])


@router.get("/v1/synthesis")
async def list_synthesis(
    kind: str | None = Query(default=None, description="Filter by kind (always 'synthesis')"),
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
    wiki: WikiQuery = Depends(get_wiki),
) -> dict:
    """List synthesis cache pages.

    Returns all cached synthesis pages with their metadata.
    Optionally accepts a query parameter for cache hit detection.
    """
    wiki_base = wiki.wiki_base
    from llm_wiki.synthesis.cache import SynthesisCacheJob  # noqa: PLC0415

    cache_job = SynthesisCacheJob(
        wiki_base=wiki_base,
        log_db=wiki_base / "state" / "query_log.db",
    )

    pages = cache_job.list_synthesis_pages()
    pages = pages[:limit]

    return {"kind": "synthesis", "pages": pages, "total": len(pages)}


@router.get("/v1/synthesis/{query_hash}")
async def get_synthesis(
    query_hash: str,
    wiki: WikiQuery = Depends(get_wiki),
) -> dict:
    """Get a synthesis cache page by query hash.

    Returns the full synthesis page content for a cached query.
    """
    wiki_base = wiki.wiki_base
    from llm_wiki.synthesis.cache import SynthesisCacheJob  # noqa: PLC0415

    cache_job = SynthesisCacheJob(
        wiki_base=wiki_base,
        log_db=wiki_base / "state" / "query_log.db",
    )

    page = cache_job.find_page_by_hash(query_hash)
    if page is None:
        from llm_wiki.exceptions import WikiNotFoundError  # noqa: PLC0415

        raise WikiNotFoundError(f"Synthesis cache page not found for hash: {query_hash}")

    return page

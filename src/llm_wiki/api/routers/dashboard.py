"""Dashboard REST endpoint — GET /v1/domains/{domain}/dashboard."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from llm_wiki.api.errors import wiki_error_to_http
from llm_wiki.api.services.dashboard import get_domain_dashboard
from llm_wiki.deps import get_wiki
from llm_wiki.exceptions import DomainUnknownError
from llm_wiki.query.search import WikiQuery

router = APIRouter(tags=["dashboard"])

# Domain identifiers are slug-like: [a-z0-9_-], 1–64 chars
_DOMAIN_PATH = Annotated[str, Path(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]


@router.get("/v1/domains/{domain}/dashboard")
async def get_domain_dashboard_endpoint(
    domain: Annotated[str, _DOMAIN_PATH],
    wiki: WikiQuery = Depends(get_wiki),
) -> dict:
    """Get per-domain health dashboard.

    Returns page count, confidence distribution, recent changes,
    low confidence count, stale count, and last governance run.
    """
    try:
        wiki_root = wiki.wiki_base
        response = get_domain_dashboard(domain, wiki_root)
        return response.model_dump()
    except DomainUnknownError as e:
        raise wiki_error_to_http(e) from e

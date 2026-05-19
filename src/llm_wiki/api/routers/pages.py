"""Pages endpoints — GET /v1/pages/{page_id} and GET /v1/pages.

Page content is read from the filesystem under ``wiki_system/domains/``.
The list endpoint uses the MetadataIndex with cursor-based pagination.
"""

from __future__ import annotations

import asyncio
import base64

from fastapi import APIRouter, Depends, Query

from llm_wiki.api.models import PageListResponse, PageResponse
from llm_wiki.deps import get_wiki
from llm_wiki.exceptions import WikiNotFoundError
from llm_wiki.query.search import WikiQuery
from llm_wiki.utils.frontmatter import parse_frontmatter

router = APIRouter(tags=["pages"])


def _encode_cursor(offset: int) -> str:
    """Encode an integer offset as a base64 cursor token."""
    return base64.b64encode(str(offset).encode()).decode()


def _decode_cursor(cursor: str) -> int:
    """Decode a base64 cursor token back to an integer offset."""
    try:
        return int(base64.b64decode(cursor).decode())
    except Exception:
        raise ValueError("Invalid cursor")


@router.get("/v1/pages/{page_id}", response_model=PageResponse)
async def read_page(
    page_id: str,
    wiki: WikiQuery = Depends(get_wiki),
) -> PageResponse:
    """Read a single page by ID.

    Returns full content plus frontmatter provenance metadata.
    Raises WikiNotFoundError (404) if page doesn't exist.
    """
    # Try to locate the page file on the filesystem.
    wiki_base = wiki.wiki_base

    # Check domains first
    found = False
    content = ""
    frontmatter_dict: dict = {}

    for domain_dir in (wiki_base / "domains").iterdir():
        if not domain_dir.is_dir():
            continue
        page_file = domain_dir / "pages" / f"{page_id}.md"
        if page_file.exists():
            content = await asyncio.to_thread(page_file.read_text, encoding="utf-8")
            frontmatter_dict, content = parse_frontmatter(content)
            found = True
            break

    # Check shared directory
    if not found:
        shared_file = wiki_base / "shared" / f"{page_id}.md"
        if shared_file.exists():
            content = await asyncio.to_thread(shared_file.read_text, encoding="utf-8")
            frontmatter_dict, content = parse_frontmatter(content)
            found = True

    if not found:
        raise WikiNotFoundError(f"Page not found: {page_id}")

    return PageResponse(
        page_id=page_id,
        title=frontmatter_dict.get("title", page_id),
        content=content,
        frontmatter=frontmatter_dict,
        domain=frontmatter_dict.get("domain", "general"),
        kind=frontmatter_dict.get("kind", "page"),
        confidence=frontmatter_dict.get("confidence", 0.0),
    )


@router.get("/v1/pages", response_model=PageListResponse)
async def list_pages(
    domain: str | None = Query(default=None, description="Filter by domain"),
    kind: str | None = Query(default=None, description="Filter by kind"),
    cursor: str | None = Query(default=None, description="Pagination cursor"),
    limit: int = Query(default=50, ge=1, le=200, description="Page size"),
    wiki: WikiQuery = Depends(get_wiki),
) -> PageListResponse:
    """List pages with cursor-based pagination and optional filters.

    Reads from the MetadataIndex (not the filesystem directly for
    filtering since the search endpoint already applies metadata filters).
    """
    all_pages: list[dict] = []

    if domain or kind:
        # Use metadata index which already has filtered structures
        if domain:
            page_ids = wiki.metadata_index.by_domain.get(domain, set())
        else:
            page_ids = set(wiki.metadata_index.pages.keys())

        for pid in page_ids:
            meta = wiki.metadata_index.get_page(pid)
            if meta is None:
                continue
            if kind and meta.get("kind") != kind:
                continue
            all_pages.append(meta)
    else:
        # No filters — list all pages from metadata index
        all_pages = list(wiki.metadata_index.pages.values())

    # Apply cursor-based pagination
    offset = 0
    if cursor:
        try:
            offset = _decode_cursor(cursor)
        except ValueError:
            offset = 0

    total = len(all_pages)
    page_items = all_pages[offset : offset + limit]
    next_cursor = _encode_cursor(offset + limit) if (offset + limit) < total else None

    results = []
    for meta in page_items:
        results.append(
            PageResponse(
                page_id=meta.get("page_id", meta.get("id", "")),
                title=meta.get("title", ""),
                content="",
                frontmatter=meta,
                domain=meta.get("domain", "general"),
                kind=meta.get("kind", "page"),
                confidence=meta.get("confidence", 0.0),
            )
        )

    return PageListResponse(
        pages=results,
        next_cursor=next_cursor,
        total_hint=total,
    )

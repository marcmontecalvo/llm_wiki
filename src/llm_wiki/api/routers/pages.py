"""Pages endpoints — GET /v1/pages/{page_id} and GET /v1/pages.

Page content is read from the filesystem under ``wiki_system/domains/``.
The list endpoint uses the MetadataIndex with cursor-based pagination.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

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
        authority_score=frontmatter_dict.get("authority_score", 0.0),
    )


@router.get("/v1/pages", response_model=PageListResponse)
async def list_pages(
    domain: str | None = Query(default=None, description="Filter by domain"),
    kind: str | None = Query(default=None, description="Filter by kind"),
    updated_since: datetime | None = Query(
        default=None,
        description="Return only pages with updated_at after this ISO8601 timestamp",
    ),
    cursor: str | None = Query(default=None, description="Pagination cursor"),
    limit: int = Query(default=50, ge=1, le=200, description="Page size"),
    include_archived: bool = Query(default=False, description="Include archived pages in results"),
    wiki: WikiQuery = Depends(get_wiki),
) -> PageListResponse:
    """List pages with cursor-based pagination and optional filters.

    Archived pages are excluded by default.  Set ``include_archived=true``
    to include stale content in results.
    """
    page_items, next_cursor = await asyncio.to_thread(
        wiki.list_pages,
        domain=domain,
        kind=kind,
        updated_since=updated_since,
        cursor=cursor,
        limit=limit,
        include_archived=include_archived,
    )

    results = [
        PageResponse(
            page_id=meta.get("page_id", meta.get("id", "")),
            title=meta.get("title", ""),
            content="",
            frontmatter=meta,
            domain=meta.get("domain", "general"),
            kind=meta.get("kind", "page"),
            confidence=meta.get("confidence", 0.0),
            authority_score=meta.get("authority_score", 0.0),
        )
        for meta in page_items
    ]

    return PageListResponse(
        pages=results,
        next_cursor=next_cursor,
        total_hint=len(results),
    )


# ── Page write models ───────────────────────────────────────────────────────


class PageWriteRequest(BaseModel):
    """Body for page creation and update."""

    title: str = Field(max_length=200)
    content: str = ""
    domain: str = "general"
    kind: str = "page"
    confidence: float = 0.0
    authority_score: float = 0.0
    tags: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    updated_at: str = ""


@router.post("/v1/pages", response_model=PageResponse, status_code=201)
async def create_page(
    body: PageWriteRequest,
    wiki: WikiQuery = Depends(get_wiki),
) -> PageResponse:
    """Create a new wiki page.

    Writes markdown with front matter to the domain's pages directory.
    """
    wiki_base = wiki.wiki_base
    page_id = body.title.strip().lower().replace(" ", "-")

    return await _save_page(wiki_base, page_id, body)


@router.put("/v1/pages/{page_id}", response_model=PageResponse)
async def update_page(
    page_id: str,
    body: PageWriteRequest,
    wiki: WikiQuery = Depends(get_wiki),
) -> PageResponse:
    """Update an existing wiki page.

    Overwrites the markdown file with the updated content and front matter.
    """
    wiki_base = wiki.wiki_base
    return await _save_page(wiki_base, page_id, body)


async def _save_page(
    wiki_base: Path,
    page_id: str,
    body: PageWriteRequest,
) -> PageResponse:
    """Write page markdown with front matter."""
    # Validate domain
    domains_dir = wiki_base / "domains" / body.domain / "pages"
    if not domains_dir.exists():
        # Try to create domain dir structure
        try:
            domains_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise HTTPException(status_code=400, detail=f"Invalid domain: {e}")

    updated = datetime.now(UTC).isoformat()

    # Build front matter
    fm_lines = [
        "---",
        f"id: {page_id}",
        f"title: {body.title}",
        f"domain: {body.domain}",
        f"kind: {body.kind}",
        f"confidence: {body.confidence:.2f}",
        f"authority_score: {body.authority_score:.2f}",
        f"updated_at: {updated}",
    ]
    if body.tags:
        fm_lines.append("tags: [" + ", ".join(body.tags) + "]")
    if body.sources:
        fm_lines.append("sources: [" + ", ".join(body.sources) + "]")
    fm_lines.append("---")

    fm_text = "\n".join(fm_lines)
    content_text = (body.content or "").lstrip("\n")

    page_file = domains_dir / f"{page_id}.md"
    await asyncio.to_thread(page_file.write_text, fm_text + "\n" + content_text, encoding="utf-8")

    # Read back for response
    content = await asyncio.to_thread(page_file.read_text, encoding="utf-8")
    fm_dict, body_text = parse_frontmatter(content)

    return PageResponse(
        page_id=page_id,
        title=fm_dict.get("title", page_id),
        content=body_text,
        frontmatter=fm_dict,
        domain=fm_dict.get("domain", "general"),
        kind=fm_dict.get("kind", "page"),
        confidence=fm_dict.get("confidence", 0.0),
        authority_score=fm_dict.get("authority_score", 0.0),
    )

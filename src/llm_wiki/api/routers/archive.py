"""Archive listing REST endpoint — GET /v1/domains/{domain}/archive."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from llm_wiki.deps import get_wiki
from llm_wiki.query.search import WikiQuery

router = APIRouter(tags=["archive"])


@router.get("/v1/domains/{domain}/archive")
def list_archive(
    domain: str,
    wiki: WikiQuery = Depends(get_wiki),
) -> dict[str, Any]:
    """List archived pages for a domain."""
    wiki_base = wiki.wiki_base
    archive_dir = wiki_base / "domains" / domain / "archive"

    pages: list[dict[str, Any]] = []
    if archive_dir.exists():
        for page_file in sorted(archive_dir.glob("*.md")):
            try:
                content = page_file.read_text(encoding="utf-8")
                from llm_wiki.utils.frontmatter import parse_frontmatter  # noqa: PLC0415

                metadata, _ = parse_frontmatter(content)
                pages.append(
                    {
                        "page_id": metadata.get("id", page_file.stem),
                        "title": metadata.get("title", page_file.stem),
                        "archived_at": metadata.get("archived_at"),
                        "updated_at": metadata.get("updated_at"),
                    }
                )
            except Exception as e:
                from logging import getLogger  # noqa: PLC0415

                getLogger(__name__).warning("Failed to parse %s: %s", page_file, e)

    return {"kind": "archive", "pages": pages, "domain": domain, "total": len(pages)}

"""Domain listing endpoint.

Route:
    - GET /v1/domains
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends

from llm_wiki.api.models import DomainInfo, DomainListResponse
from llm_wiki.deps import get_wiki
from llm_wiki.query.search import WikiQuery

router = APIRouter(prefix="/v1", tags=["domains"])


def _count_md_files(dir_path: Path) -> int:
    """Count .md files in a directory (for disk I/O via asyncio.to_thread)."""
    return len(list(dir_path.glob("*.md")))


@router.get("/domains", response_model=DomainListResponse)
async def list_domains(wiki: WikiQuery = Depends(get_wiki)) -> DomainListResponse:
    """Return configured domains with page_count and last_updated metadata."""
    wiki_base = wiki.wiki_base

    # Load config to get domain list (disk I/O)
    try:
        from llm_wiki.config.loader import load_config

        config = await asyncio.to_thread(load_config, wiki_base / "config")
        domain_configs = config.domains.domains
    except Exception:
        domain_configs = []

    result: list[DomainInfo] = []

    for dc in domain_configs:
        domain_id = dc.id
        scope = getattr(dc, "title", "shared")

        # Page count from metadata index (in-memory)
        page_count = 0
        try:
            mi = wiki.metadata_index
            pages_in_domain = mi.by_domain.get(domain_id, set())
            page_count = len(pages_in_domain)
        except Exception:
            # Fallback: count markdown files on disk (disk I/O)
            pages_dir = wiki_base / "domains" / domain_id / "pages"
            if await asyncio.to_thread(pages_dir.exists):
                page_count = await asyncio.to_thread(_count_md_files, pages_dir)
            # No shared-space fallback — zero-indexed is the honest answer

        # Last updated from index (in-memory)
        last_updated = None
        try:
            mi = wiki.metadata_index
            pages_in_domain = mi.by_domain.get(domain_id, set())
            if pages_in_domain:
                most_recent = None
                for pid in pages_in_domain:
                    meta = mi.pages.get(pid, {})
                    updated = meta.get("updated_at")
                    if updated:
                        if most_recent is None or updated > most_recent:
                            most_recent = updated
                last_updated = most_recent
        except Exception:
            last_updated = None

        result.append(
            DomainInfo(
                name=domain_id,
                scope=scope,
                page_count=page_count,
                last_updated=last_updated,
            )
        )

    return DomainListResponse(domains=result)

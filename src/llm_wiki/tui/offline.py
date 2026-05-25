"""Offline file-system fallback reader (scan wiki pages from disk)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


@dataclass
class OfflinePage:
    page_id: str
    title: str
    domain: str
    kind: str
    updated_at: str
    content: str
    frontmatter: dict[str, Any]


class OfflineReader:
    """Read wiki pages directly from the filesystem when the daemon is offline."""

    def __init__(self, wiki_base: str | Path) -> None:
        self.wiki_base = Path(wiki_base)

    def list_pages(self, domain: str | None = None, kind: str | None = None) -> list[OfflinePage]:
        pages: list[OfflinePage] = []
        domains_dir = self.wiki_base / "domains"
        if not domains_dir.is_dir():
            return pages
        for domain_dir in sorted(domains_dir.iterdir()):
            if not domain_dir.is_dir():
                continue
            if domain and domain_dir.name != domain:
                continue
            pages_dir = domain_dir / "pages"
            if not pages_dir.is_dir():
                continue
            for md_file in sorted(pages_dir.glob("*.md")):
                fm, body = parse_frontmatter(md_file.read_text(encoding="utf-8"))
                if kind and fm.get("kind") != kind:
                    continue
                pages.append(
                    OfflinePage(
                        page_id=md_file.stem,
                        title=fm.get("title", md_file.stem),
                        domain=fm.get("domain", domain_dir.name),
                        kind=fm.get("kind", "page"),
                        updated_at=fm.get("updated_at", ""),
                        content=body,
                        frontmatter=fm,
                    )
                )
        return pages

    def read_page(self, page_id: str) -> OfflinePage | None:
        # Check domain directories first
        domains_dir = self.wiki_base / "domains"
        if domains_dir.is_dir():
            for domain_dir in domains_dir.iterdir():
                md_file = domain_dir / "pages" / f"{page_id}.md"
                if md_file.exists():
                    fm, body = parse_frontmatter(md_file.read_text(encoding="utf-8"))
                    return OfflinePage(
                        page_id=md_file.stem,
                        title=fm.get("title", md_file.stem),
                        domain=fm.get("domain", domain_dir.name),
                        kind=fm.get("kind", "page"),
                        updated_at=fm.get("updated_at", ""),
                        content=body,
                        frontmatter=fm,
                    )
        # Check shared directory
        shared_file = self.wiki_base / "shared" / f"{page_id}.md"
        if shared_file.exists():
            fm, body = parse_frontmatter(shared_file.read_text(encoding="utf-8"))
            return OfflinePage(
                page_id=shared_file.stem,
                title=fm.get("title", shared_file.stem),
                domain=fm.get("domain", "shared"),
                kind=fm.get("kind", "page"),
                updated_at=fm.get("updated_at", ""),
                content=body,
                frontmatter=fm,
            )
        return None

    def list_domains(self) -> list[dict]:
        """Return list of discovered domain dirs with page counts."""
        domains: list[dict] = []
        domains_dir = self.wiki_base / "domains"
        if not domains_dir.is_dir():
            return domains
        for dd in sorted(domains_dir.iterdir()):
            if dd.is_dir():
                count = (dd / "pages").glob("*.md")
                domains.append({"name": dd.name, "page_count": len(list(count))})
        return domains

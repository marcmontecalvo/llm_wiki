"""Workspace-scoped knowledge service.

Combines wiki pages and workspace facts under a single ``workspace_id``
boundary so Homefront integration clients can query the full knowledge
surface without knowing which sub-system holds each piece.

The workspace is the **primary** isolation boundary for facts
(hard storage-level). For pages it is a **policy filter** atop
domain scoping (shared domains are visible to all workspaces;
personal domains are scoped to the owning workspace).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from llm_wiki.config.loader import WikiConfig
from llm_wiki.governance.staleness import StalenessDetector
from llm_wiki.knowledge.storage import WorkspaceFactStore
from llm_wiki.query.search import WikiQuery

logger = logging.getLogger(__name__)

# Staleness threshold (days) — pages/facts older than this are "stale".
_STALE_DAYS = 90


@dataclass
class KnowledgeQueryResult:
    """Combined query result from pages and facts."""

    query: str
    results: list[dict[str, Any]] = field(default_factory=list)
    page_count: int = 0
    fact_count: int = 0
    timed_out: bool = False


@dataclass
class KnowledgeSearchResult:
    """Combined search result from pages and facts."""

    query: str
    results: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0


class WorkspaceKnowledgeService:
    """Orchestrates wiki pages and workspace facts under a common API."""

    def __init__(
        self,
        wiki: WikiQuery,
        store: WorkspaceFactStore,
        wiki_config: WikiConfig | None = None,
    ) -> None:
        self._wiki = wiki
        self._store = store
        self._wiki_config = wiki_config

    # ── Domain-scoped page helpers ──────────────────────────────────────

    def _scope_pages_by_workspace(
        self,
        query: str,
        depth: str = "standard",
        profile_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return wiki pages scoped to a workspace.

        Pages from shared domains are visible to all workspaces.
        Pages from personal domains are scoped to the owning workspace.

        Because domain config tracks ``owner`` (profile_id) rather than
        ``owner_workspace``, personal pages match by profile.  Shared
        domain pages are always visible.  Domain filtering applies only
        to wiki pages, not facts.
        """
        allowed_domains: set[str] | None = None
        if self._wiki_config is not None and self._wiki_config.domains is not None:
            domain_list = self._wiki_config.domains.domains
            allowed_ids: set[str] = {d.id for d in domain_list if d.scope == "shared"}
            if profile_id:
                allowed_ids |= {
                    d.id for d in domain_list if d.scope == "personal" and d.owner == profile_id
                }
            allowed_domains = allowed_ids

        if depth == "deep":
            # Use metadata listing for completeness
            page_list, _ = self._wiki.list_pages(limit=2000)
            results: list[dict[str, Any]] = []
            for meta in page_list:
                domain = meta.get("domain", "general")
                if allowed_domains is not None and domain not in allowed_domains:
                    continue
                entry: dict[str, Any] = {**meta, "source": "page"}
                results.append(entry)
            return results

        # Use the index-backed search
        pages = self._wiki.search(
            query,
            limit=50,
            scope_to_profile=profile_id,
            include_archived=False,
        )
        matched: list[dict[str, Any]] = []
        for p in pages:
            domain = p.get("domain", p.get("metadata", {}).get("domain", "general"))
            if allowed_domains is not None and domain not in allowed_domains:
                continue
            matched.append(
                {
                    "page_id": p.get("page_id", p.get("id", "")),
                    "title": p.get("title", ""),
                    "domain": domain,
                    "confidence": p.get("confidence", p.get("score", 0.0)),
                    "score": p.get("score", 0.0),
                    "source": "page",
                }
            )
        return matched

    def _scope_facts_by_workspace(
        self,
        workspace_id: str,
        query_text: str,
    ) -> list[dict[str, Any]]:
        """Search facts within a workspace by value text.

        Scans all facts for the workspace and ranks by keyword match.
        """
        facts_list = self._store.list_facts(workspace_id, limit=5000)
        if not query_text:
            return [
                {
                    "fact_key": f.key,
                    "value": f.value,
                    "category": f.category,
                    "confidence": f.confidence,
                    "source": "fact",
                }
                for f in facts_list.facts
                if f.status == "active"
            ]

        query_lower = query_text.lower()
        matched: list[dict[str, Any]] = []
        for f in facts_list.facts:
            if f.status not in ("active", "pending_review"):
                continue
            key_str = f.key.lower()
            value_str = str(f.value).lower()
            if query_lower in key_str or query_lower in value_str:
                matched.append(
                    {
                        "fact_key": f.key,
                        "value": f.value,
                        "category": f.category,
                        "confidence": f.confidence,
                        "source": "fact",
                    }
                )

        # Key matches ranked above value matches
        matched.sort(
            key=lambda r: 1.0 if query_lower in r["fact_key"].lower() else 0.5,
            reverse=True,
        )
        return matched

    # ── Content helpers ─────────────────────────────────────────────────

    @staticmethod
    def _read_page_content(page_id: str, wiki_base: Path | str) -> str:
        """Read page content from filesystem (sync, suitable for to_thread)."""
        wiki_base = Path(wiki_base)
        domains_dir = wiki_base / "domains"
        if domains_dir.is_dir():
            for domain_dir in domains_dir.iterdir():
                if not domain_dir.is_dir() or domain_dir.is_symlink():
                    continue
                page_file = domain_dir / "pages" / f"{page_id}.md"
                if page_file.exists():
                    return page_file.read_text(encoding="utf-8")
        else:
            logger.debug("No domains directory at %s", domains_dir)
        shared_file = wiki_base / "shared" / f"{page_id}.md"
        if shared_file.exists():
            return shared_file.read_text(encoding="utf-8")
        return ""

    # ── Public API ─────────────────────────────────────────────────────

    async def query(
        self,
        workspace_id: str,
        query_text: str,
        depth: str = "standard",
        profile_id: str | None = None,
    ) -> KnowledgeQueryResult:
        """Combine wiki pages and workspace facts for a workspace.

        Returns combined results from both surfaces.
        """
        pages = await asyncio.to_thread(
            self._scope_pages_by_workspace, query_text, depth, profile_id
        )
        facts = await asyncio.to_thread(self._scope_facts_by_workspace, workspace_id, query_text)

        combined = pages + facts
        return KnowledgeQueryResult(
            query=query_text,
            results=[dict(r) for r in combined],
            page_count=len(pages),
            fact_count=len(facts),
        )

    async def search(
        self,
        workspace_id: str,
        query_text: str,
        profile_id: str | None = None,
        limit: int = 20,
    ) -> KnowledgeSearchResult:
        """Fulltext + vector search scoped to a workspace.

        Domain remains categorization only — not a security boundary
        for facts.  Pages follow domain scoping but workspace is the
        primary filter.
        """
        pages = await asyncio.to_thread(
            self._scope_pages_by_workspace, query_text, "standard", profile_id
        )
        facts = await asyncio.to_thread(self._scope_facts_by_workspace, workspace_id, query_text)

        combined = pages + facts
        combined.sort(
            key=lambda r: r.get("score", r.get("confidence", 0.0) or 0.0) or 0.0,
            reverse=True,
        )
        return KnowledgeSearchResult(
            query=query_text,
            results=[dict(r) for r in combined[:limit]],
            total=len(combined),
        )

    async def get_page(
        self,
        workspace_id: str,
        page_id: str,
    ) -> dict[str, Any] | None:
        """Return a page if it belongs to the workspace, else ``None``.

        Scoping follows the same rules as ``_scope_pages_by_workspace``:
        shared pages are always visible, personal pages follow domain
        ownership.

        For the workspace-directory approach (pages stored under
        ``workspaces/{workspace_id}/``), contents are pulled from that
        directory first.
        """
        page_meta = self._wiki.get_page(page_id)
        if page_meta is None:
            return None

        domain = page_meta.get("domain", "general")
        wiki_base = Path(self._wiki.wiki_base)

        # Try workspace-direct storage: workspaces/{workspace_id}/{domain}/{page_id}.md
        # This approach scopes pages by physical location rather than
        # domain metadata alone.
        workspace_pages_dir = wiki_base / "workspaces" / workspace_id / "domains" / domain / "pages"
        workspace_path = workspace_pages_dir / f"{page_id}.md"

        is_scoped = False
        if self._wiki_config is not None and self._wiki_config.domains is not None:
            for d in self._wiki_config.domains.domains:
                if d.id == domain:
                    if d.scope == "shared":
                        is_scoped = True  # shared = visible to all
                    elif d.scope == "personal":
                        # Personal pages only visible if stored in
                        # a workspace directory that matches.
                        if workspace_path.exists():
                            is_scoped = True
                    break

        if not is_scoped:
            # Check workspace directory fallback: if no domain config
            # matches, only allow if workspace-specific directory exists
            if workspace_path.exists():
                is_scoped = True
            else:
                # Without an explicit domain config, check if the page
                # exists in top-level domains/shared (legacy layout).
                domain_dir = wiki_base / "domains" / domain
                legacy_path = domain_dir / f"{page_id}.md"
                shared_path = wiki_base / "shared" / f"{page_id}.md"
                if legacy_path.is_file() or shared_path.is_file():
                    is_scoped = True
            if not is_scoped:
                return None

        content = await asyncio.to_thread(self._read_page_content, page_id, wiki_base)
        return {
            "page_id": page_id,
            "title": page_meta.get("title", page_id),
            "domain": domain,
            "content": content,
            "frontmatter": page_meta,
            "workspace_id": workspace_id,
        }

    async def get_conflicts(self, workspace_id: str) -> list[dict[str, Any]]:
        """Return unresolved conflicts for the workspace."""
        return await asyncio.to_thread(
            self._store.review_queue.list_conflicts,
            workspace_id,
            unresolved_only=True,
        )

    async def get_review_items(self, workspace_id: str) -> list[dict[str, Any]]:
        """Return pending review items for the workspace.

        Includes facts with ``status == "pending_review"`` and
        unresolved conflicts.
        """
        facts_list = await asyncio.to_thread(self._store.list_facts, workspace_id, limit=5000)
        pending: list[dict[str, Any]] = [
            {
                "fact_key": f.key,
                "category": f.category,
                "value": f.value,
                "status": f.status,
                "source": "fact",
            }
            for f in facts_list.facts
            if f.status == "pending_review"
        ]

        conflicts = await self.get_conflicts(workspace_id)
        hanging: list[dict[str, Any]] = []
        for c in conflicts:
            hanging.append(
                {
                    "fact_key": c.get("key", ""),
                    "category": "",
                    "value": {},
                    "source": "conflict",
                    "requires_review": c.get("requires_review", True),
                    "resolved": c.get("resolved", False),
                }
            )
        pending.extend(hanging)
        return pending

    async def export(
        self,
        workspace_id: str,
        fmt: str = "json",
    ) -> dict[str, Any]:
        """Export combined wiki pages and facts scoped to a workspace.

        Returns a structured dict containing both surfaces.
        """
        pages, _ = await asyncio.to_thread(self._wiki.list_pages, limit=10000)
        facts_list = await asyncio.to_thread(self._store.list_facts, workspace_id, limit=10000)

        return {
            "workspace_id": workspace_id,
            "exported_at": datetime.now(tz=UTC).isoformat(),
            "format": fmt,
            "pages": [
                {
                    "page_id": p.get("page_id", p.get("id", "")),
                    "domain": p.get("domain", "general"),
                    "metadata": p,
                }
                for p in pages
            ],
            "facts": [f.model_dump() for f in facts_list.facts if f.status == "active"],
        }

    async def list_stale(
        self,
        workspace_id: str,
        threshold_days: int = _STALE_DAYS,
    ) -> list[dict[str, Any]]:
        """Return pages and facts past their staleness threshold.

        Pages are checked using ``StalenessDetector``.  Facts are
        checked against their ``updated_at`` field.
        """
        stale: list[dict[str, Any]] = []
        cutoff = datetime.now(tz=UTC) - timedelta(days=threshold_days)

        # Stale wiki pages (all domains — workspace scoping via domain)
        detector = StalenessDetector()
        _wiki_base = Path(self._wiki.wiki_base)
        for report in detector.analyze_all(_wiki_base, min_score=0.2):
            if report.age_days is not None and report.age_days > threshold_days:
                stale.append(
                    {
                        "page_id": report.page_id,
                        "type": "page",
                        "staleness_score": report.score,
                        "age_days": report.age_days,
                        "reasons": report.reasons,
                    }
                )

        # Stale facts from the workspace
        facts_list = await asyncio.to_thread(self._store.list_facts, workspace_id, limit=10000)
        for f in facts_list.facts:
            f_updated = f.updated_at
            if f_updated.tzinfo is None:
                f_updated = f_updated.replace(tzinfo=UTC)
            if f_updated < cutoff:
                stale.append(
                    {
                        "fact_key": f.key,
                        "type": "fact",
                        "last_updated": f.updated_at.isoformat(),
                        "age_days": (datetime.now(tz=UTC) - f_updated).days,
                    }
                )

        stale.sort(key=lambda r: r.get("age_days", 0), reverse=True)
        return stale

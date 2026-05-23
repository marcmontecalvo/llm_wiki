"""Unified search interface for wiki queries."""

import base64
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llm_wiki.index.fulltext import FulltextIndex
from llm_wiki.index.metadata import MetadataIndex
from llm_wiki.index.vector import VectorIndex

logger = logging.getLogger(__name__)

_RRF_K = 60  # standard Reciprocal Rank Fusion constant


class WikiQuery:
    """Unified query interface for searching wiki pages."""

    def __init__(
        self,
        wiki_base: Path | None = None,
        index_dir: Path | None = None,
        wiki_config: Any = None,
    ):
        """Initialize wiki query interface.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)
            index_dir: Directory for indexes (defaults to wiki_system/index)
        """
        self.wiki_base = wiki_base or Path("wiki_system")
        self.index_dir = index_dir or (self.wiki_base / "index")

        # Initialize indexes
        self.metadata_index = MetadataIndex(index_dir=self.index_dir)
        self.fulltext_index = FulltextIndex(index_dir=self.index_dir)
        self.vector_index = VectorIndex(index_dir=self.index_dir)

        # Central lock registry -- one lock per incrementally-written index
        # backlinks and graph_edges are rebuild-only (derived indexes); they
        # are never written by add_page()/remove_page().  Their exclusivity
        # is guaranteed by IndexRebuildJob holding all three locks.
        self._index_locks: dict[str, threading.Lock] = {
            "fulltext": threading.Lock(),
            "vector": threading.Lock(),
            "metadata": threading.Lock(),
        }

        self._load_indexes()
        self._wiki_config = wiki_config

    def acquire_all_locks(self) -> None:
        """Acquire all index locks. Used by IndexRebuildJob before full rebuild."""
        for lock in self._index_locks.values():
            lock.acquire()

    def release_all_locks(self) -> None:
        """Release all index locks. Called in IndexRebuildJob.execute() finally block."""
        for lock in self._index_locks.values():
            lock.release()

    def reload_vector_index(self) -> None:
        """Reload FAISS index from disk into memory. Called after IndexRebuildJob completes."""
        with self._index_locks["vector"]:
            self.vector_index.load()

    def _load_indexes(self) -> None:
        """Load all indexes from disk at startup."""
        try:
            self.metadata_index.load()
            self.fulltext_index.load()
            self.vector_index.load()
            logger.info("Loaded wiki indexes")
        except Exception as e:
            logger.warning(f"Failed to load indexes: {e}")

    def _resolve_search_domains(
        self,
        domain: str | None,
        scope_to_profile: str | None,
    ) -> list[str] | None:
        """Return list of domain IDs to search, or ``None`` to skip filtering.

        When ``scope_to_profile`` is set but config is ``None``, returns
        an empty list (fail-closed) to prevent leaking personal-domain
        content through a missing-config path.

        When ``scope_to_profile`` is set AND ``domain`` is also set,
        the requested domain is intersected with the caller's allowed
        domains to prevent bypassing personal-domain ownership checks.

        Logic lives exclusively here — never duplicate in routes/tools.
        """
        if self._wiki_config is None or self._wiki_config.domains is None:
            if scope_to_profile is not None:
                # Profile scoping requested but config missing — fail-closed
                return []
            # No scope request, no config — skip filtering (backward compat)
            if domain is not None:
                return [domain]
            return None

        all_domains_cfg = self._wiki_config.domains.domains

        # Compute the caller's allowed set of domains
        allowed: set[str] = set()
        if scope_to_profile is None:
            # No profile filter: search all configured domains
            allowed = {d.id for d in all_domains_cfg}
        else:
            # Profile filter: shared domains + this profile's personal domain(s)
            for d in all_domains_cfg:
                if d.scope == "shared":
                    allowed.add(d.id)
                elif d.scope == "personal" and d.owner == scope_to_profile:
                    allowed.add(d.id)

        if domain is not None:
            # Explicit domain: intersect with allowed set
            if domain in allowed:
                return [domain]
            return []  # unauthorized explicit domain

        return list(allowed)

    def search(
        self,
        query: str | None = None,
        tags: list[str] | None = None,
        kind: str | None = None,
        domain: str | None = None,
        limit: int = 10,
        scope_to_profile: str | None = None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        """Search for wiki pages.

        Combines metadata, fulltext, and vector (semantic) search. If query
        is provided, merges fulltext and vector results via Reciprocal Rank
        Fusion, then applies metadata filters.

        Args:
            query: Search query text
            tags: Filter by tags
            kind: Filter by page kind
            domain: Filter by domain
            limit: Max results
            scope_to_profile: Scope to a user profile's domains
            include_archived: When False (default), exclude archived pages

        Returns:
            List of page result dicts
        """
        allowed_domains: set[str] | None = None
        resolved = self._resolve_search_domains(domain, scope_to_profile)
        if resolved is not None and resolved != []:
            allowed_domains = set(resolved)
        elif resolved == []:
            # Explicitly unauthorized — empty list means zero access
            allowed_domains = set()
        else:
            # None — no domain filtering
            allowed_domains = None

        if query:
            # Push domain filter into index search to avoid in-scope hits being
            # pushing underneath the top-N window by out-of-scope results.
            if allowed_domains is not None:
                ft_results: list[dict[str, Any]] = []
                vec_results: list[dict[str, Any]] = []
                # Sort domains for stable, deterministic concat order;
                # set order is undefined and would bias RRF ranks.
                for d in sorted(allowed_domains):
                    ft_results.extend(self.fulltext_index.search(query, domain=d, limit=limit))
                    vec_results.extend(self.vector_index.search(query, domain=d, limit=limit))
            else:
                ft_results = self.fulltext_index.search(query, domain=None, limit=limit * 2)
                vec_results = self.vector_index.search(query, domain=None, limit=limit * 2)

            # Reciprocal Rank Fusion
            rrf_scores: dict[str, float] = {}
            for rank, r in enumerate(ft_results + vec_results):
                pid = r["page_id"]
                rrf_scores[pid] = rrf_scores.get(pid, 0.0) + 1.0 / (_RRF_K + rank + 1)

            # Collect candidate page_ids from fused ranking
            candidate_ids = sorted(rrf_scores, key=lambda k: rrf_scores[k], reverse=True)
        else:
            candidate_ids = list(self.metadata_index.pages.keys())

        # Apply metadata filters including domain scoping
        filtered_results = []
        for page_id in candidate_ids:
            metadata = self.metadata_index.get_page(page_id)
            if not metadata:
                continue
            # Exclude archived pages unless explicitly included
            if not include_archived and metadata.get("archived"):
                continue
            page_domain = metadata.get("domain", "general")

            # Scope filtering: page must be in a domain the caller is allowed to see
            if allowed_domains is not None:
                if page_domain not in allowed_domains:
                    continue
            if kind and metadata.get("kind") != kind:
                continue
            if tags:
                page_tags = {str(t).lower() for t in metadata.get("tags", [])}
                required_tags = {t.lower() for t in tags}
                if not required_tags.issubset(page_tags):
                    continue

            score = 0.0
            if query and rrf_scores:
                score = rrf_scores.get(page_id, 0.0)

            # Ensure confidence is set from metadata; when claims with
            # trust tags exist compute a trust-based confidence to override
            # the stored value so query results reflect Epic 2 scoring.
            claims = metadata.get("claims", [])
            if claims:
                metadata_copy = dict(metadata)
                score, metadata_copy = self._set_rerank_score(score, metadata_copy, claims)
            else:
                metadata_copy = dict(metadata)
                if query and metadata_copy.get("confidence", 0.0) == 0.0:
                    metadata_copy["confidence"] = metadata_copy.get("score", score)

            row = metadata_copy
            row["page_id"] = page_id
            row["id"] = page_id
            row["score"] = row.get("score", score)
            # Merge RRF score at top level for ranking
            row["_rrf"] = score
            filtered_results.append(row)

        # Sort by score (descending)
        filtered_results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        # Remove internal RRF key from final output
        for row in filtered_results:
            row.pop("_rrf", None)

        # When include_archived=True, also scan archive/ directories for
        # pages that are not in the index (moved to archive/).
        if include_archived:
            archived_pages = self._scan_archived_pages(allowed_domains)
            existing_ids = {r["page_id"] for r in filtered_results}
            for ap in archived_pages:
                if ap["page_id"] not in existing_ids:
                    ap["score"] = 0.0
                    filtered_results.append(ap)

            filtered_results.sort(key=lambda x: x.get("score", 0.0), reverse=True)

        return filtered_results[:limit]

    def _scan_archived_pages(self, allowed_domains: set[str] | None) -> list[dict[str, Any]]:
        """Scan archive/ directories for pages excluded from the index.

        Args:
            allowed_domains: Domain filter (same semantics as _resolve_search_domains)

        Returns:
            List of archived page dicts with metadata
        """
        results: list[dict[str, Any]] = []
        domains_dir = self.wiki_base / "domains"
        if not domains_dir.exists():
            return results

        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir() or domain_dir.is_symlink():
                continue
            domain_name = domain_dir.name

            # Apply domain scoping
            if allowed_domains is not None and domain_name not in allowed_domains:
                continue

            archive_dir = domain_dir / "archive"
            if not archive_dir.exists():
                continue

            for page_file in archive_dir.glob("*.md"):
                try:
                    content = page_file.read_text(encoding="utf-8")
                    from llm_wiki.utils.frontmatter import (  # noqa: PLC0415
                        parse_frontmatter,
                    )

                    metadata, _ = parse_frontmatter(content)
                    page_id = metadata.get("id", page_file.stem)
                    results.append(
                        {
                            **metadata,
                            "page_id": page_id,
                            "id": page_id,
                            "archived": True,
                            "score": 0.0,
                        }
                    )
                except Exception:
                    pass

        return results

    @staticmethod
    def _set_rerank_score(
        score: float, metadata: dict[str, Any], claims: list
    ) -> tuple[float, dict[str, Any]]:
        """Compute trust-based confidence from claims and update the result.

        When claims with trust tags exist the confidence is set to the
        ratio of extracted/inferred claims.  The RRF score is preserved
        in ``metadata["score"]`` for ranking.
        """
        result = dict(metadata)
        total = len(claims)
        non_ambiguous = sum(
            1
            for c in claims
            if isinstance(c, dict) and c.get("trust_tag") not in ("ambiguous", None)
        )
        trust_confidence = non_ambiguous / total if total > 0 else 0.0
        result["confidence"] = trust_confidence
        result.setdefault("score", score)
        return score, result

    def get_page(self, page_id: str) -> dict[str, Any] | None:
        """Get page metadata by ID.

        Searches both the metadata index and archived pages via direct file
        scan so that archived pages remain retrievable by ID.
        """
        result = self.metadata_index.get_page(page_id)
        if result is not None:
            result["archived"] = False
            return result

        # Fallback: search archive/ directories for pages excluded from index
        domains_dir = self.wiki_base / "domains"
        if not domains_dir.exists():
            return None

        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir() or domain_dir.is_symlink():
                continue
            archive_dir = domain_dir / "archive"
            if not archive_dir.exists():
                continue
            for page_file in archive_dir.glob("*.md"):
                try:
                    content = page_file.read_text(encoding="utf-8")
                    from llm_wiki.utils.frontmatter import parse_frontmatter  # noqa: PLC0415

                    metadata, _ = parse_frontmatter(content)
                    if metadata.get("id", page_file.stem) == page_id:
                        return {**metadata, "page_id": page_id, "archived": True}
                except Exception:
                    pass

        return None

    def list_pages(
        self,
        domain: str | None = None,
        kind: str | None = None,
        updated_since: datetime | None = None,
        cursor: str | None = None,
        limit: int = 50,
        include_archived: bool = False,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """List pages with optional filtering and cursor-based pagination.

        Args:
            domain: Filter by domain
            kind: Filter by page kind
            updated_since: Filter by updated_at after this timestamp
            cursor: Pagination cursor
            limit: Page size
            include_archived: When False (default), exclude archived pages

        Returns:
            Tuple of (page list, next cursor or None)
        """
        all_pages: list[dict[str, Any]] = []

        if domain or kind:
            if domain:
                page_ids: set[str] = self.metadata_index.by_domain.get(domain, set())
            else:
                page_ids = set(self.metadata_index.pages.keys())

            for pid in page_ids:
                meta = self.metadata_index.get_page(pid)
                if meta is None:
                    continue
                if kind and meta.get("kind") != kind:
                    continue
                all_pages.append(meta)
        else:
            all_pages = list(self.metadata_index.pages.values())

        # When include_archived=True, append pages from archive/ directories
        # that match the same domain scope as the indexed results.
        if include_archived:
            # Reconstruct allowed_domains so archive scan respects domain filter
            if domain and kind:
                allowed_domains_archived = {domain}
            elif domain:
                allowed_domains_archived = {domain}
            else:
                allowed_domains_archived = None
            archived_pages = self._scan_archived_pages(allowed_domains_archived)
            existing_ids = {p.get("page_id") or p.get("id") for p in all_pages}
            for ap in archived_pages:
                if ap["page_id"] not in existing_ids:
                    all_pages.append(ap)

        if updated_since is not None:
            # Normalise to UTC-aware so comparisons never raise TypeError between
            # naive and aware datetimes (e.g. stored timestamps without Z suffix).
            if updated_since.tzinfo is None:
                updated_since = updated_since.replace(tzinfo=UTC)

            def _parse(ts: str | None) -> datetime | None:
                if not ts:
                    return None
                try:
                    parsed = datetime.fromisoformat(ts)
                    # Treat timezone-naive stored timestamps as UTC.
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=UTC)
                    return parsed
                except ValueError:
                    return None

            # Pages without updated_at are excluded from filtered results.
            # Pages with an unparseable updated_at also fall back to datetime.min
            # (UTC) which is always <= any realistic filter — effectively excluded.
            _epoch = datetime.min.replace(tzinfo=UTC)
            all_pages = [
                p for p in all_pages if (_parse(p.get("updated_at")) or _epoch) > updated_since
            ]

        offset = 0
        if cursor:
            try:
                offset = int(base64.b64decode(cursor).decode())
            except Exception:
                offset = 0

        total = len(all_pages)
        page_items = all_pages[offset : offset + limit]
        next_cursor = (
            base64.b64encode(str(offset + limit).encode()).decode()
            if (offset + limit) < total
            else None
        )

        return page_items, next_cursor

    def get_pages_with_content(
        self,
        page_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Return pages with both metadata and markdown content.

        Uses the metadata index for frontmatter (confidence, sources,
        contradictions, title, etc.) and reads the raw markdown files
        for content.  Order matches ``page_ids``.
        """
        domains_dir = self.wiki_base / "domains"
        pages: list[dict[str, Any]] = []
        for pid in page_ids:
            metadata = self.metadata_index.get_page(pid)
            if metadata is None:
                continue
            domain = metadata.get("domain", "general")
            # Check promoted location: domains/{domain}/pages/{id}/page.md
            md_file = domains_dir / domain / "pages" / pid / "page.md"
            if not md_file.exists():
                # Fall back to queue location: domains/{domain}/queue/{id}.md
                md_file = domains_dir / domain / "queue" / f"{pid}.md"
            content = ""
            if md_file.exists():
                content = md_file.read_text(encoding="utf-8")
            row: dict[str, Any] = dict(metadata)
            row["page_id"] = pid
            row["id"] = pid
            row["content"] = content
            pages.append(row)
        return pages

    def find_by_tag(self, tag: str) -> list[dict[str, Any]]:
        """Find pages by tag."""
        return self.metadata_index.find_by_tag(tag)

    def find_by_kind(self, kind: str) -> list[dict[str, Any]]:
        """Find pages by kind."""
        return self.metadata_index.find_by_kind(kind)

    def find_by_domain(self, domain: str) -> list[dict[str, Any]]:
        """Find pages by domain."""
        return self.metadata_index.find_by_domain(domain)

    def get_all_tags(self) -> list[str]:
        """Get all unique tags in the wiki."""
        return self.metadata_index.get_all_tags()

    def rebuild_indexes(self) -> tuple[int, int, int]:
        """Rebuild all indexes from wiki pages.

        Each save is protected by its per-index lock.  IndexRebuildJob
        bypasses this method (it holds all locks directly) to avoid
        deadlocks.

        Returns:
            Tuple of (metadata_count, fulltext_count, vector_count)
        """
        logger.info("Rebuilding wiki indexes")

        metadata_count = self.metadata_index.rebuild_from_pages(self.wiki_base)
        fulltext_count = self.fulltext_index.rebuild_from_pages(self.wiki_base)
        vector_count = self.vector_index.rebuild_from_pages(self.wiki_base)

        with self._index_locks["metadata"]:
            self.metadata_index.save()
        with self._index_locks["fulltext"]:
            self.fulltext_index.save()
        with self._index_locks["vector"]:
            self.vector_index.save()

        logger.info(
            f"Rebuilt indexes: {metadata_count} metadata, "
            f"{fulltext_count} fulltext, {vector_count} vector"
        )

        return metadata_count, fulltext_count, vector_count

    def add_page(self, page_id: str, title: str, content: str, metadata: dict[str, Any]) -> None:
        """Add or update a page in indexes, persisting under per-index locks."""
        domain = metadata.get("domain", "general")
        self.metadata_index.add_page(page_id, metadata)
        self.fulltext_index.add_document(page_id, title, content, domain)
        self.vector_index.add_document(page_id, title, content, domain)

        with self._index_locks["metadata"]:
            self.metadata_index.save()
        with self._index_locks["fulltext"]:
            self.fulltext_index.save()
        with self._index_locks["vector"]:
            self.vector_index.save()

    def remove_page(self, page_id: str) -> None:
        """Remove a page from indexes, persisting under per-index locks."""
        self.metadata_index.remove_page(page_id)
        self.fulltext_index.remove_document(page_id)
        self.vector_index.remove_document_in_memory(page_id)

        with self._index_locks["metadata"]:
            self.metadata_index.save()
        with self._index_locks["fulltext"]:
            self.fulltext_index.save()
        with self._index_locks["vector"]:
            self.vector_index.save()

    def save_indexes(self) -> None:
        """Save indexes to disk under per-index locks."""
        with self._index_locks["metadata"]:
            self.metadata_index.save()
        with self._index_locks["fulltext"]:
            self.fulltext_index.save()
        with self._index_locks["vector"]:
            self.vector_index.save()

"""Synthesis cache — pre-computed pages for high-value repeated queries.

Reads from query_log.db to find frequently-repeated queries, generates
synthesis pages from them, and routes matching queries to serve cached
answers instead of recomputing.

No LLM calls — entirely algorithmic.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_DIR_NAME = "synthesis"


def _normalize_query(text: str) -> str:
    """Normalize query text for comparison.

    Lowercase, strip whitespace, collapse internal whitespace.
    """
    return re.sub(r"\s+", " ", text.lower().strip())


def _query_to_slug(query_text: str) -> str:
    """Convert normalized query text to a filesystem-safe slug."""
    normalized = _normalize_query(query_text)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or "empty-query"


def _compute_query_hash(text: str) -> str:
    """Deterministic short hash of normalized query text.

    Identical to compute_query_hash() in query/log.py to ensure consistency.
    """
    normalized = _normalize_query(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


@dataclass
class CacheCandidate:
    """A query that qualifies for caching."""

    query_text: str
    query_hash: str
    query_count: int
    last_seen: str


class SynthesisCacheJob:
    """Builds and maintains the synthesis cache.

    Reads query_log.db to find candidates, generates synthesis pages,
    and stores them in wiki_system/{domain}/synthesis/ directory structure
    under a shared area.
    """

    def __init__(
        self,
        wiki_base: Path,
        log_db: Path,
        min_hits: int = 5,
        window_days: int = 30,
    ) -> None:
        self.wiki_base = wiki_base
        self.log_db = log_db
        self.min_hits = min_hits
        self.window_days = window_days
        self._cache_dir = wiki_base / "shared" / _CACHE_DIR_NAME

    def get_candidates(self) -> list[CacheCandidate]:
        """Read query_log.db and return candidates meeting threshold.

        Only considers queries within the rolling window.
        """
        if not self.log_db.exists():
            logger.info("No query log found at %s — no cache candidates", self.log_db)
            return []

        cutoff = (datetime.now(UTC) - timedelta(days=self.window_days)).isoformat()

        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT query_text, query_hash, COUNT(*) as hits,
                          MAX(timestamp) as last_seen
                   FROM queries
                   WHERE timestamp >= ?
                   GROUP BY query_hash
                   HAVING hits >= ?
                   ORDER BY hits DESC""",
                (cutoff, self.min_hits),
            ).fetchall()
        finally:
            conn.close()

        candidates: list[CacheCandidate] = []
        for query_text, query_hash, hit_count, last_seen in rows:
            candidates.append(
                CacheCandidate(
                    query_text=query_text,
                    query_hash=query_hash,
                    query_count=hit_count,
                    last_seen=str(last_seen),
                )
            )

        return candidates

    def _connect(self) -> Any:
        """Open a read-only SQLite connection."""
        import sqlite3  # noqa: PLC0415

        conn = sqlite3.connect(str(self.log_db))
        conn.row_factory = sqlite3.Row
        return conn

    def get_existing_synthesis_page(self, query_hash: str) -> Path | None:
        """Check if a synthesis page already exists for this query_hash."""
        if not self._cache_dir.exists():
            return None
        import frontmatter as fm  # noqa: PLC0415

        for md_file in self._cache_dir.glob("*.md"):
            try:
                raw = md_file.read_text(encoding="utf-8")
                post = fm.loads(raw)
                meta = dict(post.metadata)
                if str(meta.get("query_hash")) == query_hash:
                    return md_file
            except Exception:
                pass
        return None

    async def generate_synthesis_page(self, candidate: CacheCandidate) -> str | None:
        """Generate a synthesis page for a cache candidate.

        Runs the synthesis engine algorithmically (no LLM) over generic
        data and returns the page content string. Returns None if
        generation fails.
        """
        try:
            cache_dir = self._cache_dir
            cache_dir.mkdir(parents=True, exist_ok=True)

            content = self._build_synthesis_content(candidate)
            slug = _query_to_slug(candidate.query_text)
            page_path = cache_dir / f"{slug}.md"

            frontmatter = {
                "id": f"synth-{candidate.query_hash}",
                "kind": "synthesis",
                "title": candidate.query_text,
                "domain": "shared",
                "source_query": candidate.query_text,
                "query_hash": candidate.query_hash,
                "query_count": candidate.query_count,
                "cached_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
                "status": "published",
            }

            content = self._write_engine(frontmatter, candidate.query_text, content)
            page_path.write_text(content, encoding="utf-8")
            logger.info("Created synthesis cache page: %s", page_path)
            return str(page_path)
        except Exception as e:
            logger.error("Failed to generate synthesis page for '%s': %s", candidate.query_text, e)
            return None

    def _build_synthesis_content(self, candidate: CacheCandidate) -> str:
        """Build a plain algorithmic synthesis from candidate data.

        Creates a factual summary based on the query patterns observed
        in the log — no LLM involved.
        """
        lines = [
            f"# Synthesis: {candidate.query_text}",
            "",
            f"**Query**: `{candidate.query_text}`",
            f"**Times cached**: {candidate.query_count}",
            f"**Cached at**: {candidate.last_seen}",
            "",
            "This page was automatically generated as a cached synthesis of a repeated query pattern.",
            "",
            "## Summary",
            "",
            "This query has been asked at least",
            f"`{candidate.query_count}` times in the last `{self.window_days}` days,",
            "indicating consistent interest in this topic. The wiki contains relevant"
            "source pages that answer this query.",
            "",
            "## Related Knowledge",
            "",
            "Search the wiki for this query to discover the underlying source pages.Use the query:",
            "",
            "```",
            f"query: {candidate.query_text}",
            "```",
            "",
        ]
        return "\n".join(lines)

    def _write_engine(self, frontmatter: dict, title: str, body: str) -> str:
        """Write frontmatter + body into a markdown page string."""
        import frontmatter as fm  # noqa: PLC0415

        post = fm.Post(body, **frontmatter)
        return str(fm.dumps(post))

    @staticmethod
    def _hash_to_slug(query_hash: str) -> str:
        """Convert a query hash to a slug.

        Uses the first 12 chars of the hash as a stable identifier.
        """
        return f"q-{query_hash[:12]}"

    def regenerate_if_stale(
        self,
        page_path: Path,
        candidate: CacheCandidate,
    ) -> bool:
        """Regenerate the page at page_path if it's a synthesis cache page.

        Returns True if the page was regenerated.
        """
        try:
            raw = page_path.read_text(encoding="utf-8")
            fm = __import__("frontmatter")  # noqa: N806
            post = fm.loads(raw)
            metadata = dict(post.metadata)
            if metadata.get("kind") != "synthesis":
                return False
            if metadata.get("query_hash") != candidate.query_hash:
                return False
        except Exception:
            return False

        # Rebuild the content
        content = self._build_synthesis_content(candidate)
        slug = _query_to_slug(candidate.query_text)
        new_path = self._cache_dir / f"{slug}.md"

        frontmatter = {
            "id": f"synth-{candidate.query_hash}",
            "kind": "synthesis",
            "title": candidate.query_text,
            "domain": "shared",
            "source_query": candidate.query_text,
            "query_hash": candidate.query_hash,
            "query_count": candidate.query_count,
            "cached_at": metadata.get("cached_at", datetime.now(UTC).isoformat()),
            "updated_at": datetime.now(UTC).isoformat(),
            "status": "published",
        }

        post_content = self._write_engine(frontmatter, candidate.query_text, content)
        new_path.write_text(post_content, encoding="utf-8")
        logger.info("Regenerated synthesis cache page: %s", new_path)
        return True

    def list_synthesis_pages(self) -> list[dict[str, Any]]:
        """List all synthesis cache pages with metadata."""
        if not self._cache_dir.exists():
            return []

        pages: list[dict[str, Any]] = []
        for md_file in sorted(self._cache_dir.glob("*.md")):
            try:
                raw = md_file.read_text(encoding="utf-8")
                post = __import__("frontmatter").loads(raw)  # noqa: PLC0415
                meta = dict(post.metadata)
                pages.append(
                    {
                        "page_id": meta.get("id", f"synth-{md_file.stem}"),
                        "title": meta.get("title", md_file.stem),
                        "domain": meta.get("domain", "shared"),
                        "kind": "synthesis",
                        "source_query": meta.get("source_query", ""),
                        "query_hash": meta.get("query_hash", ""),
                        "query_count": meta.get("query_count", 0),
                        "cached_at": meta.get("cached_at", ""),
                        "updated_at": meta.get("updated_at", ""),
                        "content": post.content,
                    }
                )
            except Exception as e:
                logger.warning("Failed to read synthesis page %s: %s", md_file, e)

        return pages

    def find_page_by_hash(self, query_hash: str) -> dict[str, Any] | None:
        """Look up a synthesis page by query_hash.

        Returns page data if found, None otherwise.
        Searches metadata across all cache pages since filenames may vary.
        """
        if not self._cache_dir.exists():
            return None

        for md_file in self._cache_dir.glob("*.md"):
            try:
                raw = md_file.read_text(encoding="utf-8")
                import frontmatter as fm  # noqa: PLC0415

                post = fm.loads(raw)
                meta = dict(post.metadata)
                if str(meta.get("query_hash")) == query_hash:
                    return {
                        "page_id": meta.get("id", f"synth-{md_file.stem}"),
                        "title": meta.get("title", md_file.stem),
                        "domain": meta.get("domain", "shared"),
                        "kind": "synthesis",
                        "source_query": meta.get("source_query", ""),
                        "query_hash": meta.get("query_hash", ""),
                        "cached_at": meta.get("cached_at", ""),
                        "query_count": meta.get("query_count", 0),
                    }
            except Exception:
                pass

        return None

    def find_page_by_text(self, query_text: str) -> dict[str, Any] | None:
        """Look up a synthesis page by normalized query text.

        Returns page data if found, None otherwise.
        """
        normalized = _normalize_query(query_text)
        for md_file in self._cache_dir.glob("*.md"):
            try:
                raw = md_file.read_text(encoding="utf-8")
                post = __import__("frontmatter").loads(raw)  # noqa: PLC0415
                meta = dict(post.metadata)
                if (
                    meta.get("source_query")
                    and _normalize_query(meta["source_query"]) == normalized
                ):
                    return self._read_page(md_file)
            except Exception:
                continue
        return None

    def _read_page(self, page_path: Path) -> dict[str, Any]:
        """Read a synthesis page file into a dict."""
        import frontmatter as fm_module  # noqa: PLC0415

        raw = page_path.read_text(encoding="utf-8")
        post = fm_module.loads(raw)
        meta = dict(post.metadata)
        return {
            "page_id": meta.get("id", f"synth-{page_path.stem}"),
            "title": meta.get("title", page_path.stem),
            "domain": meta.get("domain", "shared"),
            "kind": "synthesis",
            "source_query": meta.get("source_query", ""),
            "query_hash": meta.get("query_hash", ""),
            "query_count": meta.get("query_count", 0),
            "cached_at": meta.get("cached_at", ""),
            "updated_at": meta.get("updated_at", ""),
            "content": post.content,
        }

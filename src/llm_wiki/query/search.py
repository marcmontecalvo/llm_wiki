"""Unified search interface for wiki queries."""

import logging
from pathlib import Path
from typing import Any

from llm_wiki.index.fulltext import FulltextIndex
from llm_wiki.index.metadata import MetadataIndex

logger = logging.getLogger(__name__)


class WikiQuery:
    """Unified query interface for searching wiki pages."""

    def __init__(self, wiki_base: Path | None = None, index_dir: Path | None = None):
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

        # Load indexes
        self._load_indexes()

    def _load_indexes(self) -> None:
        """Load indexes from disk."""
        try:
            self.metadata_index.load()
            self.fulltext_index.load()
            logger.info("Loaded wiki indexes")
        except Exception as e:
            logger.warning(f"Failed to load indexes: {e}")

    def search(
        self,
        query: str | None = None,
        tags: list[str] | None = None,
        kind: str | None = None,
        domain: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for wiki pages.

        Combines metadata and fulltext search. If query is provided, performs
        fulltext search and filters by metadata. Otherwise, performs metadata
        lookup only.

        Args:
            query: Fulltext search query
            tags: Filter by tags (AND operation - all tags must match)
            kind: Filter by page kind
            domain: Filter by domain
            limit: Maximum results to return

        Returns:
            List of search results with page_id, title, domain, score
        """
        # If fulltext query provided, start with fulltext search
        if query:
            results = self.fulltext_index.search(query, domain=domain, limit=limit * 2)
            page_ids = {r["page_id"] for r in results}
        else:
            # No fulltext query - get all pages from metadata
            page_ids = set(self.metadata_index.pages.keys())
            results = []

        # Apply metadata filters
        filtered_results = []

        for page_id in page_ids:
            metadata = self.metadata_index.get_page(page_id)
            if not metadata:
                continue

            # Apply filters
            if domain and metadata.get("domain") != domain:
                continue

            if kind and metadata.get("kind") != kind:
                continue

            if tags:
                page_tags = {str(t).lower() for t in metadata.get("tags", [])}
                required_tags = {t.lower() for t in tags}
                if not required_tags.issubset(page_tags):
                    continue

            # Get score from fulltext results, or 0 if metadata-only query
            score = 0.0
            if query:
                for r in results:
                    if r["page_id"] == page_id:
                        score = r["score"]
                        break

            filtered_results.append(
                {
                    "id": page_id,
                    "page_id": page_id,
                    "title": metadata.get("title", page_id),
                    "domain": metadata.get("domain", "general"),
                    "kind": metadata.get("kind", "page"),
                    "tags": metadata.get("tags", []),
                    "score": score,
                }
            )

        # Sort by score (descending)
        filtered_results.sort(key=lambda x: x["score"], reverse=True)

        return filtered_results[:limit]

    def get_page(self, page_id: str) -> dict[str, Any] | None:
        """Get page metadata by ID.

        Args:
            page_id: Page identifier

        Returns:
            Page metadata or None if not found
        """
        return self.metadata_index.get_page(page_id)

    def find_by_tag(self, tag: str) -> list[dict[str, Any]]:
        """Find pages by tag.

        Args:
            tag: Tag to search for

        Returns:
            List of page metadata dictionaries
        """
        return self.metadata_index.find_by_tag(tag)

    def find_by_kind(self, kind: str) -> list[dict[str, Any]]:
        """Find pages by kind.

        Args:
            kind: Page kind (entity, concept, page, source)

        Returns:
            List of page metadata dictionaries
        """
        return self.metadata_index.find_by_kind(kind)

    def find_by_domain(self, domain: str) -> list[dict[str, Any]]:
        """Find pages by domain.

        Args:
            domain: Domain identifier

        Returns:
            List of page metadata dictionaries
        """
        return self.metadata_index.find_by_domain(domain)

    def get_all_tags(self) -> list[str]:
        """Get all unique tags in the wiki.

        Returns:
            Sorted list of tags
        """
        return self.metadata_index.get_all_tags()

    def rebuild_indexes(self) -> tuple[int, int]:
        """Rebuild both indexes from wiki pages.

        Returns:
            Tuple of (metadata_count, fulltext_count)
        """
        logger.info("Rebuilding wiki indexes")

        metadata_count = self.metadata_index.rebuild_from_pages(self.wiki_base)
        fulltext_count = self.fulltext_index.rebuild_from_pages(self.wiki_base)

        # Save indexes
        self.metadata_index.save()
        self.fulltext_index.save()

        logger.info(f"Rebuilt indexes: {metadata_count} metadata, {fulltext_count} fulltext")

        return metadata_count, fulltext_count

    def add_page(self, page_id: str, title: str, content: str, metadata: dict[str, Any]) -> None:
        """Add or update a page in indexes.

        Args:
            page_id: Page identifier
            title: Page title
            content: Page content (markdown)
            metadata: Page metadata (frontmatter)
        """
        domain = metadata.get("domain", "general")

        # Add to metadata index
        self.metadata_index.add_page(page_id, metadata)

        # Add to fulltext index
        self.fulltext_index.add_document(page_id, title, content, domain)

    def remove_page(self, page_id: str) -> None:
        """Remove a page from indexes.

        Args:
            page_id: Page identifier
        """
        self.metadata_index.remove_page(page_id)
        self.fulltext_index.remove_document(page_id)

    def save_indexes(self) -> None:
        """Save indexes to disk."""
        self.metadata_index.save()
        self.fulltext_index.save()

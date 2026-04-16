"""Metadata indexer for fast page lookups."""

import json
import logging
from pathlib import Path
from typing import Any

from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


class MetadataIndex:
    """Index for page metadata (tags, kind, domain, etc.)."""

    def __init__(self, index_dir: Path | None = None):
        """Initialize metadata index.

        Args:
            index_dir: Directory to store index (defaults to wiki_system/index)
        """
        self.index_dir = index_dir or Path("wiki_system/index")
        self.index_dir.mkdir(parents=True, exist_ok=True)

        # In-memory indexes
        self.pages: dict[str, dict[str, Any]] = {}  # page_id -> metadata
        self.by_tag: dict[str, set[str]] = {}  # tag -> set of page_ids
        self.by_kind: dict[str, set[str]] = {}  # kind -> set of page_ids
        self.by_domain: dict[str, set[str]] = {}  # domain -> set of page_ids
        self.claims: list[dict[str, Any]] = []  # flat list of all claims with page context

    def add_page(self, page_id: str, metadata: dict[str, Any]) -> None:
        """Add or update a page in the index.

        Args:
            page_id: Page identifier
            metadata: Page metadata (frontmatter)
        """
        # Store full metadata
        self.pages[page_id] = metadata

        # Index by tags
        tags = metadata.get("tags", [])
        if isinstance(tags, list):
            for tag in tags:
                tag_str = str(tag).lower()
                if tag_str not in self.by_tag:
                    self.by_tag[tag_str] = set()
                self.by_tag[tag_str].add(page_id)

        # Index by kind
        kind = metadata.get("kind", "page")
        if kind not in self.by_kind:
            self.by_kind[kind] = set()
        self.by_kind[kind].add(page_id)

        # Index by domain
        domain = metadata.get("domain", "general")
        if domain not in self.by_domain:
            self.by_domain[domain] = set()
        self.by_domain[domain].add(page_id)

        # Index claims (remove old entries for this page first, then add new)
        self.claims = [c for c in self.claims if c.get("page_id") != page_id]
        for claim in metadata.get("claims", []):
            if isinstance(claim, dict) and "text" in claim:
                entry = dict(claim)
                entry["page_id"] = page_id
                self.claims.append(entry)

    def remove_page(self, page_id: str) -> None:
        """Remove a page from the index.

        Args:
            page_id: Page identifier
        """
        if page_id not in self.pages:
            return

        metadata = self.pages[page_id]

        # Remove from tag index
        tags = metadata.get("tags", [])
        if isinstance(tags, list):
            for tag in tags:
                tag_str = str(tag).lower()
                if tag_str in self.by_tag:
                    self.by_tag[tag_str].discard(page_id)

        # Remove from kind index
        kind = metadata.get("kind", "page")
        if kind in self.by_kind:
            self.by_kind[kind].discard(page_id)

        # Remove from domain index
        domain = metadata.get("domain", "general")
        if domain in self.by_domain:
            self.by_domain[domain].discard(page_id)

        # Remove claims for this page
        self.claims = [c for c in self.claims if c.get("page_id") != page_id]

        # Remove metadata
        del self.pages[page_id]

    def find_by_tag(self, tag: str) -> list[dict[str, Any]]:
        """Find pages by tag.

        Args:
            tag: Tag to search for

        Returns:
            List of page metadata dictionaries
        """
        tag_lower = tag.lower()
        page_ids = self.by_tag.get(tag_lower, set())
        return [self.pages[pid] for pid in page_ids if pid in self.pages]

    def find_by_kind(self, kind: str) -> list[dict[str, Any]]:
        """Find pages by kind.

        Args:
            kind: Page kind (entity, concept, page, source)

        Returns:
            List of page metadata dictionaries
        """
        page_ids = self.by_kind.get(kind, set())
        return [self.pages[pid] for pid in page_ids if pid in self.pages]

    def find_by_domain(self, domain: str) -> list[dict[str, Any]]:
        """Find pages by domain.

        Args:
            domain: Domain identifier

        Returns:
            List of page metadata dictionaries
        """
        page_ids = self.by_domain.get(domain, set())
        return [self.pages[pid] for pid in page_ids if pid in self.pages]

    def get_page(self, page_id: str) -> dict[str, Any] | None:
        """Get page metadata by ID.

        Args:
            page_id: Page identifier

        Returns:
            Page metadata or None if not found
        """
        return self.pages.get(page_id)

    def get_all_tags(self) -> list[str]:
        """Get all unique tags in the index.

        Returns:
            Sorted list of tags
        """
        return sorted(self.by_tag.keys())

    def search_claims(
        self, query: str, min_confidence: float = 0.0, page_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Search claims by text keyword.

        Args:
            query: Text to search for (case-insensitive substring match)
            min_confidence: Minimum confidence threshold (0.0-1.0)
            page_id: Optional page_id to restrict search to one page

        Returns:
            List of matching claim dicts sorted by confidence descending
        """
        query_lower = query.lower()
        results = []
        for claim in self.claims:
            if claim.get("confidence", 0.0) < min_confidence:
                continue
            if page_id and claim.get("page_id") != page_id:
                continue
            if query_lower in claim.get("text", "").lower():
                results.append(claim)
        results.sort(key=lambda c: c.get("confidence", 0.0), reverse=True)
        return results

    def get_claims_for_page(self, page_id: str) -> list[dict[str, Any]]:
        """Get all claims for a specific page.

        Args:
            page_id: Page identifier

        Returns:
            List of claim dicts for the page
        """
        return [c for c in self.claims if c.get("page_id") == page_id]

    def save(self) -> None:
        """Save index to disk."""
        index_file = self.index_dir / "metadata.json"

        # Convert sets to lists for JSON serialization
        data = {
            "pages": self.pages,
            "by_tag": {k: list(v) for k, v in self.by_tag.items()},
            "by_kind": {k: list(v) for k, v in self.by_kind.items()},
            "by_domain": {k: list(v) for k, v in self.by_domain.items()},
            "claims": self.claims,
        }

        with index_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved metadata index ({len(self.pages)} pages)")

    def load(self) -> None:
        """Load index from disk."""
        index_file = self.index_dir / "metadata.json"

        if not index_file.exists():
            logger.info("No existing metadata index found")
            return

        with index_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        self.pages = data.get("pages", {})
        self.by_tag = {k: set(v) for k, v in data.get("by_tag", {}).items()}
        self.by_kind = {k: set(v) for k, v in data.get("by_kind", {}).items()}
        self.by_domain = {k: set(v) for k, v in data.get("by_domain", {}).items()}
        self.claims = data.get("claims", [])

        logger.info(f"Loaded metadata index ({len(self.pages)} pages)")

    def rebuild_from_pages(self, wiki_base: Path | None = None) -> int:
        """Rebuild index from all wiki pages.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)

        Returns:
            Number of pages indexed
        """
        wiki_base = wiki_base or Path("wiki_system")

        # Clear existing index
        self.pages.clear()
        self.by_tag.clear()
        self.by_kind.clear()
        self.by_domain.clear()
        self.claims.clear()

        # Scan all domains
        domains_dir = wiki_base / "domains"
        if not domains_dir.exists():
            logger.warning(f"Domains directory not found: {domains_dir}")
            return 0

        count = 0
        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            pages_dir = domain_dir / "pages"
            if not pages_dir.exists():
                continue

            # Index all markdown files
            for page_file in pages_dir.glob("*.md"):
                try:
                    content = page_file.read_text(encoding="utf-8")
                    metadata, _ = parse_frontmatter(content)

                    page_id = metadata.get("id", page_file.stem)
                    self.add_page(page_id, metadata)
                    count += 1

                except Exception as e:
                    logger.error(f"Failed to index {page_file}: {e}")

        logger.info(f"Rebuilt metadata index: {count} pages")
        return count

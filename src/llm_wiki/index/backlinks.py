"""Backlink index for bidirectional link tracking."""

import json
import logging
import re
from pathlib import Path
from typing import Any

from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


class BacklinkIndex:
    """Index for tracking bidirectional links between pages."""

    def __init__(self, index_dir: Path | None = None):
        """Initialize backlink index.

        Args:
            index_dir: Directory to store index (defaults to wiki_system/index)
        """
        self.index_dir = index_dir or Path("wiki_system/index")
        self.index_dir.mkdir(parents=True, exist_ok=True)

        # page_id -> {
        #   "forward_links": set of target page IDs,
        #   "backlinks": set of source page IDs,
        #   "broken_links": set of non-existent target IDs
        # }
        self.index: dict[str, dict[str, Any]] = {}

    def _extract_links(self, content: str) -> list[str]:
        """Extract wiki links from content.

        Args:
            content: Page content

        Returns:
            List of linked page IDs (from [[page-id]] syntax)
        """
        # Extract [[page-id]] style links
        links = re.findall(r"\[\[([^\]]+)\]\]", content)
        return links

    def add_page_links(self, page_id: str, content: str) -> list[str]:
        """Extract and add forward links for a page.

        Args:
            page_id: Page identifier
            content: Page content (markdown)

        Returns:
            List of extracted forward links
        """
        # Extract forward links from content
        forward_links = self._extract_links(content)
        forward_links = list(set(forward_links))  # Deduplicate

        # Initialize page index if needed
        if page_id not in self.index:
            self.index[page_id] = {
                "forward_links": set(),
                "backlinks": set(),
                "broken_links": set(),
            }

        # Clear old forward links first
        old_forward = self.index[page_id]["forward_links"].copy()
        self.index[page_id]["forward_links"] = set(forward_links)

        # Remove old backlinks from targets
        for old_link in old_forward:
            if old_link in self.index:
                self.index[old_link]["backlinks"].discard(page_id)

        # Add new backlinks to targets
        for link in forward_links:
            if link not in self.index:
                self.index[link] = {
                    "forward_links": set(),
                    "backlinks": set(),
                    "broken_links": set(),
                }
            self.index[link]["backlinks"].add(page_id)

        logger.debug(f"Added {len(forward_links)} forward links for page {page_id}")

        return forward_links

    def remove_page(self, page_id: str) -> None:
        """Remove a page from the index.

        When a page is deleted, update all pages that link to it.

        Args:
            page_id: Page identifier to remove
        """
        if page_id not in self.index:
            return

        page_data = self.index[page_id]

        # Remove this page from all backlinks
        for source_id in page_data["backlinks"]:
            if source_id in self.index:
                self.index[source_id]["forward_links"].discard(page_id)
                self.index[source_id]["broken_links"].add(page_id)

        # Remove this page as a target from forward links
        for target_id in page_data["forward_links"]:
            if target_id in self.index:
                self.index[target_id]["backlinks"].discard(page_id)

        # Remove the page itself
        del self.index[page_id]

        logger.debug(f"Removed page {page_id} from backlink index")

    def rename_page(self, old_id: str, new_id: str) -> None:
        """Rename a page and update all references.

        Args:
            old_id: Old page identifier
            new_id: New page identifier
        """
        if old_id not in self.index:
            logger.warning(f"Page {old_id} not found in backlink index")
            return

        # Move the page entry
        self.index[new_id] = self.index.pop(old_id)

        # Update all forward links pointing to old_id
        for page_id in self.index:
            if old_id in self.index[page_id]["forward_links"]:
                self.index[page_id]["forward_links"].discard(old_id)
                self.index[page_id]["forward_links"].add(new_id)

        # Update all backlinks pointing to old_id
        for target_id in self.index[new_id]["forward_links"]:
            if target_id in self.index:
                self.index[target_id]["backlinks"].discard(old_id)
                self.index[target_id]["backlinks"].add(new_id)

        logger.debug(f"Renamed page {old_id} to {new_id}")

    def get_backlinks(self, page_id: str) -> list[str]:
        """Get all pages that link to the given page.

        Args:
            page_id: Page identifier

        Returns:
            List of page IDs that link to this page
        """
        if page_id not in self.index:
            return []

        return sorted(self.index[page_id]["backlinks"])

    def get_forward_links(self, page_id: str) -> list[str]:
        """Get all pages that the given page links to.

        Args:
            page_id: Page identifier

        Returns:
            List of page IDs that this page links to
        """
        if page_id not in self.index:
            return []

        return sorted(self.index[page_id]["forward_links"])

    def get_broken_links(self, page_id: str) -> list[str]:
        """Get broken links (links to non-existent pages) for a page.

        Args:
            page_id: Page identifier

        Returns:
            List of broken link targets
        """
        if page_id not in self.index:
            return []

        return sorted(self.index[page_id]["broken_links"])

    def update_broken_links(self, all_page_ids: set[str]) -> dict[str, int]:
        """Update broken link detection based on existing pages.

        Args:
            all_page_ids: Set of all valid page IDs in the wiki

        Returns:
            Dict with stats: total_broken_links, pages_with_broken_links
        """
        total_broken = 0
        pages_with_broken = 0

        for page_id in self.index:
            forward_links = self.index[page_id]["forward_links"]
            broken = forward_links - all_page_ids

            if broken:
                self.index[page_id]["broken_links"] = broken
                total_broken += len(broken)
                pages_with_broken += 1
            else:
                self.index[page_id]["broken_links"] = set()

        logger.info(
            f"Updated broken links: {total_broken} total, {pages_with_broken} pages affected"
        )

        return {
            "total_broken_links": total_broken,
            "pages_with_broken_links": pages_with_broken,
        }

    def get_orphan_pages(self, all_page_ids: set[str]) -> list[str]:
        """Find pages with no backlinks (orphans).

        Args:
            all_page_ids: Set of all valid page IDs in the wiki

        Returns:
            List of orphan page IDs
        """
        orphans = []
        for page_id in all_page_ids:
            if page_id not in self.index or not self.index[page_id]["backlinks"]:
                orphans.append(page_id)

        return sorted(orphans)

    def get_link_stats(self) -> dict[str, Any]:
        """Get statistics about the link index.

        Returns:
            Dict with stats
        """
        total_forward_links = 0
        total_backlinks = 0
        total_broken_links = 0
        pages_with_links = 0

        for page_data in self.index.values():
            forward = len(page_data["forward_links"])
            broken = len(page_data["broken_links"])

            if forward > 0 or broken > 0:
                pages_with_links += 1

            total_forward_links += forward
            total_backlinks += len(page_data["backlinks"])
            total_broken_links += broken

        return {
            "total_pages": len(self.index),
            "pages_with_links": pages_with_links,
            "total_forward_links": total_forward_links,
            "total_backlinks": total_backlinks,
            "total_broken_links": total_broken_links,
        }

    def save(self) -> None:
        """Save index to disk."""
        index_file = self.index_dir / "backlinks.json"

        # Convert sets to lists for JSON serialization
        data = {}
        for page_id, page_data in self.index.items():
            data[page_id] = {
                "forward_links": sorted(page_data["forward_links"]),
                "backlinks": sorted(page_data["backlinks"]),
                "broken_links": sorted(page_data["broken_links"]),
            }

        with index_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved backlink index ({len(self.index)} pages)")

    def load(self) -> None:
        """Load index from disk."""
        index_file = self.index_dir / "backlinks.json"

        if not index_file.exists():
            logger.info("No existing backlink index found")
            return

        with index_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        self.index = {}
        for page_id, page_data in data.items():
            self.index[page_id] = {
                "forward_links": set(page_data.get("forward_links", [])),
                "backlinks": set(page_data.get("backlinks", [])),
                "broken_links": set(page_data.get("broken_links", [])),
            }

        logger.info(f"Loaded backlink index ({len(self.index)} pages)")

    def rebuild_from_pages(self, wiki_base: Path | None = None) -> int:
        """Rebuild index from all wiki pages.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)

        Returns:
            Number of pages indexed
        """
        wiki_base = wiki_base or Path("wiki_system")

        # Clear existing index
        self.index.clear()

        # Scan all domains
        domains_dir = wiki_base / "domains"
        if not domains_dir.exists():
            logger.warning(f"Domains directory not found: {domains_dir}")
            return 0

        count = 0
        page_ids = set()

        # First pass: collect all page IDs
        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            pages_dir = domain_dir / "pages"
            if not pages_dir.exists():
                continue

            for page_file in pages_dir.glob("*.md"):
                try:
                    content = page_file.read_text(encoding="utf-8")
                    metadata, _ = parse_frontmatter(content)
                    page_id = metadata.get("id", page_file.stem)
                    page_ids.add(page_id)
                except Exception as e:
                    logger.error(f"Failed to read {page_file}: {e}")

        # Second pass: extract links
        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            pages_dir = domain_dir / "pages"
            if not pages_dir.exists():
                continue

            for page_file in pages_dir.glob("*.md"):
                try:
                    content = page_file.read_text(encoding="utf-8")
                    metadata, body = parse_frontmatter(content)

                    page_id = metadata.get("id", page_file.stem)
                    self.add_page_links(page_id, body)
                    count += 1

                except Exception as e:
                    logger.error(f"Failed to index {page_file}: {e}")

        # Update broken links
        self.update_broken_links(page_ids)

        logger.info(f"Rebuilt backlink index: {count} pages")
        return count

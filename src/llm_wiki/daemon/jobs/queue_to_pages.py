"""Queue-to-pages daemon job."""

import logging
from pathlib import Path
from typing import Any

import frontmatter

from llm_wiki.paths import resolve_wiki_base
from llm_wiki.utils.frontmatter import write_frontmatter
from llm_wiki.utils.id_gen import generate_page_id

logger = logging.getLogger(__name__)

# Modules-scoped set to track used page IDs within a single execution run
_used_ids: set[str] = set()


class QueueToPagesJob:
    """Daemon job for migrating queued files into published pages."""

    def __init__(self, wiki_base: Path | None = None):
        """Initialize queue-to-pages job.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)
        """
        self.wiki_base = resolve_wiki_base(wiki_base)

    def _collision_check(self, page_id: str) -> bool:
        """Return True if *page_id* already exists on disk in pages/.

        Args:
            page_id: Candidate page ID

        Returns:
            True if a page with this ID already exists in pages/
        """
        return any(
            p.exists() for p in self.wiki_base.glob("domains/*/pages/*.md") if p.stem == page_id
        )

    def execute(self) -> dict[str, Any]:
        """Process all queued files.

        Returns:
            Dictionary with migration statistics
        """
        logger.info("Starting queue-to-pages migration")

        # Collect all domain queue directories
        queue_dirs = sorted(self.wiki_base.glob("domains/*/queue"))
        if not queue_dirs:
            return {
                "status": "success",
                "moved": 0,
                "binned": 0,
                "error": 0,
                "skipped": 0,
            }

        moved = 0
        binned = 0
        error = 0

        for queue_dir in queue_dirs:
            domain = queue_dir.parent.name
            md_files = sorted(queue_dir.glob("*.md"))
            if not md_files:
                continue

            logger.info(f"Processing {len(md_files)} file(s) in {domain}/queue/")

            pages_dir = queue_dir.parent / "pages"
            pages_dir.mkdir(parents=True, exist_ok=True)

            for filepath in md_files:
                try:
                    raw = filepath.read_text(encoding="utf-8")

                    # Parse frontmatter — use the postmatter library to
                    # correctly handle edge cases with empty frontmatter.
                    post = frontmatter.loads(raw)
                    metadata = dict(post.metadata)  # may be empty {}
                    content = post.content

                    # Determine or validate ID
                    page_id = metadata.get("id")
                    if not page_id:
                        title = metadata.get("title", filepath.stem)
                        page_id = generate_page_id(
                            title,
                            domain,
                            collision_check=self._collision_check,
                        )
                        metadata["id"] = page_id

                    # Update status to published
                    metadata["status"] = "published"
                    # Remove queue-specific metadata
                    metadata.pop("source_path", None)

                    # Build final output
                    final_content = write_frontmatter(metadata, content)

                    # Write to pages/
                    output_path = pages_dir / f"{page_id}.md"
                    output_path.write_text(final_content, encoding="utf-8")

                    # Remove from queue
                    filepath.unlink()

                    moved += 1
                    logger.info(f"  Migrated: {filepath.name} -> pages/{page_id}.md")

                except Exception as e:
                    logger.error(
                        f"  Failed to migrate {filepath.name}: {e}",
                        exc_info=True,
                    )
                    error += 1

        # Clean up empty queue directories
        for queue_dir in queue_dirs:
            if not any(queue_dir.iterdir()):
                try:
                    queue_dir.rmdir()
                    logger.debug(f"Removed empty queue directory: {queue_dir}")
                except OSError:
                    pass

        logger.info(f"Queue-to-pages complete: {moved} moved, {error} errors")
        return {
            "status": "success",
            "moved": moved,
            "binned": binned,
            "error": error,
            "skipped": 0,
        }


def run_queue_to_pages(wiki_base: Path | None = None) -> dict[str, Any]:
    """Run queue-to-pages job.

    This function is called by the daemon scheduler.

    Args:
        wiki_base: Base wiki directory (defaults to wiki_system/)

    Returns:
        Dictionary with migration statistics
    """
    # Reset used ID tracking so each run starts fresh
    _used_ids.clear()
    job = QueueToPagesJob(wiki_base=wiki_base)
    return job.execute()

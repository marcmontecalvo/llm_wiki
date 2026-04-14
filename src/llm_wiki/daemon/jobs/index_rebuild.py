"""Index rebuild daemon job."""

import logging
from pathlib import Path
from typing import Any

from llm_wiki.query.search import WikiQuery

logger = logging.getLogger(__name__)


class IndexRebuildJob:
    """Daemon job for rebuilding search indexes."""

    def __init__(self, wiki_base: Path | None = None):
        """Initialize index rebuild job.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)
        """
        self.wiki_base = wiki_base or Path("wiki_system")
        self.wiki_query = WikiQuery(wiki_base=self.wiki_base)

    def execute(self) -> dict[str, Any]:
        """Execute index rebuild.

        Returns:
            Dictionary with rebuild statistics
        """
        logger.info("Starting index rebuild job")

        try:
            metadata_count, fulltext_count = self.wiki_query.rebuild_indexes()

            logger.info(
                f"Index rebuild complete: {metadata_count} metadata, {fulltext_count} fulltext"
            )

            return {
                "metadata_count": metadata_count,
                "fulltext_count": fulltext_count,
                "status": "success",
            }

        except Exception as e:
            logger.error(f"Index rebuild failed: {e}", exc_info=True)
            return {
                "metadata_count": 0,
                "fulltext_count": 0,
                "status": "error",
                "error": str(e),
            }


def run_index_rebuild(wiki_base: Path | None = None) -> dict[str, Any]:
    """Run index rebuild job.

    This function is called by the daemon scheduler.

    Args:
        wiki_base: Base wiki directory (defaults to wiki_system/)

    Returns:
        Dictionary with rebuild statistics
    """
    job = IndexRebuildJob(wiki_base=wiki_base)
    return job.execute()

"""Index rebuild daemon job."""

import logging
from pathlib import Path
from typing import Any

from llm_wiki.index.backlinks import BacklinkIndex
from llm_wiki.index.graph_edges import GraphEdgeIndex
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
        self.backlink_index = BacklinkIndex(index_dir=self.wiki_base / "index")
        self.graph_edge_index = GraphEdgeIndex(index_dir=self.wiki_base / "index")

    def execute(self) -> dict[str, Any]:
        """Execute index rebuild.

        Returns:
            Dictionary with rebuild statistics
        """
        logger.info("Starting index rebuild job")

        try:
            metadata_count, fulltext_count = self.wiki_query.rebuild_indexes()

            backlink_count = self.backlink_index.rebuild_from_pages(self.wiki_base)
            self.backlink_index.save()

            graph_edge_count = self.graph_edge_index.rebuild_from_pages(self.wiki_base)
            self.graph_edge_index.save()

            logger.info(
                f"Index rebuild complete: {metadata_count} metadata, "
                f"{fulltext_count} fulltext, {backlink_count} backlinks, "
                f"{graph_edge_count} graph edge pages"
            )

            return {
                "metadata_pages": metadata_count,
                "fulltext_documents": fulltext_count,
                "backlink_count": backlink_count,
                "graph_edge_count": graph_edge_count,
                "status": "success",
            }

        except Exception as e:
            logger.error(f"Index rebuild failed: {e}", exc_info=True)
            return {
                "metadata_pages": 0,
                "fulltext_documents": 0,
                "backlink_count": 0,
                "graph_edge_count": 0,
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

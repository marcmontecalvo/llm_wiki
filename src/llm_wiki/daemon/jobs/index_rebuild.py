"""Index rebuild daemon job."""

import logging
from pathlib import Path
from typing import Any

from llm_wiki.index.backlinks import BacklinkIndex
from llm_wiki.index.graph_edges import GraphEdgeIndex
from llm_wiki.paths import resolve_wiki_base
from llm_wiki.query.search import WikiQuery

logger = logging.getLogger(__name__)


class IndexRebuildJob:
    """Daemon job for rebuilding search indexes."""

    def __init__(self, wiki_base: Path | None = None, wiki: WikiQuery | None = None):
        """Initialize index rebuild job.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)
            wiki: Injected WikiQuery singleton (falls back to creating one for
                  backward compatibility)
        """
        self.wiki_base = resolve_wiki_base(wiki_base)
        self.wiki_query = wiki if wiki is not None else WikiQuery(wiki_base=self.wiki_base)
        self.backlink_index = BacklinkIndex(index_dir=self.wiki_base / "index")
        self.graph_edge_index = GraphEdgeIndex(index_dir=self.wiki_base / "index")

    def execute(self) -> dict[str, Any]:
        """Execute index rebuild with full lock coverage.

        Holds all WikiQuery locks during the rebuild to prevent incremental
        writers from producing torn state.  Index saves are performed
        directly on the index instances (bypassing WikiQuery methods) to
        avoid re-acquiring the already-held locks and deadlocking.

        After releasing locks, the FAISS index is reloaded into memory.

        Returns:
            Dictionary with rebuild statistics
        """
        logger.info("Starting index rebuild job")

        self.wiki_query.acquire_all_locks()
        try:
            # Rebuild all indexes (in-memory only -- do NOT call save() yet)
            metadata_count = self.wiki_query.metadata_index.rebuild_from_pages(self.wiki_base)
            fulltext_count = self.wiki_query.fulltext_index.rebuild_from_pages(self.wiki_base)
            vector_count = self.wiki_query.vector_index.rebuild_from_pages(self.wiki_base)
            backlink_count = self.backlink_index.rebuild_from_pages(self.wiki_base)
            graph_edge_count = self.graph_edge_index.rebuild_from_pages(self.wiki_base)

            # Save directly -- locks are already held by acquire_all_locks()
            self.wiki_query.metadata_index.save()
            self.wiki_query.fulltext_index.save()
            self.wiki_query.vector_index.save()
            self.backlink_index.save()
            self.graph_edge_index.save()

            logger.info(
                f"Index rebuild complete: {metadata_count} metadata, "
                f"{fulltext_count} fulltext, {vector_count} vector, "
                f"{backlink_count} backlinks, {graph_edge_count} graph edge pages"
            )

            # Compute and write authority scores after indexes are rebuilt
            from llm_wiki.synthesis.authority import (  # noqa: PLC0415
                compute_authority_scores,
                write_authority_scores,
            )

            raw_scores = compute_authority_scores(self.wiki_base)
            scored = write_authority_scores(self.wiki_base, raw_scores)
            logger.info(
                "Authority scoring complete: computed %d scores, wrote %d pages",
                len(raw_scores),
                scored,
            )

            return {
                "metadata_pages": metadata_count,
                "fulltext_documents": fulltext_count,
                "vector_documents": vector_count,
                "backlink_count": backlink_count,
                "graph_edge_count": graph_edge_count,
                "authority_scores_computed": len(raw_scores),
                "pages_updated": scored,
                "status": "success",
            }

        except Exception as e:
            logger.error(f"Index rebuild failed: {e}", exc_info=True)
            return {
                "metadata_pages": 0,
                "fulltext_documents": 0,
                "vector_documents": 0,
                "backlink_count": 0,
                "graph_edge_count": 0,
                "status": "error",
                "error": str(e),
            }
        finally:
            self.wiki_query.release_all_locks()
            # After releasing locks, reload FAISS into memory
            self.wiki_query.reload_vector_index()


def run_index_rebuild(
    wiki_base: Path | None = None, wiki: WikiQuery | None = None
) -> dict[str, Any]:
    """Run index rebuild job.

    This function is called by the daemon scheduler.

    Args:
        wiki_base: Base wiki directory (defaults to wiki_system/)
        wiki: Optional injected WikiQuery singleton

    Returns:
        Dictionary with rebuild statistics
    """
    job = IndexRebuildJob(wiki_base=wiki_base, wiki=wiki)
    return job.execute()

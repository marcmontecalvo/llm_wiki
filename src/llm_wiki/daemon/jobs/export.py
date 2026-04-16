"""Export daemon job."""

import logging
from pathlib import Path
from typing import Any

from llm_wiki.export.graph import GraphExporter
from llm_wiki.export.json_sidecar import JSONSidecarExporter
from llm_wiki.export.llmsfull import LLMSFullExporter
from llm_wiki.export.llmstxt import LLMSTxtExporter
from llm_wiki.export.sitemap import SitemapGenerator

logger = logging.getLogger(__name__)


class ExportJob:
    """Daemon job for running all exporters."""

    def __init__(self, wiki_base: Path | None = None):
        """Initialize export job.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)
        """
        self.wiki_base = wiki_base or Path("wiki_system")

        # Initialize exporters
        self.llmstxt_exporter = LLMSTxtExporter(wiki_base=self.wiki_base)
        self.llmsfull_exporter = LLMSFullExporter(wiki_base=self.wiki_base)
        self.json_exporter = JSONSidecarExporter(wiki_base=self.wiki_base)
        self.graph_exporter = GraphExporter(wiki_base=self.wiki_base)
        self.sitemap_generator = SitemapGenerator(wiki_base=self.wiki_base)

    def execute(self) -> dict[str, Any]:
        """Execute all exporters.

        Returns:
            Dictionary with export statistics
        """
        logger.info("Starting export job")

        try:
            # Run all exporters
            llmstxt_path = self.llmstxt_exporter.export_all()
            llmsfull_path = self.llmsfull_exporter.export_all()
            json_count = self.json_exporter.export_all()
            graph_path = self.graph_exporter.export_json()
            sitemap_path = self.sitemap_generator.generate()

            stats = {
                "status": "success",
                "llmstxt_path": str(llmstxt_path),
                "llmsfull_path": str(llmsfull_path),
                "json_sidecars": json_count,
                "graph_path": str(graph_path),
                "sitemap_path": str(sitemap_path),
            }

            logger.info(f"Export job complete: {stats}")

            return stats

        except Exception as e:
            logger.error(f"Export job failed: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
            }


def run_export_job(wiki_base: Path | None = None) -> dict[str, Any]:
    """Run export job.

    This function is called by the daemon scheduler.

    Args:
        wiki_base: Base wiki directory (defaults to wiki_system/)

    Returns:
        Dictionary with export statistics
    """
    job = ExportJob(wiki_base=wiki_base)
    return job.execute()

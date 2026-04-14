"""Inbox watcher for file ingestion."""

import logging
import shutil
from pathlib import Path

from llm_wiki.adapters.base import AdapterRegistry
from llm_wiki.adapters.markdown import MarkdownAdapter
from llm_wiki.adapters.text import TextAdapter
from llm_wiki.ingest.normalizer import NormalizationPipeline

logger = logging.getLogger(__name__)


class InboxWatcher:
    """Watches inbox directory for new files and processes them."""

    def __init__(
        self,
        inbox_dir: Path | None = None,
        config_dir: Path | None = None,
    ):
        """Initialize inbox watcher.

        Args:
            inbox_dir: Base inbox directory (defaults to wiki_system/inbox)
            config_dir: Config directory (defaults to config/)
        """
        self.inbox_dir = inbox_dir or Path("wiki_system/inbox")
        self.new_dir = self.inbox_dir / "new"
        self.processing_dir = self.inbox_dir / "processing"
        self.done_dir = self.inbox_dir / "done"
        self.failed_dir = self.inbox_dir / "failed"

        # Ensure directories exist
        for directory in [self.new_dir, self.processing_dir, self.done_dir, self.failed_dir]:
            directory.mkdir(parents=True, exist_ok=True)

        # Set up normalization pipeline
        registry = AdapterRegistry()
        registry.register(MarkdownAdapter)
        registry.register(TextAdapter)
        self.pipeline = NormalizationPipeline(registry, config_dir)

    def scan(self) -> dict[str, int]:
        """Scan inbox for new files and process them.

        Returns:
            Dictionary with processing stats (processed, failed, skipped)
        """
        stats = {"processed": 0, "failed": 0, "skipped": 0}

        # Get all files in new/ directory
        files = list(self.new_dir.glob("*"))
        files = [f for f in files if f.is_file()]

        logger.info(f"Found {len(files)} file(s) in inbox")

        for filepath in files:
            try:
                self._process_file(filepath)
                stats["processed"] += 1
            except Exception as e:
                logger.error(f"Failed to process {filepath.name}: {e}")
                self._move_to_failed(filepath, str(e))
                stats["failed"] += 1

        return stats

    def _process_file(self, filepath: Path) -> None:
        """Process a single file from inbox.

        Args:
            filepath: Path to file in new/ directory

        Raises:
            Exception: If processing fails
        """
        logger.info(f"Processing {filepath.name}")

        # Move to processing/ directory
        processing_path = self.processing_dir / filepath.name
        shutil.move(str(filepath), str(processing_path))

        try:
            # Process through normalization pipeline
            output_path = self.pipeline.process_file(processing_path)
            logger.info(f"Normalized to {output_path}")

            # Move to done/ directory
            done_path = self.done_dir / processing_path.name
            shutil.move(str(processing_path), str(done_path))
            logger.info(f"Moved to done: {processing_path.name}")

        except Exception as e:
            # Move back to new/ on failure so it can be retried
            shutil.move(str(processing_path), str(filepath))
            raise e

    def _move_to_failed(self, filepath: Path, error: str) -> None:
        """Move file to failed/ directory.

        Args:
            filepath: Path to file
            error: Error message
        """
        failed_path = self.failed_dir / filepath.name

        # If file already exists in failed, append counter
        if failed_path.exists():
            counter = 1
            while (self.failed_dir / f"{filepath.stem}_{counter}{filepath.suffix}").exists():
                counter += 1
            failed_path = self.failed_dir / f"{filepath.stem}_{counter}{filepath.suffix}"

        shutil.move(str(filepath), str(failed_path))

        # Write error log
        error_log = failed_path.with_suffix(failed_path.suffix + ".error")
        error_log.write_text(error, encoding="utf-8")

        logger.info(f"Moved to failed: {filepath.name}")

"""Inbox watcher for file ingestion."""

import logging
import shutil
from pathlib import Path

from llm_wiki.adapters.base import AdapterRegistry
from llm_wiki.adapters.markdown import MarkdownAdapter
from llm_wiki.adapters.obsidian import ObsidianVaultAdapter
from llm_wiki.adapters.text import TextAdapter
from llm_wiki.ingest.failed import FailedIngestionsTracker, FailureReason
from llm_wiki.ingest.normalizer import NormalizationPipeline

logger = logging.getLogger(__name__)


class InboxWatcher:
    """Watches inbox directory for new files and processes them."""

    def __init__(
        self,
        inbox_dir: Path | None = None,
        config_dir: Path | None = None,
        failed_tracker: FailedIngestionsTracker | None = None,
    ):
        """Initialize inbox watcher.

        Args:
            inbox_dir: Base inbox directory (defaults to wiki_system/inbox)
            config_dir: Config directory (defaults to config/)
            failed_tracker: Optional tracker for failed ingestions
        """
        self.inbox_dir = inbox_dir or Path("wiki_system/inbox")
        self.new_dir = self.inbox_dir / "new"
        self.processing_dir = self.inbox_dir / "processing"
        self.done_dir = self.inbox_dir / "done"
        self.failed_dir = self.inbox_dir / "failed"

        # Ensure directories exist
        for directory in [self.new_dir, self.processing_dir, self.done_dir, self.failed_dir]:
            directory.mkdir(parents=True, exist_ok=True)

        # Set up failed ingestion tracker
        if failed_tracker is None:
            wiki_base = self.inbox_dir.parent  # Go up from inbox/ to wiki_system/
            state_dir = wiki_base / "state"
            failed_tracker = FailedIngestionsTracker(state_dir=state_dir)
        self.failed_tracker = failed_tracker

        # Set up normalization pipeline
        registry = AdapterRegistry()
        registry.register(MarkdownAdapter)
        registry.register(ObsidianVaultAdapter)
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

        # Record failure in tracker
        failure_reason = self._determine_failure_reason(error)
        self.failed_tracker.record_failure(
            file_path=failed_path,
            reason=failure_reason,
            error_message=error,
        )

        logger.info(f"Moved to failed: {filepath.name}")

    def _determine_failure_reason(self, error: str) -> FailureReason:
        """Determine the failure reason from error message.

        Args:
            error: Error message string

        Returns:
            FailureReason enum value
        """
        error_lower = error.lower()

        # Check for transient failures
        if "timeout" in error_lower:
            return FailureReason.LLM_TIMEOUT
        if "network" in error_lower or "connection" in error_lower:
            return FailureReason.NETWORK_ERROR
        if "temporary" in error_lower or "try again" in error_lower:
            return FailureReason.TEMPORARY_ERROR

        # Check for permanent failures
        if "invalid" in error_lower or "format" in error_lower:
            return FailureReason.INVALID_FORMAT
        if "corrupt" in error_lower:
            return FailureReason.CORRUPTED_FILE
        if "unsupported" in error_lower or "type" in error_lower:
            return FailureReason.UNSUPPORTED_TYPE
        if "permission" in error_lower:
            return FailureReason.PERMISSION_DENIED

        # Check for recoverable failures
        if "metadata" in error_lower:
            return FailureReason.MISSING_METADATA
        if "schema" in error_lower or "validation" in error_lower:
            return FailureReason.SCHEMA_VALIDATION_FAILED
        if "config" in error_lower:
            return FailureReason.CONFIG_ERROR

        # Default to unknown
        return FailureReason.UNKNOWN

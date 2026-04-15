"""Retry failed ingestions daemon job."""

import logging
import shutil
from pathlib import Path
from typing import Any

from llm_wiki.ingest.failed import FailedIngestionsTracker
from llm_wiki.ingest.watcher import InboxWatcher

logger = logging.getLogger(__name__)


class RetryFailedIngestsJob:
    """Daemon job for retrying failed file ingestions."""

    def __init__(self, wiki_base: Path | None = None):
        """Initialize retry failed ingests job.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)
        """
        self.wiki_base = wiki_base or Path("wiki_system")

        # Initialize tracker and watcher
        state_dir = self.wiki_base / "state"
        self.tracker = FailedIngestionsTracker(state_dir=state_dir)
        self.watcher = InboxWatcher(inbox_dir=self.wiki_base / "inbox")

    def execute(self) -> dict[str, Any]:
        """Execute retry of failed ingestions.

        Returns:
            Dictionary with retry statistics
        """
        logger.info("Starting retry failed ingests job")

        try:
            # Get retryable ingestions
            retryable = self.tracker.get_retryable_ingestions()
            logger.info(f"Found {len(retryable)} retryable ingestions")

            if not retryable:
                return {
                    "status": "success",
                    "retried": 0,
                    "succeeded": 0,
                    "failed": 0,
                }

            retried_count = 0
            succeeded_count = 0
            failed_count = 0

            # Process each retryable ingestion
            for ingestion in retryable:
                file_path = ingestion.file_path
                failed_path = self.watcher.failed_dir / file_path.name

                # Check if file exists in failed directory
                if not failed_path.exists():
                    logger.warning(f"Failed file no longer exists: {failed_path}, clearing record")
                    self.tracker.clear_ingestion(file_path)
                    continue

                try:
                    # Move file from failed/ to new/ directory
                    new_path = self.watcher.new_dir / failed_path.name
                    if new_path.exists():
                        # Handle naming conflict
                        counter = 1
                        while (
                            self.watcher.new_dir
                            / f"{failed_path.stem}_{counter}{failed_path.suffix}"
                        ).exists():
                            counter += 1
                        new_path = (
                            self.watcher.new_dir
                            / f"{failed_path.stem}_{counter}{failed_path.suffix}"
                        )

                    shutil.move(str(failed_path), str(new_path))
                    logger.debug(f"Moved {failed_path.name} from failed/ to new/")

                    # Remove associated error file
                    error_file = failed_path.with_suffix(failed_path.suffix + ".error")
                    if error_file.exists():
                        error_file.unlink()
                        logger.debug(f"Removed error file: {error_file.name}")

                    retried_count += 1

                    # Re-process through watcher
                    logger.info(f"Re-processing: {new_path.name}")
                    try:
                        self.watcher._process_file(new_path)
                        # Success - clear the record
                        self.tracker.clear_ingestion(file_path)
                        succeeded_count += 1
                        logger.info(f"Successfully re-processed: {new_path.name}")
                    except Exception as process_error:
                        # Failure - record the failure again

                        failure_reason = self._determine_failure_reason(str(process_error))
                        self.tracker.record_failure(
                            file_path=file_path,
                            reason=failure_reason,
                            error_message=str(process_error),
                            max_retries=ingestion.max_retries,
                        )
                        failed_count += 1
                        logger.warning(
                            f"Re-processing failed again: {new_path.name}: {process_error}"
                        )

                except Exception as e:
                    logger.error(f"Error processing retry for {file_path.name}: {e}", exc_info=True)
                    failed_count += 1

            stats = {
                "status": "success",
                "retried": retried_count,
                "succeeded": succeeded_count,
                "failed": failed_count,
            }

            logger.info(f"Retry job complete: {stats}")
            return stats

        except Exception as e:
            logger.error(f"Retry failed ingests job failed: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "retried": 0,
                "succeeded": 0,
                "failed": 0,
            }

    def _determine_failure_reason(self, error: str) -> str:
        """Determine the failure reason from error message.

        Args:
            error: Error message string

        Returns:
            FailureReason value as string
        """
        from llm_wiki.ingest.failed import FailureReason

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


def run_retry_failed_ingests(wiki_base: Path | None = None) -> dict[str, Any]:
    """Run retry failed ingests job.

    This function is called by the daemon scheduler.

    Args:
        wiki_base: Base wiki directory (defaults to wiki_system/)

    Returns:
        Dictionary with retry statistics
    """
    job = RetryFailedIngestsJob(wiki_base=wiki_base)
    return job.execute()

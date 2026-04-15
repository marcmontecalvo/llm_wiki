"""Tests for RetryFailedIngestsJob."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from llm_wiki.daemon.jobs.retry_failed_ingests import (
    RetryFailedIngestsJob,
    run_retry_failed_ingests,
)
from llm_wiki.ingest.failed import FailedIngestion, FailureReason


class TestRetryFailedIngestsJob:
    """Test RetryFailedIngestsJob."""

    @pytest.fixture
    def temp_wiki_base(self):
        """Create temporary wiki base directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wiki_base = Path(tmpdir)

            # Create necessary directories
            state_dir = wiki_base / "state"
            inbox_dir = wiki_base / "inbox"
            for subdir in [
                state_dir,
                inbox_dir / "new",
                inbox_dir / "processing",
                inbox_dir / "done",
                inbox_dir / "failed",
            ]:
                subdir.mkdir(parents=True, exist_ok=True)

            yield wiki_base

    def test_initialization(self, temp_wiki_base):
        """Test job initialization."""
        job = RetryFailedIngestsJob(wiki_base=temp_wiki_base)

        assert job.wiki_base == temp_wiki_base
        assert job.tracker is not None
        assert job.watcher is not None

    def test_execute_no_retryable_ingestions(self, temp_wiki_base):
        """Test execute when no ingestions are retryable."""
        job = RetryFailedIngestsJob(wiki_base=temp_wiki_base)

        result = job.execute()

        assert result["status"] == "success"
        assert result["retried"] == 0
        assert result["succeeded"] == 0
        assert result["failed"] == 0

    def test_execute_with_missing_failed_file(self, temp_wiki_base):
        """Test execute when failed file no longer exists."""
        job = RetryFailedIngestsJob(wiki_base=temp_wiki_base)

        # Record a failure for a file that doesn't exist
        missing_path = Path("/nonexistent/file.md")
        job.tracker.record_failure(
            missing_path,
            FailureReason.LLM_TIMEOUT,
        )

        # Mock get_retryable_ingestions to return the non-existent file
        with patch.object(job.tracker, "get_retryable_ingestions") as mock_get:
            ingestion = FailedIngestion(
                file_path=missing_path,
                original_timestamp=__import__("datetime").datetime.now(__import__("datetime").UTC),
                failure_reason=FailureReason.LLM_TIMEOUT,
            )
            mock_get.return_value = [ingestion]

            result = job.execute()

            assert result["status"] == "success"
            assert result["retried"] == 0

    def test_execute_retry_success(self, temp_wiki_base):
        """Test execute with successful retry."""
        from datetime import UTC, datetime

        job = RetryFailedIngestsJob(wiki_base=temp_wiki_base)

        # Create a mock ingestion for a file that exists
        test_file = job.watcher.failed_dir / "test.md"
        test_file.write_text("Content", encoding="utf-8")

        ingestion = FailedIngestion(
            file_path=test_file,
            original_timestamp=datetime.now(UTC),
            failure_reason=FailureReason.LLM_TIMEOUT,
        )

        # Mock tracker methods
        with (
            patch.object(job.tracker, "get_retryable_ingestions") as mock_get,
            patch.object(job.tracker, "clear_ingestion"),
            patch.object(job.watcher, "_process_file") as mock_process,
        ):
            mock_get.return_value = [ingestion]
            mock_process.return_value = None

            result = job.execute()

            assert result["status"] == "success"
            assert result["retried"] == 1
            assert result["succeeded"] == 1

    def test_execute_retry_fails(self, temp_wiki_base):
        """Test execute when retry fails again."""
        from datetime import UTC, datetime

        job = RetryFailedIngestsJob(wiki_base=temp_wiki_base)

        # Create a mock ingestion
        test_file = job.watcher.failed_dir / "test.md"
        test_file.write_text("Content", encoding="utf-8")

        ingestion = FailedIngestion(
            file_path=test_file,
            original_timestamp=datetime.now(UTC),
            failure_reason=FailureReason.LLM_TIMEOUT,
        )

        # Mock tracker and watcher methods
        with (
            patch.object(job.tracker, "get_retryable_ingestions") as mock_get,
            patch.object(job.tracker, "record_failure") as mock_record,
            patch.object(job.watcher, "_process_file") as mock_process,
        ):
            mock_get.return_value = [ingestion]
            mock_process.side_effect = ValueError("Processing failed")

            result = job.execute()

            assert result["status"] == "success"
            assert result["retried"] == 1
            assert result["failed"] == 1
            mock_record.assert_called_once()

    def test_determine_failure_reason_timeout(self, temp_wiki_base):
        """Test failure reason determination for timeout."""
        job = RetryFailedIngestsJob(wiki_base=temp_wiki_base)

        reason = job._determine_failure_reason("Request timeout after 30 seconds")
        assert reason == FailureReason.LLM_TIMEOUT

    def test_determine_failure_reason_network(self, temp_wiki_base):
        """Test failure reason determination for network error."""
        job = RetryFailedIngestsJob(wiki_base=temp_wiki_base)

        reason = job._determine_failure_reason("Network connection failed")
        assert reason == FailureReason.NETWORK_ERROR

    def test_determine_failure_reason_invalid_format(self, temp_wiki_base):
        """Test failure reason determination for invalid format."""
        job = RetryFailedIngestsJob(wiki_base=temp_wiki_base)

        reason = job._determine_failure_reason("Invalid format in file")
        assert reason == FailureReason.INVALID_FORMAT

    def test_determine_failure_reason_permission(self, temp_wiki_base):
        """Test failure reason determination for permission denied."""
        job = RetryFailedIngestsJob(wiki_base=temp_wiki_base)

        reason = job._determine_failure_reason("Permission denied: cannot read file")
        assert reason == FailureReason.PERMISSION_DENIED

    def test_determine_failure_reason_schema(self, temp_wiki_base):
        """Test failure reason determination for schema validation."""
        job = RetryFailedIngestsJob(wiki_base=temp_wiki_base)

        reason = job._determine_failure_reason("Schema validation failed")
        assert reason == FailureReason.SCHEMA_VALIDATION_FAILED

    def test_determine_failure_reason_unknown(self, temp_wiki_base):
        """Test failure reason determination for unknown error."""
        job = RetryFailedIngestsJob(wiki_base=temp_wiki_base)

        reason = job._determine_failure_reason("Some random error")
        assert reason == FailureReason.UNKNOWN

    def test_run_retry_failed_ingests_function(self, temp_wiki_base):
        """Test the module-level run_retry_failed_ingests function."""
        result = run_retry_failed_ingests(wiki_base=temp_wiki_base)

        assert result["status"] == "success"
        assert "retried" in result
        assert "succeeded" in result
        assert "failed" in result

    def test_execute_exception_handling(self, temp_wiki_base):
        """Test exception handling in execute method."""
        job = RetryFailedIngestsJob(wiki_base=temp_wiki_base)

        # Mock tracker to raise an exception
        with patch.object(job.tracker, "get_retryable_ingestions") as mock_get:
            mock_get.side_effect = RuntimeError("Database error")

            result = job.execute()

            assert result["status"] == "error"
            assert "error" in result
            assert result["retried"] == 0

    def test_execute_clears_error_file(self, temp_wiki_base):
        """Test that .error files are created and tracked."""
        from datetime import UTC, datetime

        job = RetryFailedIngestsJob(wiki_base=temp_wiki_base)

        # Create a file with error
        test_file = job.watcher.failed_dir / "test.md"
        test_file.write_text("Content", encoding="utf-8")
        error_file = test_file.with_suffix(test_file.suffix + ".error")
        error_file.write_text("Test error", encoding="utf-8")

        assert error_file.exists()

        ingestion = FailedIngestion(
            file_path=test_file,
            original_timestamp=datetime.now(UTC),
            failure_reason=FailureReason.LLM_TIMEOUT,
        )

        with (
            patch.object(job.tracker, "get_retryable_ingestions") as mock_get,
            patch.object(job.tracker, "clear_ingestion"),
            patch.object(job.watcher, "_process_file") as mock_process,
        ):
            mock_get.return_value = [ingestion]
            mock_process.return_value = None

            job.execute()

            # Error file should be removed after successful retry
            assert not error_file.exists()

    def test_execute_moves_file_to_new(self, temp_wiki_base):
        """Test that files are moved from failed to new directory."""
        from datetime import UTC, datetime

        job = RetryFailedIngestsJob(wiki_base=temp_wiki_base)

        # Create a file in failed directory
        test_file = job.watcher.failed_dir / "test.md"
        test_file.write_text("Content", encoding="utf-8")

        ingestion = FailedIngestion(
            file_path=test_file,
            original_timestamp=datetime.now(UTC),
            failure_reason=FailureReason.LLM_TIMEOUT,
        )

        with (
            patch.object(job.tracker, "get_retryable_ingestions") as mock_get,
            patch.object(job.tracker, "clear_ingestion"),
            patch.object(job.watcher, "_process_file") as mock_process,
        ):
            mock_get.return_value = [ingestion]
            mock_process.return_value = None

            job.execute()

            # File should be in new directory
            assert (job.watcher.new_dir / "test.md").exists()
            assert not test_file.exists()

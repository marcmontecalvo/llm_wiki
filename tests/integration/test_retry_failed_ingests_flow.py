"""Integration tests for complete retry failed ingests flow."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from llm_wiki.daemon.jobs.retry_failed_ingests import RetryFailedIngestsJob
from llm_wiki.ingest.failed import FailedIngestion, FailedIngestionsTracker, FailureReason
from llm_wiki.ingest.watcher import InboxWatcher


class TestRetryFailedIngestsFlow:
    """Integration tests for the complete retry flow."""

    @pytest.fixture
    def temp_wiki_system(self):
        """Create a temporary wiki_system directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wiki_base = Path(tmpdir)

            # Create directory structure
            directories = [
                wiki_base / "state",
                wiki_base / "inbox" / "new",
                wiki_base / "inbox" / "processing",
                wiki_base / "inbox" / "done",
                wiki_base / "inbox" / "failed",
            ]

            for directory in directories:
                directory.mkdir(parents=True, exist_ok=True)

            yield wiki_base

    def test_watcher_integration_with_tracker(self, temp_wiki_system):
        """Test that watcher properly integrates with failure tracker."""
        watcher = InboxWatcher(inbox_dir=temp_wiki_system / "inbox")

        # Create and fail a file
        test_file = watcher.new_dir / "test.md"
        test_file.write_text("Content", encoding="utf-8")

        watcher._move_to_failed(test_file, "Network timeout")

        # Check that failure was recorded
        failed_file = watcher.failed_dir / "test.md"
        assert failed_file.exists()

        # Check tracker has the record
        all_failed = watcher.failed_tracker.get_all_failed()
        assert len(all_failed) == 1
        assert all_failed[0].failure_reason == FailureReason.LLM_TIMEOUT

    def test_failure_reason_detection(self, temp_wiki_system):
        """Test failure reason detection through watcher."""
        watcher = InboxWatcher(inbox_dir=temp_wiki_system / "inbox")

        test_cases = [
            ("test1.md", "Request timeout", FailureReason.LLM_TIMEOUT),
            ("test2.md", "Connection refused", FailureReason.NETWORK_ERROR),
            ("test3.md", "Invalid file format", FailureReason.INVALID_FORMAT),
            ("test4.md", "Permission denied", FailureReason.PERMISSION_DENIED),
        ]

        for filename, error_msg, _expected_reason in test_cases:
            test_file = watcher.new_dir / filename
            test_file.write_text("Content", encoding="utf-8")
            watcher._move_to_failed(test_file, error_msg)

        # Check all reasons were recorded correctly
        all_failed = watcher.failed_tracker.get_all_failed()
        assert len(all_failed) == 4

        for i, (_, _, expected_reason) in enumerate(test_cases):
            assert all_failed[i].failure_reason == expected_reason

    def test_job_with_mock_retryable_files(self, temp_wiki_system):
        """Test retry job with mocked retryable files."""
        from datetime import UTC, datetime

        job = RetryFailedIngestsJob(wiki_base=temp_wiki_system)

        # Create some files in failed directory
        for i in range(3):
            test_file = job.watcher.failed_dir / f"test_{i}.md"
            test_file.write_text(f"Content {i}", encoding="utf-8")

        # Create mock ingestions
        ingestions = []
        for i in range(3):
            failed_file = job.watcher.failed_dir / f"test_{i}.md"
            ingestion = FailedIngestion(
                file_path=failed_file,
                original_timestamp=datetime.now(UTC),
                failure_reason=FailureReason.TEMPORARY_ERROR,
            )
            ingestions.append(ingestion)

        # Mock the tracker and watcher
        with (
            patch.object(job.tracker, "get_retryable_ingestions") as mock_get,
            patch.object(job.tracker, "clear_ingestion") as mock_clear,
            patch.object(job.watcher, "_process_file") as mock_process,
        ):
            mock_get.return_value = ingestions
            mock_process.return_value = None

            result = job.execute()

            assert result["status"] == "success"
            assert result["retried"] == 3
            assert result["succeeded"] == 3
            assert mock_clear.call_count == 3

    def test_error_file_tracking(self, temp_wiki_system):
        """Test that error files are properly created and tracked."""
        watcher = InboxWatcher(inbox_dir=temp_wiki_system / "inbox")

        # Create a file and fail it
        test_file = watcher.new_dir / "test.md"
        test_file.write_text("Content", encoding="utf-8")

        error_message = "Processing failed with error"
        watcher._move_to_failed(test_file, error_message)

        # Check error file exists
        failed_file = watcher.failed_dir / "test.md"
        error_file = failed_file.with_suffix(".md.error")

        assert error_file.exists()
        assert error_file.read_text(encoding="utf-8") == error_message

    def test_persistence_across_instances(self, temp_wiki_system):
        """Test that state persists across tracker instances."""
        # First instance - record a failure
        tracker1 = FailedIngestionsTracker(state_dir=temp_wiki_system / "state")
        test_file = Path("/test/file.md")

        tracker1.record_failure(test_file, FailureReason.LLM_TIMEOUT)

        # Second instance - should see the failure
        tracker2 = FailedIngestionsTracker(state_dir=temp_wiki_system / "state")
        all_failed = tracker2.get_all_failed()

        assert len(all_failed) == 1
        assert all_failed[0].file_path == test_file

    def test_retry_job_no_retryable(self, temp_wiki_system):
        """Test retry job with no retryable ingestions."""
        job = RetryFailedIngestsJob(wiki_base=temp_wiki_system)

        result = job.execute()

        assert result["status"] == "success"
        assert result["retried"] == 0
        assert result["succeeded"] == 0
        assert result["failed"] == 0

    def test_job_error_handling(self, temp_wiki_system):
        """Test job handles errors gracefully."""
        job = RetryFailedIngestsJob(wiki_base=temp_wiki_system)

        # Simulate an error in tracker
        with patch.object(job.tracker, "get_retryable_ingestions") as mock_get:
            mock_get.side_effect = RuntimeError("Database connection failed")

            result = job.execute()

            assert result["status"] == "error"
            assert "error" in result

    def test_watcher_categorization_logic(self, temp_wiki_system):
        """Test the watcher's failure reason categorization."""
        watcher = InboxWatcher(inbox_dir=temp_wiki_system / "inbox")

        # Test various error messages
        test_cases = {
            "timeout occurred": FailureReason.LLM_TIMEOUT,
            "network error": FailureReason.NETWORK_ERROR,
            "invalid format": FailureReason.INVALID_FORMAT,
            "corrupted data": FailureReason.CORRUPTED_FILE,
            "unsupported type": FailureReason.UNSUPPORTED_TYPE,
            "permission denied": FailureReason.PERMISSION_DENIED,
            "missing metadata": FailureReason.MISSING_METADATA,
            "schema validation": FailureReason.SCHEMA_VALIDATION_FAILED,
            "config error": FailureReason.CONFIG_ERROR,
            "random unknown error": FailureReason.UNKNOWN,
        }

        for error_msg, expected_reason in test_cases.items():
            reason = watcher._determine_failure_reason(error_msg)
            assert reason == expected_reason, f"Failed for: {error_msg}"

    def test_multiple_job_executions(self, temp_wiki_system):
        """Test multiple job executions work correctly."""
        job = RetryFailedIngestsJob(wiki_base=temp_wiki_system)

        # First execution
        result1 = job.execute()
        assert result1["status"] == "success"

        # Second execution
        result2 = job.execute()
        assert result2["status"] == "success"

        # Both should complete without errors
        assert result1["retried"] == 0
        assert result2["retried"] == 0

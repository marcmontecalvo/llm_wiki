"""Tests for FailedIngestionsTracker."""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from llm_wiki.ingest.failed import (
    FailedIngestion,
    FailedIngestionsTracker,
    FailureReason,
    is_permanent_failure,
    is_transient_failure,
)


class TestFailureReason:
    """Test FailureReason enum and helper functions."""

    def test_transient_failures(self):
        """Test transient failure detection."""
        assert is_transient_failure(FailureReason.LLM_TIMEOUT)
        assert is_transient_failure(FailureReason.NETWORK_ERROR)
        assert is_transient_failure(FailureReason.TEMPORARY_ERROR)

    def test_permanent_failures(self):
        """Test permanent failure detection."""
        assert is_permanent_failure(FailureReason.INVALID_FORMAT)
        assert is_permanent_failure(FailureReason.CORRUPTED_FILE)
        assert is_permanent_failure(FailureReason.UNSUPPORTED_TYPE)
        assert is_permanent_failure(FailureReason.PERMISSION_DENIED)

    def test_recoverable_failures_not_permanent(self):
        """Test that recoverable failures are not marked as permanent."""
        assert not is_permanent_failure(FailureReason.MISSING_METADATA)
        assert not is_permanent_failure(FailureReason.SCHEMA_VALIDATION_FAILED)
        assert not is_permanent_failure(FailureReason.CONFIG_ERROR)

    def test_unknown_not_permanent(self):
        """Test that unknown failures are not marked as permanent."""
        assert not is_permanent_failure(FailureReason.UNKNOWN)


class TestFailedIngestion:
    """Test FailedIngestion record."""

    def test_creation(self):
        """Test creating a failed ingestion record."""
        file_path = Path("/test/file.md")
        reason = FailureReason.LLM_TIMEOUT

        ingestion = FailedIngestion(
            file_path=file_path,
            original_timestamp=datetime.now(UTC),
            failure_reason=reason,
        )

        assert ingestion.file_path == file_path
        assert ingestion.failure_reason == reason
        assert ingestion.failure_count == 1
        assert not ingestion.permanent_failure

    def test_should_retry_when_due(self):
        """Test should_retry returns True when retry is due."""
        ingestion = FailedIngestion(
            file_path=Path("/test/file.md"),
            original_timestamp=datetime.now(UTC),
            failure_reason=FailureReason.LLM_TIMEOUT,
            next_retry=datetime.now(UTC) - timedelta(seconds=1),
        )

        assert ingestion.should_retry()

    def test_should_not_retry_when_not_due(self):
        """Test should_retry returns False when retry is not due yet."""
        ingestion = FailedIngestion(
            file_path=Path("/test/file.md"),
            original_timestamp=datetime.now(UTC),
            failure_reason=FailureReason.LLM_TIMEOUT,
            next_retry=datetime.now(UTC) + timedelta(seconds=60),
        )

        assert not ingestion.should_retry()

    def test_should_not_retry_when_permanent(self):
        """Test should_retry returns False for permanent failures."""
        ingestion = FailedIngestion(
            file_path=Path("/test/file.md"),
            original_timestamp=datetime.now(UTC),
            failure_reason=FailureReason.INVALID_FORMAT,
            permanent_failure=True,
        )

        assert not ingestion.should_retry()

    def test_should_not_retry_when_max_retries_exceeded(self):
        """Test should_retry returns False when max retries exceeded."""
        ingestion = FailedIngestion(
            file_path=Path("/test/file.md"),
            original_timestamp=datetime.now(UTC),
            failure_reason=FailureReason.LLM_TIMEOUT,
            failure_count=5,
            max_retries=5,
            next_retry=datetime.now(UTC) - timedelta(seconds=1),
        )

        assert not ingestion.should_retry()

    def test_mark_as_permanent(self):
        """Test marking ingestion as permanent."""
        ingestion = FailedIngestion(
            file_path=Path("/test/file.md"),
            original_timestamp=datetime.now(UTC),
            failure_reason=FailureReason.LLM_TIMEOUT,
        )

        assert not ingestion.permanent_failure
        ingestion.mark_as_permanent()
        assert ingestion.permanent_failure

    def test_record_retry_attempt(self):
        """Test recording a retry attempt."""
        ingestion = FailedIngestion(
            file_path=Path("/test/file.md"),
            original_timestamp=datetime.now(UTC),
            failure_reason=FailureReason.LLM_TIMEOUT,
        )

        assert len(ingestion.retry_attempts) == 0

        ingestion.record_retry_attempt(success=True)
        assert len(ingestion.retry_attempts) == 1
        assert ingestion.retry_attempts[0]["success"]

        ingestion.record_retry_attempt(success=False, error="Test error")
        assert len(ingestion.retry_attempts) == 2
        assert not ingestion.retry_attempts[1]["success"]
        assert ingestion.retry_attempts[1]["error"] == "Test error"

    def test_to_dict_and_from_dict(self):
        """Test serialization and deserialization."""
        file_path = Path("/test/file.md")
        original_time = datetime.now(UTC)

        ingestion = FailedIngestion(
            file_path=file_path,
            original_timestamp=original_time,
            failure_reason=FailureReason.LLM_TIMEOUT,
            failure_count=2,
            error_message="Test error",
        )

        data = ingestion.to_dict()
        assert data["file_path"] == str(file_path)
        assert data["failure_reason"] == FailureReason.LLM_TIMEOUT
        assert data["failure_count"] == 2

        restored = FailedIngestion.from_dict(data)
        assert restored.file_path == file_path
        assert restored.failure_reason == FailureReason.LLM_TIMEOUT
        assert restored.failure_count == 2
        assert restored.error_message == "Test error"


class TestFailedIngestionsTracker:
    """Test FailedIngestionsTracker."""

    @pytest.fixture
    def temp_state_dir(self):
        """Create temporary state directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_initialization(self, temp_state_dir):
        """Test tracker initialization."""
        tracker = FailedIngestionsTracker(state_dir=temp_state_dir)

        assert tracker.state_dir == temp_state_dir
        assert tracker.state_file == temp_state_dir / "failed_ingestions.json"
        assert len(tracker._ingestions) == 0

    def test_record_failure(self, temp_state_dir):
        """Test recording a failure."""
        tracker = FailedIngestionsTracker(state_dir=temp_state_dir)
        file_path = Path("/test/file.md")

        ingestion = tracker.record_failure(
            file_path=file_path,
            reason=FailureReason.LLM_TIMEOUT,
            error_message="Timeout occurred",
        )

        assert ingestion.file_path == file_path
        assert ingestion.failure_reason == FailureReason.LLM_TIMEOUT
        assert ingestion.error_message == "Timeout occurred"

    def test_record_failure_updates_existing(self, temp_state_dir):
        """Test that recording a failure for the same file updates the record."""
        tracker = FailedIngestionsTracker(state_dir=temp_state_dir)
        file_path = Path("/test/file.md")

        tracker.record_failure(
            file_path=file_path,
            reason=FailureReason.LLM_TIMEOUT,
            error_message="First error",
        )

        ingestion = tracker.record_failure(
            file_path=file_path,
            reason=FailureReason.NETWORK_ERROR,
            error_message="Second error",
        )

        assert ingestion.failure_count == 2
        assert ingestion.failure_reason == FailureReason.NETWORK_ERROR
        assert ingestion.error_message == "Second error"

    def test_permanent_failure_on_max_retries(self, temp_state_dir):
        """Test that ingestion is marked permanent after max retries."""
        tracker = FailedIngestionsTracker(state_dir=temp_state_dir)
        file_path = Path("/test/file.md")

        for i in range(5):
            ingestion = tracker.record_failure(
                file_path=file_path,
                reason=FailureReason.LLM_TIMEOUT,
                error_message=f"Error {i + 1}",
                max_retries=5,
            )

        assert ingestion.permanent_failure
        assert ingestion.failure_count == 5

    def test_permanent_failure_reason_marks_permanent(self, temp_state_dir):
        """Test that permanent failure reasons immediately mark as permanent."""
        tracker = FailedIngestionsTracker(state_dir=temp_state_dir)
        file_path = Path("/test/file.md")

        ingestion = tracker.record_failure(
            file_path=file_path,
            reason=FailureReason.INVALID_FORMAT,
            error_message="Invalid format",
        )

        assert ingestion.permanent_failure

    def test_get_failed_ingestion(self, temp_state_dir):
        """Test retrieving a failed ingestion."""
        tracker = FailedIngestionsTracker(state_dir=temp_state_dir)
        file_path = Path("/test/file.md")

        tracker.record_failure(
            file_path=file_path,
            reason=FailureReason.LLM_TIMEOUT,
        )

        ingestion = tracker.get_failed_ingestion(file_path)
        assert ingestion is not None
        assert ingestion.file_path == file_path

    def test_get_retryable_ingestions(self, temp_state_dir):
        """Test getting retryable ingestions."""
        tracker = FailedIngestionsTracker(state_dir=temp_state_dir)

        # Record some failures
        ingestion1 = tracker.record_failure(Path("/test/file1.md"), FailureReason.LLM_TIMEOUT)
        # file2 is permanent, so won't be retryable
        tracker.record_failure(Path("/test/file2.md"), FailureReason.INVALID_FORMAT)
        # file3 is transient but not due yet
        ingestion3 = tracker.record_failure(
            Path("/test/file3.md"),
            FailureReason.LLM_TIMEOUT,
            max_retries=5,
        )

        # Mark file1 as ready to retry (in the past)
        ingestion1.next_retry = datetime.now(UTC) - timedelta(seconds=1)
        # Mark file3 as not due for retry (in the future)
        ingestion3.next_retry = datetime.now(UTC) + timedelta(hours=1)

        retryable = tracker.get_retryable_ingestions()
        assert len(retryable) == 1
        assert retryable[0].file_path == Path("/test/file1.md")

        # file2 should be in permanent failures
        permanent = tracker.get_permanent_failures()
        assert len(permanent) == 1
        assert permanent[0].file_path == Path("/test/file2.md")

    def test_get_all_failed(self, temp_state_dir):
        """Test getting all failed ingestions."""
        tracker = FailedIngestionsTracker(state_dir=temp_state_dir)

        tracker.record_failure(Path("/test/file1.md"), FailureReason.LLM_TIMEOUT)
        tracker.record_failure(Path("/test/file2.md"), FailureReason.INVALID_FORMAT)

        all_failed = tracker.get_all_failed()
        assert len(all_failed) == 2

    def test_get_permanent_failures(self, temp_state_dir):
        """Test getting permanent failures."""
        tracker = FailedIngestionsTracker(state_dir=temp_state_dir)

        tracker.record_failure(Path("/test/file1.md"), FailureReason.LLM_TIMEOUT)
        tracker.record_failure(Path("/test/file2.md"), FailureReason.INVALID_FORMAT)

        permanent = tracker.get_permanent_failures()
        assert len(permanent) == 1
        assert permanent[0].file_path == Path("/test/file2.md")

    def test_clear_ingestion(self, temp_state_dir):
        """Test clearing an ingestion record."""
        tracker = FailedIngestionsTracker(state_dir=temp_state_dir)
        file_path = Path("/test/file.md")

        tracker.record_failure(file_path, FailureReason.LLM_TIMEOUT)
        assert tracker.get_failed_ingestion(file_path) is not None

        tracker.clear_ingestion(file_path)
        assert tracker.get_failed_ingestion(file_path) is None

    def test_clear_all(self, temp_state_dir):
        """Test clearing all ingestion records."""
        tracker = FailedIngestionsTracker(state_dir=temp_state_dir)

        tracker.record_failure(Path("/test/file1.md"), FailureReason.LLM_TIMEOUT)
        tracker.record_failure(Path("/test/file2.md"), FailureReason.NETWORK_ERROR)
        assert len(tracker.get_all_failed()) == 2

        tracker.clear_all()
        assert len(tracker.get_all_failed()) == 0

    def test_persistence(self, temp_state_dir):
        """Test that state is persisted to disk."""
        tracker1 = FailedIngestionsTracker(state_dir=temp_state_dir)
        file_path = Path("/test/file.md")

        tracker1.record_failure(file_path, FailureReason.LLM_TIMEOUT)

        # Create new tracker instance
        tracker2 = FailedIngestionsTracker(state_dir=temp_state_dir)

        ingestion = tracker2.get_failed_ingestion(file_path)
        assert ingestion is not None
        assert ingestion.failure_reason == FailureReason.LLM_TIMEOUT

    def test_get_stats(self, temp_state_dir):
        """Test getting statistics."""
        tracker = FailedIngestionsTracker(state_dir=temp_state_dir)

        tracker.record_failure(Path("/test/file1.md"), FailureReason.LLM_TIMEOUT)
        tracker.record_failure(Path("/test/file2.md"), FailureReason.NETWORK_ERROR)
        tracker.record_failure(Path("/test/file3.md"), FailureReason.INVALID_FORMAT)

        stats = tracker.get_stats()
        assert stats["total_failed"] == 3
        assert stats["permanent_failures"] == 1
        assert stats["transient_failures"] == 2
        assert FailureReason.LLM_TIMEOUT in stats["by_reason"]

    def test_exponential_backoff_delays(self, temp_state_dir):
        """Test that retry delays increase exponentially."""
        tracker = FailedIngestionsTracker(state_dir=temp_state_dir)
        file_path = Path("/test/file.md")

        # Record multiple failures
        for _i in range(3):
            tracker.record_failure(
                file_path,
                FailureReason.LLM_TIMEOUT,
                max_retries=5,
            )

        ingestion = tracker.get_failed_ingestion(file_path)

        # Next retry should be scheduled
        assert ingestion.next_retry > datetime.now(UTC)

        # Second failure should have longer delay
        first_delay = (ingestion.next_retry - datetime.now(UTC)).total_seconds()

        tracker.record_failure(
            file_path,
            FailureReason.LLM_TIMEOUT,
            max_retries=5,
        )

        ingestion = tracker.get_failed_ingestion(file_path)
        second_delay = (ingestion.next_retry - datetime.now(UTC)).total_seconds()

        # Second delay should be greater than first
        assert second_delay > first_delay

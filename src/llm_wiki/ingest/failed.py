"""Failed ingestion tracking and management."""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FailureReason(StrEnum):
    """Categories of ingestion failures."""

    # Transient failures - should be retried
    LLM_TIMEOUT = "llm_timeout"
    NETWORK_ERROR = "network_error"
    TEMPORARY_ERROR = "temporary_error"

    # Permanent failures - should not be retried
    INVALID_FORMAT = "invalid_format"
    CORRUPTED_FILE = "corrupted_file"
    UNSUPPORTED_TYPE = "unsupported_type"
    PERMISSION_DENIED = "permission_denied"

    # Recoverable failures - can be fixed and retried
    MISSING_METADATA = "missing_metadata"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    CONFIG_ERROR = "config_error"

    # Unknown
    UNKNOWN = "unknown"


def is_transient_failure(reason: FailureReason | str) -> bool:
    """Check if a failure reason is transient (should be retried).

    Args:
        reason: Failure reason enum or string

    Returns:
        True if failure is transient
    """
    transient_reasons = {
        FailureReason.LLM_TIMEOUT,
        FailureReason.NETWORK_ERROR,
        FailureReason.TEMPORARY_ERROR,
    }
    return reason in transient_reasons


def is_permanent_failure(reason: FailureReason | str) -> bool:
    """Check if a failure reason is permanent (should not be retried).

    Args:
        reason: Failure reason enum or string

    Returns:
        True if failure is permanent
    """
    permanent_reasons = {
        FailureReason.INVALID_FORMAT,
        FailureReason.CORRUPTED_FILE,
        FailureReason.UNSUPPORTED_TYPE,
        FailureReason.PERMISSION_DENIED,
    }
    return reason in permanent_reasons


@dataclass
class FailedIngestion:
    """Record of a failed file ingestion."""

    file_path: Path
    original_timestamp: datetime
    failure_reason: str  # FailureReason value
    failure_count: int = 1
    last_attempt: datetime = field(default_factory=lambda: datetime.now(UTC))
    next_retry: datetime = field(default_factory=lambda: datetime.now(UTC))
    max_retries: int = 5
    permanent_failure: bool = False
    error_message: str = ""
    retry_attempts: list[dict[str, Any]] = field(default_factory=list)

    def should_retry(self) -> bool:
        """Check if this ingestion should be retried.

        Returns:
            True if should retry
        """
        if self.permanent_failure:
            return False

        if self.failure_count >= self.max_retries:
            return False

        # Check if retry is due
        return datetime.now(UTC) >= self.next_retry

    def mark_as_permanent(self) -> None:
        """Mark this ingestion as permanently failed."""
        self.permanent_failure = True

    def record_retry_attempt(self, success: bool, error: str = "") -> None:
        """Record a retry attempt.

        Args:
            success: Whether the retry succeeded
            error: Error message if retry failed
        """
        self.retry_attempts.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "success": success,
                "error": error,
                "failure_count": self.failure_count,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation
        """
        data = asdict(self)
        data["file_path"] = str(self.file_path)
        data["original_timestamp"] = self.original_timestamp.isoformat()
        data["last_attempt"] = self.last_attempt.isoformat()
        data["next_retry"] = self.next_retry.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FailedIngestion":
        """Create from dictionary.

        Args:
            data: Dictionary with ingestion data

        Returns:
            FailedIngestion instance
        """
        return cls(
            file_path=Path(data["file_path"]),
            original_timestamp=datetime.fromisoformat(data["original_timestamp"]),
            failure_reason=data["failure_reason"],
            failure_count=data.get("failure_count", 1),
            last_attempt=datetime.fromisoformat(
                data.get("last_attempt", datetime.now(UTC).isoformat())
            ),
            next_retry=datetime.fromisoformat(
                data.get("next_retry", datetime.now(UTC).isoformat())
            ),
            max_retries=data.get("max_retries", 5),
            permanent_failure=data.get("permanent_failure", False),
            error_message=data.get("error_message", ""),
            retry_attempts=data.get("retry_attempts", []),
        )


class FailedIngestionsTracker:
    """Tracks and manages failed ingestions."""

    # Exponential backoff delays in seconds
    DEFAULT_RETRY_DELAYS = [
        5 * 60,  # 5 minutes
        30 * 60,  # 30 minutes
        2 * 3600,  # 2 hours
        6 * 3600,  # 6 hours
        24 * 3600,  # 24 hours
    ]

    def __init__(self, state_dir: Path | None = None):
        """Initialize tracker.

        Args:
            state_dir: Directory for storing state (defaults to wiki_system/state)
        """
        self.state_dir = state_dir or Path("wiki_system/state")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "failed_ingestions.json"
        self._ingestions: dict[str, FailedIngestion] = {}
        self._load()

    def _load(self) -> None:
        """Load failed ingestions from disk."""
        if not self.state_file.exists():
            self._ingestions = {}
            return

        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            self._ingestions = {
                key: FailedIngestion.from_dict(value) for key, value in data.items()
            }
            logger.debug(f"Loaded {len(self._ingestions)} failed ingestions")
        except Exception as e:
            logger.error(f"Failed to load ingestions state: {e}")
            self._ingestions = {}

    def _save(self) -> None:
        """Save failed ingestions to disk."""
        try:
            data = {key: value.to_dict() for key, value in self._ingestions.items()}
            self.state_file.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save ingestions state: {e}")

    def _get_key(self, file_path: Path) -> str:
        """Get unique key for a file path.

        Args:
            file_path: Path to file

        Returns:
            Unique key
        """
        return str(file_path.resolve())

    def record_failure(
        self,
        file_path: Path,
        reason: FailureReason | str,
        error_message: str = "",
        max_retries: int = 5,
    ) -> FailedIngestion:
        """Record a failed ingestion.

        Args:
            file_path: Path to file that failed
            reason: Failure reason
            error_message: Detailed error message
            max_retries: Maximum retry attempts

        Returns:
            FailedIngestion record
        """
        key = self._get_key(file_path)

        if key in self._ingestions:
            # Update existing failure
            ingestion = self._ingestions[key]
            ingestion.failure_count += 1
            ingestion.last_attempt = datetime.now(UTC)
            ingestion.failure_reason = str(reason)
            ingestion.error_message = error_message
        else:
            # Create new failure record
            ingestion = FailedIngestion(
                file_path=file_path,
                original_timestamp=datetime.now(UTC),
                failure_reason=str(reason),
                error_message=error_message,
                max_retries=max_retries,
            )

        # Check if should mark as permanent
        if is_permanent_failure(ingestion.failure_reason):
            ingestion.permanent_failure = True
        elif ingestion.failure_count >= max_retries:
            ingestion.permanent_failure = True

        # Schedule next retry with exponential backoff
        if not ingestion.permanent_failure:
            delay_index = min(ingestion.failure_count - 1, len(self.DEFAULT_RETRY_DELAYS) - 1)
            delay_seconds = self.DEFAULT_RETRY_DELAYS[delay_index]
            ingestion.next_retry = datetime.now(UTC) + timedelta(seconds=delay_seconds)

        self._ingestions[key] = ingestion
        self._save()

        logger.info(
            f"Recorded failure for {file_path.name}: {reason} "
            f"(count={ingestion.failure_count}, permanent={ingestion.permanent_failure})"
        )

        return ingestion

    def get_failed_ingestion(self, file_path: Path) -> FailedIngestion | None:
        """Get a failed ingestion by path.

        Args:
            file_path: Path to file

        Returns:
            FailedIngestion or None
        """
        key = self._get_key(file_path)
        return self._ingestions.get(key)

    def get_retryable_ingestions(self) -> list[FailedIngestion]:
        """Get all ingestions due for retry.

        Returns:
            List of FailedIngestion records ready to retry
        """
        return [ingestion for ingestion in self._ingestions.values() if ingestion.should_retry()]

    def get_all_failed(self) -> list[FailedIngestion]:
        """Get all failed ingestions.

        Returns:
            List of all FailedIngestion records
        """
        return list(self._ingestions.values())

    def get_permanent_failures(self) -> list[FailedIngestion]:
        """Get all permanently failed ingestions.

        Returns:
            List of FailedIngestion records marked permanent
        """
        return [ingestion for ingestion in self._ingestions.values() if ingestion.permanent_failure]

    def clear_ingestion(self, file_path: Path) -> None:
        """Clear a failed ingestion record (when file is processed successfully).

        Args:
            file_path: Path to file
        """
        key = self._get_key(file_path)
        if key in self._ingestions:
            del self._ingestions[key]
            self._save()
            logger.debug(f"Cleared failure record for {file_path.name}")

    def mark_as_permanent(self, file_path: Path) -> bool:
        """Mark a failed ingestion as permanently failed.

        Args:
            file_path: Path to file

        Returns:
            True if the record was found and updated
        """
        key = self._get_key(file_path)
        if key not in self._ingestions:
            return False
        self._ingestions[key].mark_as_permanent()
        self._save()
        logger.debug(f"Marked as permanent failure: {file_path.name}")
        return True

    def clear_all(self) -> None:
        """Clear all failed ingestion records."""
        self._ingestions.clear()
        self._save()
        logger.debug("Cleared all failure records")

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about failed ingestions.

        Returns:
            Dictionary with stats
        """
        all_ingestions = list(self._ingestions.values())
        permanent = [i for i in all_ingestions if i.permanent_failure]
        transient = [i for i in all_ingestions if not i.permanent_failure]
        retryable = [i for i in transient if i.should_retry()]

        return {
            "total_failed": len(all_ingestions),
            "permanent_failures": len(permanent),
            "transient_failures": len(transient),
            "retryable_now": len(retryable),
            "by_reason": self._count_by_reason(all_ingestions),
        }

    def _count_by_reason(self, ingestions: list[FailedIngestion]) -> dict[str, int]:
        """Count failures by reason.

        Args:
            ingestions: List of ingestions to count

        Returns:
            Dictionary with counts by reason
        """
        counts: dict[str, int] = {}
        for ingestion in ingestions:
            reason = ingestion.failure_reason
            counts[reason] = counts.get(reason, 0) + 1
        return counts

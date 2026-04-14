"""Data models for enhanced job scheduling."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any


class JobStatus(StrEnum):
    """Possible job execution statuses."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class JobPriority(int, Enum):
    """Job priority levels (1-10, higher = more important)."""

    CRITICAL = 10  # Index corruption fix
    HIGH = 9  # Failed ingest retry
    MEDIUM_HIGH = 6  # Governance, export
    MEDIUM = 5
    LOW = 1  # Stats, cleanup


@dataclass
class JobDefinition:
    """Enhanced job definition with scheduling, priority, and retry configuration."""

    name: str
    func: Any  # Callable
    schedule: str | None = None  # Cron expression (e.g., "0 2 * * *")
    interval_seconds: float | None = None  # Interval in seconds
    priority: int = 5  # 1-10, higher = more important
    max_runtime_seconds: int = 3600  # Max seconds before timeout
    retries: int = 0  # Max retry attempts
    retry_delay_seconds: int = 60  # Seconds between retries
    enabled: bool = True
    concurrent: bool = False  # Can run concurrently with itself
    dependencies: list[str] = field(default_factory=list)  # Job names this depends on
    kwargs: dict[str, Any] = field(default_factory=dict)  # Arguments to pass to func

    def __post_init__(self) -> None:
        """Validate job definition."""
        if not self.name:
            raise ValueError("Job name cannot be empty")
        if self.schedule is None and self.interval_seconds is None:
            raise ValueError("Job must have either schedule or interval_seconds")
        if self.priority < 1 or self.priority > 10:
            raise ValueError("Priority must be between 1 and 10")
        if self.max_runtime_seconds < 1:
            raise ValueError("max_runtime_seconds must be at least 1")
        if self.retries < 0:
            raise ValueError("retries cannot be negative")
        if self.retry_delay_seconds < 1:
            raise ValueError("retry_delay_seconds must be at least 1")


@dataclass
class JobExecution:
    """Record of a job execution."""

    job_name: str
    execution_id: str
    started_at: datetime
    completed_at: datetime | None = None
    status: JobStatus = JobStatus.RUNNING
    error: str | None = None
    result: dict[str, Any] | None = None
    duration_seconds: float = 0.0
    retry_count: int = 0

    @classmethod
    def create(cls, job_name: str, execution_id: str) -> "JobExecution":
        """Create a new execution record.

        Args:
            job_name: Name of the job
            execution_id: Unique execution ID

        Returns:
            New JobExecution instance
        """
        return cls(
            job_name=job_name,
            execution_id=execution_id,
            started_at=datetime.now(UTC),
            status=JobStatus.RUNNING,
        )

    def complete(
        self,
        status: JobStatus = JobStatus.COMPLETED,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Mark execution as complete.

        Args:
            status: Final status
            result: Execution result
            error: Error message if failed
        """
        self.completed_at = datetime.now(UTC)
        self.status = status
        self.result = result
        self.error = error
        self.duration_seconds = (self.completed_at - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return {
            "job_name": self.job_name,
            "execution_id": self.execution_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status.value,
            "error": self.error,
            "result": self.result,
            "duration_seconds": self.duration_seconds,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobExecution":
        """Create from dictionary.

        Args:
            data: Dictionary with execution data

        Returns:
            JobExecution instance
        """
        return cls(
            job_name=data["job_name"],
            execution_id=data["execution_id"],
            started_at=datetime.fromisoformat(data["started_at"]),
            completed_at=(
                datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
            ),
            status=JobStatus(data.get("status", "running")),
            error=data.get("error"),
            result=data.get("result"),
            duration_seconds=data.get("duration_seconds", 0.0),
            retry_count=data.get("retry_count", 0),
        )


@dataclass
class JobExecutionHistory:
    """History of job executions."""

    job_name: str
    executions: list[JobExecution] = field(default_factory=list)
    max_history: int = 100  # Keep only recent executions

    def add(self, execution: JobExecution) -> None:
        """Add execution to history.

        Args:
            execution: Execution record to add
        """
        self.executions.append(execution)
        # Keep only recent executions
        if len(self.executions) > self.max_history:
            self.executions = self.executions[-self.max_history :]

    def get_last(self) -> JobExecution | None:
        """Get the most recent execution.

        Returns:
            Most recent JobExecution or None
        """
        return self.executions[-1] if self.executions else None

    def get_by_status(self, status: JobStatus) -> list[JobExecution]:
        """Get executions with specific status.

        Args:
            status: Status to filter by

        Returns:
            List of matching executions
        """
        return [e for e in self.executions if e.status == status]

    def get_failed_count(self, minutes: int = 60) -> int:
        """Get count of failed executions in last N minutes.

        Args:
            minutes: Number of minutes to look back

        Returns:
            Count of failures
        """
        cutoff = datetime.now(UTC).timestamp() - (minutes * 60)
        return sum(
            1
            for e in self.executions
            if e.status == JobStatus.FAILED and e.started_at.timestamp() > cutoff
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return {
            "job_name": self.job_name,
            "executions": [e.to_dict() for e in self.executions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], max_history: int = 100) -> "JobExecutionHistory":
        """Create from dictionary.

        Args:
            data: Dictionary with history data
            max_history: Maximum history size

        Returns:
            JobExecutionHistory instance
        """
        history = cls(job_name=data["job_name"], max_history=max_history)
        history.executions = [JobExecution.from_dict(e) for e in data.get("executions", [])]
        return history

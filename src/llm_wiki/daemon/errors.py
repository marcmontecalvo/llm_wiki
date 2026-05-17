"""Custom exception hierarchy for the daemon subsystem."""

__all__ = [
    "DaemonError",
    "ConfigError",
    "SchedulerError",
    "SchedulerAlreadyRunningError",
    "SchedulerNotRunningError",
    "JobNotFoundError",
    "WorkerPoolError",
    "WorkerPoolAlreadyStartedError",
    "WorkerPoolNotStartedError",
    "ExecutionError",
    "GovernanceError",
    "IngestionError",
]


class DaemonError(Exception):
    """Base exception for all daemon subsystem failures."""


class ConfigError(DaemonError):
    """Raised when configuration is invalid at runtime."""


class SchedulerError(DaemonError):
    """Base for scheduler-specific errors."""


class SchedulerAlreadyRunningError(SchedulerError):
    """Scheduler is started when an operation expects it stopped."""


class SchedulerNotRunningError(SchedulerError):
    """Scheduler is stopped when an operation expects it running."""


class JobNotFoundError(SchedulerError):
    """Job name not found in the scheduler."""


class WorkerPoolError(DaemonError):
    """Base for worker-pool-specific errors."""


class WorkerPoolAlreadyStartedError(WorkerPoolError):
    """Worker pool is started when an operation expects it stopped."""


class WorkerPoolNotStartedError(WorkerPoolError):
    """Worker pool is stopped when an operation expects it running."""


class ExecutionError(DaemonError):
    """Raised when a job execution recording fails."""


class GovernanceError(DaemonError):
    """Raised when governance checks encounter a fatal problem."""


class IngestionError(DaemonError):
    """Raised when an ingestion step fails irrecoverably."""

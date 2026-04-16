"""Job scheduler for daemon tasks."""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from llm_wiki.daemon.execution_store import JobExecutionStore
from llm_wiki.daemon.models import JobDefinition, JobExecution, JobStatus
from llm_wiki.models.config import DaemonConfig

logger = logging.getLogger(__name__)


class JobScheduler:
    """Manages scheduled jobs for wiki maintenance.

    Supports both interval-based and cron-based scheduling.  Wraps every
    registered callable so that execution start/completion is automatically
    recorded via :class:`~llm_wiki.daemon.execution_store.JobExecutionStore`.
    """

    def __init__(
        self,
        config: DaemonConfig,
        execution_store: JobExecutionStore | None = None,
    ) -> None:
        """Initialize scheduler.

        Args:
            config: Daemon configuration
            execution_store: Optional store for persisting execution history.
                             A default store is created if not supplied.
        """
        self.config = config
        self.scheduler = BackgroundScheduler()
        self._jobs: dict[str, str] = {}  # job_name -> APScheduler job_id
        self._definitions: dict[str, JobDefinition] = {}  # job_name -> definition
        self.execution_store = execution_store or JobExecutionStore()

    # ------------------------------------------------------------------
    # Job registration
    # ------------------------------------------------------------------

    def add_job(
        self,
        func: Callable[..., Any],
        job_name: str,
        interval_seconds: float,
        enabled: bool = True,
        **kwargs: Any,
    ) -> None:
        """Add an interval-based job (backwards-compatible API).

        Args:
            func: Function to execute
            job_name: Unique job name
            interval_seconds: Run interval in seconds
            enabled: Whether job is enabled
            **kwargs: Additional arguments passed to func
        """
        if not enabled:
            logger.info("Job '%s' is disabled, skipping registration", job_name)
            return

        if job_name in self._jobs:
            logger.warning("Job '%s' already registered, skipping", job_name)
            return

        try:
            trigger = IntervalTrigger(seconds=interval_seconds)
            wrapped = self._wrap(func, job_name)
            job = self.scheduler.add_job(
                func=wrapped,
                trigger=trigger,
                id=job_name,
                name=job_name,
                kwargs=kwargs,
                misfire_grace_time=60,
                coalesce=True,
                max_instances=1,
            )
            self._jobs[job_name] = job.id
            logger.info(
                "Registered interval job '%s' (%.0fs, enabled=%s)",
                job_name,
                interval_seconds,
                enabled,
            )
        except Exception as exc:
            logger.error("Failed to register job '%s': %s", job_name, exc)
            raise

    def add_job_cron(
        self,
        func: Callable[..., Any],
        job_name: str,
        cron_expression: str,
        enabled: bool = True,
        **kwargs: Any,
    ) -> None:
        """Add a cron-scheduled job.

        Args:
            func: Function to execute
            job_name: Unique job name
            cron_expression: Standard crontab expression, e.g. ``"0 2 * * *"``
            enabled: Whether the job is enabled
            **kwargs: Additional arguments passed to func

        Raises:
            ValueError: If the cron expression is invalid
        """
        if not enabled:
            logger.info("Cron job '%s' is disabled, skipping registration", job_name)
            return

        if job_name in self._jobs:
            logger.warning("Job '%s' already registered, skipping", job_name)
            return

        try:
            trigger = CronTrigger.from_crontab(cron_expression)
        except ValueError as exc:
            raise ValueError(
                f"Invalid cron expression '{cron_expression}' for job '{job_name}': {exc}"
            ) from exc

        try:
            wrapped = self._wrap(func, job_name)
            job = self.scheduler.add_job(
                func=wrapped,
                trigger=trigger,
                id=job_name,
                name=job_name,
                kwargs=kwargs,
                misfire_grace_time=300,
                coalesce=True,
                max_instances=1,
            )
            self._jobs[job_name] = job.id
            logger.info(
                "Registered cron job '%s' (schedule='%s', enabled=%s)",
                job_name,
                cron_expression,
                enabled,
            )
        except Exception as exc:
            logger.error("Failed to register cron job '%s': %s", job_name, exc)
            raise

    def add_job_definition(
        self,
        job_def: JobDefinition,
    ) -> None:
        """Register a job from a :class:`~llm_wiki.daemon.models.JobDefinition`.

        Automatically selects the cron or interval trigger based on which
        field is set on the definition.

        Args:
            job_def: Full job definition (schedule or interval_seconds must be set)

        Raises:
            ValueError: If the definition has neither schedule nor interval_seconds
        """
        if not job_def.enabled:
            logger.info("Job '%s' is disabled, skipping registration", job_def.name)
            return

        if job_def.name in self._jobs:
            logger.warning("Job '%s' already registered, skipping", job_def.name)
            return

        self._definitions[job_def.name] = job_def

        if job_def.schedule:
            self.add_job_cron(
                func=job_def.func,
                job_name=job_def.name,
                cron_expression=job_def.schedule,
                enabled=job_def.enabled,
                **job_def.kwargs,
            )
        elif job_def.interval_seconds is not None:
            self.add_job(
                func=job_def.func,
                job_name=job_def.name,
                interval_seconds=job_def.interval_seconds,
                enabled=job_def.enabled,
                **job_def.kwargs,
            )
        else:
            raise ValueError(
                f"JobDefinition '{job_def.name}' has neither schedule nor interval_seconds"
            )

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------

    def remove_job(self, job_name: str) -> None:
        """Remove a job from the scheduler.

        Args:
            job_name: Job name to remove
        """
        if job_name not in self._jobs:
            logger.warning("Job '%s' not found, cannot remove", job_name)
            return

        try:
            job_id = self._jobs[job_name]
            self.scheduler.remove_job(job_id)
            del self._jobs[job_name]
            self._definitions.pop(job_name, None)
            logger.info("Removed job '%s'", job_name)
        except Exception as exc:
            logger.error("Failed to remove job '%s': %s", job_name, exc)
            raise

    def pause_job(self, job_name: str) -> None:
        """Pause a job without removing it.

        Args:
            job_name: Job name to pause

        Raises:
            KeyError: If job not found
        """
        if job_name not in self._jobs:
            raise KeyError(f"Job '{job_name}' not found")
        self.scheduler.pause_job(self._jobs[job_name])
        logger.info("Paused job '%s'", job_name)

    def resume_job(self, job_name: str) -> None:
        """Resume a paused job.

        Args:
            job_name: Job name to resume

        Raises:
            KeyError: If job not found
        """
        if job_name not in self._jobs:
            raise KeyError(f"Job '{job_name}' not found")
        self.scheduler.resume_job(self._jobs[job_name])
        logger.info("Resumed job '%s'", job_name)

    def run_now(self, job_name: str) -> None:
        """Trigger a job to run immediately (in addition to its schedule).

        Uses APScheduler's ``modify_job`` to set the next run time to now.

        Args:
            job_name: Job name to trigger immediately

        Raises:
            KeyError: If job not found
        """
        if job_name not in self._jobs:
            raise KeyError(f"Job '{job_name}' not found")
        self.scheduler.modify_job(self._jobs[job_name], next_run_time=datetime.now(UTC))
        logger.info("Triggered immediate run of job '%s'", job_name)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the scheduler.

        Raises:
            RuntimeError: If scheduler is already running
        """
        if self.scheduler.running:
            raise RuntimeError("Scheduler is already running")

        try:
            self.scheduler.start()
            logger.info("Scheduler started with %d jobs", len(self._jobs))
        except Exception as exc:
            logger.error("Failed to start scheduler: %s", exc)
            raise

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the scheduler.

        Args:
            wait: If True, wait for running jobs to complete
        """
        if not self.scheduler.running:
            logger.warning("Scheduler is not running")
            return

        try:
            logger.info("Shutting down scheduler (wait=%s)...", wait)
            self.scheduler.shutdown(wait=wait)
            logger.info("Scheduler shutdown complete")
        except Exception as exc:
            logger.error("Error during scheduler shutdown: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        """Return True if the scheduler is running."""
        return bool(self.scheduler.running)

    def get_jobs(self) -> list[str]:
        """Return a copy of registered job names."""
        return list(self._jobs.keys())

    def get_job_info(self, job_name: str) -> dict[str, Any] | None:
        """Return metadata about a registered job.

        Includes scheduling info, last execution status, and priority (when
        a :class:`~llm_wiki.daemon.models.JobDefinition` was used).

        Args:
            job_name: Job name

        Returns:
            Info dict, or None if not found
        """
        if job_name not in self._jobs:
            return None

        job_id = self._jobs[job_name]
        job = self.scheduler.get_job(job_id)

        # APScheduler returns None when the scheduler is stopped; still return
        # whatever we know from the definition and execution store.
        if job is not None:
            next_run: datetime | None = getattr(job, "next_run_time", None)
            if next_run is None and hasattr(job.trigger, "get_next_fire_time"):
                try:
                    next_run = job.trigger.get_next_fire_time(None, datetime.now(UTC))
                except Exception:
                    pass
            info: dict[str, Any] = {
                "id": job.id,
                "name": job.name,
                "next_run_time": next_run,
                "trigger": str(job.trigger),
            }
        else:
            info = {
                "id": job_id,
                "name": job_name,
                "next_run_time": None,
                "trigger": None,
            }

        # Attach definition metadata if available
        defn = self._definitions.get(job_name)
        if defn:
            info["priority"] = defn.priority
            info["enabled"] = defn.enabled
            info["dependencies"] = defn.dependencies
            info["max_runtime_seconds"] = defn.max_runtime_seconds

        # Attach last execution info
        last = self.execution_store.get_last_execution(job_name)
        if last:
            info["last_status"] = last.status.value
            info["last_started_at"] = last.started_at.isoformat()
            info["last_duration_seconds"] = last.duration_seconds
            if last.error:
                info["last_error"] = last.error

        return info

    def get_execution_history(self, job_name: str) -> list[dict[str, Any]]:
        """Return serialized execution history for a job.

        Args:
            job_name: Job name

        Returns:
            List of execution dicts (newest first)
        """
        history = self.execution_store.get_history(job_name)
        return [ex.to_dict() for ex in reversed(history.executions)]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _wrap(self, func: Callable[..., Any], job_name: str) -> Callable[..., Any]:
        """Return a wrapper that records execution start/end.

        The wrapper is a plain function (not a closure over ``self``) so that
        APScheduler can pickle it if needed; instead we capture the store
        reference directly.

        Args:
            func: Original job function
            job_name: Name used for execution records

        Returns:
            Wrapped callable
        """
        store = self.execution_store

        def _tracked(**kwargs: Any) -> Any:
            execution_id = str(uuid.uuid4())
            execution = JobExecution.create(job_name, execution_id)
            store.record_start(execution)

            try:
                result = func(**kwargs)
                result_dict = result if isinstance(result, dict) else {"result": str(result)}
                execution.complete(status=JobStatus.COMPLETED, result=result_dict)
                return result
            except Exception as exc:
                execution.complete(status=JobStatus.FAILED, error=str(exc))
                logger.exception("Job '%s' raised an exception", job_name)
                raise
            finally:
                store.record_complete(execution)

        _tracked.__name__ = f"_tracked_{job_name}"
        return _tracked

"""Job scheduler for daemon tasks."""

import logging
from collections.abc import Callable
from datetime import UTC
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from llm_wiki.models.config import DaemonConfig

logger = logging.getLogger(__name__)


class JobScheduler:
    """Manages scheduled jobs for wiki maintenance."""

    def __init__(self, config: DaemonConfig):
        """Initialize scheduler.

        Args:
            config: Daemon configuration
        """
        self.config = config
        self.scheduler = BackgroundScheduler()
        self._jobs: dict[str, str] = {}  # job_name -> job_id mapping

    def add_job(
        self,
        func: Callable[..., Any],
        job_name: str,
        interval_seconds: float,
        enabled: bool = True,
        **kwargs: Any,
    ) -> None:
        """Add a job to the scheduler.

        Args:
            func: Function to execute
            job_name: Unique job name
            interval_seconds: Run interval in seconds
            enabled: Whether job is enabled
            **kwargs: Additional arguments passed to func
        """
        if not enabled:
            logger.info(f"Job '{job_name}' is disabled, skipping registration")
            return

        if job_name in self._jobs:
            logger.warning(f"Job '{job_name}' already registered, skipping")
            return

        try:
            trigger = IntervalTrigger(seconds=interval_seconds)
            job = self.scheduler.add_job(
                func=func,
                trigger=trigger,
                id=job_name,
                name=job_name,
                kwargs=kwargs,
                misfire_grace_time=60,  # Allow 60s grace for missed executions
                coalesce=True,  # Combine multiple missed executions into one
                max_instances=1,  # Prevent concurrent executions
            )

            self._jobs[job_name] = job.id
            logger.info(
                f"Registered job '{job_name}' with interval {interval_seconds}s (enabled={enabled})"
            )

        except Exception as e:
            logger.error(f"Failed to register job '{job_name}': {e}")
            raise

    def remove_job(self, job_name: str) -> None:
        """Remove a job from the scheduler.

        Args:
            job_name: Job name to remove
        """
        if job_name not in self._jobs:
            logger.warning(f"Job '{job_name}' not found, cannot remove")
            return

        try:
            job_id = self._jobs[job_name]
            self.scheduler.remove_job(job_id)
            del self._jobs[job_name]
            logger.info(f"Removed job '{job_name}'")

        except Exception as e:
            logger.error(f"Failed to remove job '{job_name}': {e}")
            raise

    def start(self) -> None:
        """Start the scheduler.

        Raises:
            RuntimeError: If scheduler is already running
        """
        if self.scheduler.running:
            raise RuntimeError("Scheduler is already running")

        try:
            self.scheduler.start()
            logger.info(f"Scheduler started with {len(self._jobs)} jobs")

        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
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
            logger.info(f"Shutting down scheduler (wait={wait})...")
            self.scheduler.shutdown(wait=wait)
            logger.info("Scheduler shutdown complete")

        except Exception as e:
            logger.error(f"Error during scheduler shutdown: {e}")
            raise

    def is_running(self) -> bool:
        """Check if scheduler is running.

        Returns:
            True if scheduler is running
        """
        return bool(self.scheduler.running)

    def get_jobs(self) -> list[str]:
        """Get list of registered job names.

        Returns:
            List of job names
        """
        return list(self._jobs.keys())

    def get_job_info(self, job_name: str) -> dict[str, Any] | None:
        """Get information about a job.

        Args:
            job_name: Job name

        Returns:
            Job info dict or None if not found
        """
        if job_name not in self._jobs:
            return None

        job_id = self._jobs[job_name]
        job = self.scheduler.get_job(job_id)

        if not job:
            return None

        # Get next run time from trigger if available
        next_run = None
        if hasattr(job, "next_run_time"):
            next_run = job.next_run_time
        elif hasattr(job.trigger, "get_next_fire_time"):
            # Get from trigger if job doesn't have it
            try:
                from datetime import datetime

                next_run = job.trigger.get_next_fire_time(None, datetime.now(UTC))
            except Exception:
                pass

        return {
            "id": job.id,
            "name": job.name,
            "next_run_time": next_run,
            "trigger": str(job.trigger),
        }

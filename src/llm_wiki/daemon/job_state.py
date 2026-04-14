"""Job execution state persistence and management."""

import json
import logging
from pathlib import Path
from typing import Any

from llm_wiki.daemon.models import JobExecution, JobExecutionHistory, JobStatus

logger = logging.getLogger(__name__)


class JobStateManager:
    """Manages job execution state and history persistence."""

    def __init__(self, state_dir: Path | str | None = None):
        """Initialize job state manager.

        Args:
            state_dir: Directory for storing job state (default: wiki_system/state/job_executions)
        """
        if state_dir is None:
            state_dir = Path("wiki_system") / "state" / "job_executions"
        else:
            state_dir = Path(state_dir)

        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self._history_cache: dict[str, JobExecutionHistory] = {}

    def save_execution(self, execution: JobExecution) -> None:
        """Save a job execution record.

        Args:
            execution: JobExecution to save
        """
        # Add to in-memory history
        if execution.job_name not in self._history_cache:
            self._history_cache[execution.job_name] = JobExecutionHistory(
                job_name=execution.job_name
            )
        self._history_cache[execution.job_name].add(execution)

        # Save to file
        self._save_history_to_file(execution.job_name)

    def load_history(self, job_name: str) -> JobExecutionHistory:
        """Load execution history for a job.

        Args:
            job_name: Name of job

        Returns:
            JobExecutionHistory for the job
        """
        # Check cache first
        if job_name in self._history_cache:
            return self._history_cache[job_name]

        # Try to load from file
        history_file = self.state_dir / f"{job_name}_history.json"
        if history_file.exists():
            try:
                with open(history_file, encoding="utf-8") as f:
                    data = json.load(f)
                history = JobExecutionHistory.from_dict(data)
                self._history_cache[job_name] = history
                return history
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load history for {job_name}: {e}")

        # Return empty history
        history = JobExecutionHistory(job_name=job_name)
        self._history_cache[job_name] = history
        return history

    def get_last_execution(self, job_name: str) -> JobExecution | None:
        """Get the last execution of a job.

        Args:
            job_name: Name of job

        Returns:
            Last JobExecution or None if never run
        """
        history = self.load_history(job_name)
        return history.get_last()

    def get_failed_count(self, job_name: str, minutes: int = 60) -> int:
        """Get count of failed executions in last N minutes.

        Args:
            job_name: Name of job
            minutes: Number of minutes to look back

        Returns:
            Count of failures
        """
        history = self.load_history(job_name)
        return history.get_failed_count(minutes)

    def get_execution_by_id(self, job_name: str, execution_id: str) -> JobExecution | None:
        """Get a specific execution by ID.

        Args:
            job_name: Name of job
            execution_id: Execution ID

        Returns:
            JobExecution or None if not found
        """
        history = self.load_history(job_name)
        for execution in history.executions:
            if execution.execution_id == execution_id:
                return execution
        return None

    def get_all_histories(self) -> dict[str, JobExecutionHistory]:
        """Get all execution histories.

        Returns:
            Dictionary of job_name -> JobExecutionHistory
        """
        # Load all from files
        for history_file in self.state_dir.glob("*_history.json"):
            job_name = history_file.stem.replace("_history", "")
            if job_name not in self._history_cache:
                self.load_history(job_name)

        return dict(self._history_cache)

    def clear_history(self, job_name: str) -> None:
        """Clear execution history for a job.

        Args:
            job_name: Name of job
        """
        # Clear from cache
        if job_name in self._history_cache:
            del self._history_cache[job_name]

        # Clear from file
        history_file = self.state_dir / f"{job_name}_history.json"
        if history_file.exists():
            try:
                history_file.unlink()
                logger.info(f"Cleared history for job: {job_name}")
            except OSError as e:
                logger.error(f"Failed to clear history for {job_name}: {e}")

    def _save_history_to_file(self, job_name: str) -> None:
        """Save execution history to file (internal).

        Args:
            job_name: Name of job
        """
        history = self._history_cache.get(job_name)
        if not history:
            return

        history_file = self.state_dir / f"{job_name}_history.json"

        try:
            # Write atomically
            temp_file = history_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(history.to_dict(), f, indent=2, sort_keys=True)

            # Atomic rename
            temp_file.replace(history_file)
            logger.debug(f"Saved execution history for {job_name}")

        except OSError as e:
            logger.error(f"Failed to save history for {job_name}: {e}")

    def get_stats(self, job_name: str) -> dict[str, Any]:
        """Get statistics for a job.

        Args:
            job_name: Name of job

        Returns:
            Dictionary with execution statistics
        """
        history = self.load_history(job_name)

        if not history.executions:
            return {
                "job_name": job_name,
                "total_executions": 0,
                "total_successes": 0,
                "total_failures": 0,
                "total_timeouts": 0,
                "success_rate": 0.0,
                "average_duration_seconds": 0.0,
                "last_execution": None,
                "last_status": None,
            }

        total = len(history.executions)
        successes = len(history.get_by_status(JobStatus.COMPLETED))
        failures = len(history.get_by_status(JobStatus.FAILED))
        timeouts = len(history.get_by_status(JobStatus.TIMEOUT))

        avg_duration = (
            sum(e.duration_seconds for e in history.executions) / total if total > 0 else 0.0
        )

        last = history.get_last()

        return {
            "job_name": job_name,
            "total_executions": total,
            "total_successes": successes,
            "total_failures": failures,
            "total_timeouts": timeouts,
            "success_rate": successes / total if total > 0 else 0.0,
            "average_duration_seconds": avg_duration,
            "last_execution": last.started_at.isoformat() if last else None,
            "last_status": last.status.value if last else None,
        }

    def export_history(self, job_name: str) -> dict[str, Any]:
        """Export execution history for a job.

        Args:
            job_name: Name of job

        Returns:
            Dictionary with execution history
        """
        history = self.load_history(job_name)
        return history.to_dict()

"""Job execution history persistence for the daemon scheduler."""

import json
import logging
import threading
from pathlib import Path
from typing import Any

from llm_wiki.daemon.models import JobExecution, JobExecutionHistory

logger = logging.getLogger(__name__)

_DEFAULT_STATE_DIR = Path("wiki_system") / "state" / "job_executions"


class JobExecutionStore:
    """Persists job execution history to disk.

    Each job has its own JSON file under ``state_dir/<job_name>.json``.
    Keeps up to ``max_history`` executions per job (oldest are pruned).
    """

    def __init__(
        self,
        state_dir: Path | None = None,
        max_history: int = 100,
    ) -> None:
        """Initialize the execution store.

        Args:
            state_dir: Directory for execution files
                       (default: wiki_system/state/job_executions/)
            max_history: Maximum executions to keep per job
        """
        self.state_dir = Path(state_dir) if state_dir else _DEFAULT_STATE_DIR
        self.max_history = max_history
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_start(self, execution: JobExecution) -> None:
        """Persist the start of a job execution.

        Args:
            execution: Execution record in RUNNING state
        """
        with self._lock:
            history = self._load(execution.job_name)
            history.add(execution)
            self._save(history)

    def record_complete(self, execution: JobExecution) -> None:
        """Update the stored record once a job finishes.

        Args:
            execution: Execution record in a terminal state
        """
        with self._lock:
            history = self._load(execution.job_name)

            # Replace the matching in-progress record if it exists
            updated = False
            for i, ex in enumerate(history.executions):
                if ex.execution_id == execution.execution_id:
                    history.executions[i] = execution
                    updated = True
                    break

            if not updated:
                history.add(execution)

            self._save(history)

    def get_history(self, job_name: str) -> JobExecutionHistory:
        """Load execution history for a job.

        Args:
            job_name: Name of the job

        Returns:
            JobExecutionHistory (empty if no history exists)
        """
        return self._load(job_name)

    def get_last_execution(self, job_name: str) -> JobExecution | None:
        """Return the most recent execution for a job.

        Args:
            job_name: Name of the job

        Returns:
            Most recent JobExecution, or None
        """
        return self._load(job_name).get_last()

    def list_jobs(self) -> list[str]:
        """Return the names of all jobs with stored history.

        Returns:
            Sorted list of job names
        """
        return sorted(p.stem for p in self.state_dir.glob("*.json"))

    def clear_history(self, job_name: str) -> bool:
        """Delete stored history for a job.

        Args:
            job_name: Name of the job

        Returns:
            True if history existed and was deleted, False otherwise
        """
        path = self._path(job_name)
        if path.exists():
            path.unlink()
            return True
        return False

    def export_stats(self) -> dict[str, Any]:
        """Export a summary of execution statistics across all jobs.

        Returns:
            Dict mapping job_name → stats dict
        """
        stats: dict[str, Any] = {}
        for job_name in self.list_jobs():
            history = self._load(job_name)
            last = history.get_last()
            stats[job_name] = {
                "total_executions": len(history.executions),
                "failures_last_hour": history.get_failed_count(minutes=60),
                "last_status": last.status.value if last else None,
                "last_started_at": last.started_at.isoformat() if last else None,
                "last_duration_seconds": last.duration_seconds if last else None,
            }
        return stats

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _path(self, job_name: str) -> Path:
        return self.state_dir / f"{job_name}.json"

    def _load(self, job_name: str) -> JobExecutionHistory:
        path = self._path(job_name)
        if not path.exists():
            return JobExecutionHistory(job_name=job_name, max_history=self.max_history)

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return JobExecutionHistory.from_dict(data, max_history=self.max_history)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("Corrupted execution history for %s (%s); resetting", job_name, exc)
            return JobExecutionHistory(job_name=job_name, max_history=self.max_history)

    def _save(self, history: JobExecutionHistory) -> None:
        path = self._path(history.job_name)
        try:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(history.to_dict(), indent=2, default=str), encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            logger.error("Failed to save execution history for %s: %s", history.job_name, exc)

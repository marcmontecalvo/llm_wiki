"""Daemon state persistence."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DaemonState:
    """Manages daemon state persistence."""

    def __init__(self, state_file: Path | str | None = None):
        """Initialize state manager.

        Args:
            state_file: Path to state file (default: wiki_system/state/daemon_state.json)
        """
        if state_file is None:
            state_dir = Path("wiki_system") / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            state_file = state_dir / "daemon_state.json"
        else:
            state_file = Path(state_file)
            state_file.parent.mkdir(parents=True, exist_ok=True)

        self.state_file = state_file
        self.state: dict[str, Any] = {
            "version": 1,
            "last_updated": None,
            "job_last_run": {},  # job_name -> timestamp
            "inbox_files": {},  # filename -> status
        }

    def load(self) -> None:
        """Load state from file.

        If file doesn't exist or is corrupted, starts with empty state.
        """
        if not self.state_file.exists():
            logger.info("No state file found, starting with empty state")
            return

        try:
            with open(self.state_file, encoding="utf-8") as f:
                loaded_state = json.load(f)

            # Validate version
            if loaded_state.get("version") != 1:
                logger.warning(
                    f"State file version mismatch (expected 1, got {loaded_state.get('version')}), "
                    "resetting state"
                )
                return

            # Check for stale state (older than 30 days)
            last_updated = loaded_state.get("last_updated")
            if last_updated:
                try:
                    last_updated_dt = datetime.fromisoformat(last_updated)
                    now = datetime.now(UTC)
                    age_days = (now - last_updated_dt).days

                    if age_days > 30:
                        logger.warning(
                            f"State file is {age_days} days old (stale), resetting state"
                        )
                        return
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid last_updated timestamp: {e}")
                    return

            # Load state
            self.state = loaded_state
            logger.info(f"Loaded state from {self.state_file}")

        except json.JSONDecodeError as e:
            logger.error(f"Corrupted state file: {e}, starting with empty state")
        except OSError as e:
            logger.error(f"Failed to load state: {e}, starting with empty state")

    def save(self) -> None:
        """Save state to file."""
        try:
            # Update timestamp
            self.state["last_updated"] = datetime.now(UTC).isoformat()

            # Write atomically (write to temp file, then rename)
            temp_file = self.state_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, sort_keys=True)

            # Atomic rename
            temp_file.replace(self.state_file)

            logger.debug(f"Saved state to {self.state_file}")

        except OSError as e:
            logger.error(f"Failed to save state: {e}")

    def set_job_last_run(self, job_name: str, timestamp: datetime | None = None) -> None:
        """Record last run time for a job.

        Args:
            job_name: Name of the job
            timestamp: Run timestamp (default: now)
        """
        if timestamp is None:
            timestamp = datetime.now(UTC)

        self.state["job_last_run"][job_name] = timestamp.isoformat()

    def get_job_last_run(self, job_name: str) -> datetime | None:
        """Get last run time for a job.

        Args:
            job_name: Name of the job

        Returns:
            Last run timestamp or None if never run
        """
        timestamp_str = self.state["job_last_run"].get(job_name)
        if timestamp_str:
            try:
                return datetime.fromisoformat(timestamp_str)
            except (ValueError, TypeError):
                logger.warning(f"Invalid timestamp for job {job_name}: {timestamp_str}")
                return None
        return None

    def set_inbox_file_status(self, filename: str, status: str) -> None:
        """Set processing status for an inbox file.

        Args:
            filename: Name of the file
            status: Processing status (e.g., 'pending', 'processing', 'completed', 'failed')
        """
        self.state["inbox_files"][filename] = {
            "status": status,
            "updated_at": datetime.now(UTC).isoformat(),
        }

    def get_inbox_file_status(self, filename: str) -> str | None:
        """Get processing status for an inbox file.

        Args:
            filename: Name of the file

        Returns:
            Processing status or None if not tracked
        """
        file_state = self.state["inbox_files"].get(filename)
        if file_state:
            status = file_state.get("status")
            return str(status) if status is not None else None
        return None

    def get_all_inbox_files(self) -> dict[str, dict[str, str]]:
        """Get all inbox file statuses.

        Returns:
            Dictionary of filename -> file state
        """
        return dict(self.state["inbox_files"])

    def clear_inbox_file(self, filename: str) -> None:
        """Remove an inbox file from state.

        Args:
            filename: Name of the file to remove
        """
        if filename in self.state["inbox_files"]:
            del self.state["inbox_files"][filename]

    def clear_old_inbox_files(self, days: int = 7) -> int:
        """Clear inbox files older than specified days.

        Args:
            days: Number of days (default: 7)

        Returns:
            Number of files cleared
        """
        now = datetime.now(UTC)
        to_remove = []

        for filename, file_state in self.state["inbox_files"].items():
            updated_at = file_state.get("updated_at")
            if updated_at:
                try:
                    updated_dt = datetime.fromisoformat(updated_at)
                    age_days = (now - updated_dt).days
                    if age_days > days:
                        to_remove.append(filename)
                except (ValueError, TypeError):
                    # Invalid timestamp, remove it
                    to_remove.append(filename)

        for filename in to_remove:
            del self.state["inbox_files"][filename]

        if to_remove:
            logger.info(f"Cleared {len(to_remove)} old inbox file entries")

        return len(to_remove)

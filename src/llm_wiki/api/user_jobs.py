"""Persistent in-memory store for user-driven ingest job state.

Jobs are persisted to ``state/user_jobs.json`` using an atomic write pattern
so that uvicorn restarts do not lose pending/running ingest jobs.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from llm_wiki.api.models import IngestStatusResponse


class UserJobStore:
    """Persists ingest job status to disk."""

    def __init__(self, state_dir: Path) -> None:
        self._path = state_dir / "user_jobs.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("{}", encoding="utf-8")
        self._lock = threading.Lock()

    def save(self, job_id: str, status: IngestStatusResponse) -> None:
        """Persist or update a job status.

        Uses atomic write (write to temp file then os.replace).
        Thread-safe via internal lock.
        """
        with self._lock:
            data = self._load_raw()
            data[job_id] = status.model_dump()
            self._write_atomic(data)

    def get(self, job_id: str) -> IngestStatusResponse | None:
        """Return the status for a job, or None if not found."""
        data = self._load_raw()
        raw = data.get(job_id)
        if raw is None:
            return None
        return IngestStatusResponse(**raw)

    def list_all(self) -> list[IngestStatusResponse]:
        """Return all stored jobs in insertion order."""
        return [IngestStatusResponse(**v) for v in self._load_raw().values()]

    # -- internals ----------------------------------------------------------

    def _load_raw(self) -> dict[str, Any]:
        try:
            result: dict[str, Any] = json.loads(self._path.read_text(encoding="utf-8"))
            return result
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _write_atomic(self, data: dict) -> None:
        with tempfile.NamedTemporaryFile(
            "w", dir=self._path.parent, delete=False, suffix=".tmp", encoding="utf-8"
        ) as f:
            json.dump(data, f, indent=2, default=str)
            tmp = f.name
        os.replace(tmp, self._path)

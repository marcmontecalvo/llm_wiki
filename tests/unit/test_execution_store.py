"""Tests for JobExecutionStore."""

from pathlib import Path

import pytest

from llm_wiki.daemon.execution_store import JobExecutionStore
from llm_wiki.daemon.models import JobExecution, JobExecutionHistory, JobStatus


@pytest.fixture
def store(tmp_path: Path) -> JobExecutionStore:
    return JobExecutionStore(state_dir=tmp_path / "executions")


def _make_execution(job_name: str, status: JobStatus = JobStatus.COMPLETED) -> JobExecution:
    ex = JobExecution.create(job_name, "exec-001")
    ex.complete(status=status, result={"ok": True})
    return ex


class TestJobExecutionStore:
    def test_record_and_retrieve(self, store: JobExecutionStore):
        ex = _make_execution("governance_check")
        store.record_start(ex)
        store.record_complete(ex)

        last = store.get_last_execution("governance_check")
        assert last is not None
        assert last.execution_id == ex.execution_id
        assert last.status == JobStatus.COMPLETED

    def test_no_history_returns_none(self, store: JobExecutionStore):
        assert store.get_last_execution("nonexistent") is None

    def test_get_history_empty(self, store: JobExecutionStore):
        history = store.get_history("no_such_job")
        assert isinstance(history, JobExecutionHistory)
        assert history.executions == []

    def test_list_jobs_empty(self, store: JobExecutionStore):
        assert store.list_jobs() == []

    def test_list_jobs_after_records(self, store: JobExecutionStore):
        store.record_complete(_make_execution("job_a"))
        store.record_complete(_make_execution("job_b"))
        assert sorted(store.list_jobs()) == ["job_a", "job_b"]

    def test_clear_history(self, store: JobExecutionStore):
        store.record_complete(_make_execution("job_a"))
        assert store.clear_history("job_a") is True
        assert store.get_last_execution("job_a") is None

    def test_clear_nonexistent_returns_false(self, store: JobExecutionStore):
        assert store.clear_history("ghost") is False

    def test_record_complete_updates_existing(self, store: JobExecutionStore):
        ex = JobExecution.create("my_job", "exec-xyz")
        store.record_start(ex)  # stored as RUNNING

        ex.complete(status=JobStatus.COMPLETED, result={"done": True})
        store.record_complete(ex)

        history = store.get_history("my_job")
        # Only one record — the start was updated in place
        assert len(history.executions) == 1
        assert history.executions[0].status == JobStatus.COMPLETED

    def test_multiple_executions_ordered(self, store: JobExecutionStore):
        for i in range(5):
            ex = JobExecution.create("batch_job", f"exec-{i:03d}")
            ex.complete(status=JobStatus.COMPLETED)
            store.record_complete(ex)

        history = store.get_history("batch_job")
        assert len(history.executions) == 5

    def test_max_history_pruned(self, store: JobExecutionStore):
        small_store = JobExecutionStore(state_dir=store.state_dir, max_history=3)
        for i in range(5):
            ex = JobExecution.create("pruned_job", f"exec-{i:03d}")
            ex.complete(status=JobStatus.COMPLETED)
            small_store.record_complete(ex)

        history = small_store.get_history("pruned_job")
        assert len(history.executions) <= 3

    def test_export_stats_single_job(self, store: JobExecutionStore):
        ex = _make_execution("export_job", JobStatus.COMPLETED)
        store.record_complete(ex)

        stats = store.export_stats()
        assert "export_job" in stats
        assert stats["export_job"]["total_executions"] == 1
        assert stats["export_job"]["last_status"] == "completed"

    def test_export_stats_counts_failures(self, store: JobExecutionStore):
        for i in range(3):
            ex = JobExecution.create("flaky_job", f"exec-fail-{i}")
            ex.complete(status=JobStatus.FAILED, error="boom")
            store.record_complete(ex)

        stats = store.export_stats()
        assert stats["flaky_job"]["failures_last_hour"] == 3

    def test_corrupted_file_returns_empty(self, store: JobExecutionStore, tmp_path: Path):
        bad_path = store.state_dir / "corrupt_job.json"
        bad_path.parent.mkdir(parents=True, exist_ok=True)
        bad_path.write_text("not valid json", encoding="utf-8")

        history = store.get_history("corrupt_job")
        assert history.executions == []

    def test_atomic_write(self, store: JobExecutionStore):
        """Temp file must not persist after successful save."""
        ex = _make_execution("atomic_job")
        store.record_complete(ex)

        tmp_files = list(store.state_dir.glob("*.tmp"))
        assert tmp_files == []

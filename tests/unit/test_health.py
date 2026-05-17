"""Tests for Phase 0.4: Health check endpoint."""

from pathlib import Path

import pytest

from llm_wiki.daemon.execution_store import JobExecutionStore
from llm_wiki.daemon.scheduler import JobScheduler
from llm_wiki.daemon.workers import WorkerPool
from llm_wiki.models.config import DaemonConfig


@pytest.fixture
def daemon_config() -> DaemonConfig:
    return DaemonConfig()


@pytest.fixture
def scheduler(daemon_config: DaemonConfig) -> JobScheduler:
    return JobScheduler(daemon_config)


@pytest.fixture
def pool(daemon_config: DaemonConfig) -> WorkerPool:
    return WorkerPool(daemon_config)


class TestWorkerPoolHealth:
    """Tests for WorkerPool.health()."""

    def test_health_before_start(self, pool: WorkerPool):
        info = pool.health()
        assert info["running"] is False
        assert info["active_jobs"] == 0
        assert info["pending_jobs"] == 0
        assert info["max_workers"] == pool.max_workers

    def test_health_after_start(self, daemon_config: DaemonConfig):
        pool = WorkerPool(daemon_config)
        pool.start()
        try:
            info = pool.health()
            assert info["running"] is True
            assert info["active_jobs"] >= 0
            assert info["pending_jobs"] >= 0
        finally:
            pool.shutdown()


class TestSchedulerHealth:
    """Tests for JobScheduler.health()."""

    def test_health_before_start(self, scheduler: JobScheduler):
        info = scheduler.health()
        assert "running" in info
        assert "job_count" in info
        assert info["job_count"] == 0
        assert info["recent_errors"] == 0

    def test_health_with_jobs(self, daemon_config: DaemonConfig):
        sched = JobScheduler(daemon_config)
        sched.add_job(lambda: None, "test_job", interval_seconds=60)
        info = sched.health()
        assert info["job_count"] == 1
        assert "test_job" in info["jobs"]

    def test_health_after_start(self, daemon_config: DaemonConfig):
        sched = JobScheduler(daemon_config)
        sched.start()
        try:
            info = sched.health()
            assert info["running"] is True
            assert info["uptime_seconds"] is not None
            assert info["uptime_seconds"] >= 0
        finally:
            sched.shutdown()


class TestExecutionStoreExtras:
    """Tests for new execution store methods."""

    def test_job_names_empty(self, daemon_config: DaemonConfig, temp_dir: Path):
        store = JobExecutionStore(state_dir=temp_dir / "store")
        assert store.job_names() == []

    def test_job_names_after_recording(self, daemon_config: DaemonConfig, temp_dir: Path):
        store = JobExecutionStore(state_dir=temp_dir / "store")
        import uuid

        from llm_wiki.daemon.models import JobExecution

        exec_ = JobExecution.create("export", str(uuid.uuid4()))
        store.record_complete(exec_)
        names = store.job_names()
        assert "export" in names

    def test_get_all_history_empty(self, daemon_config: DaemonConfig, temp_dir: Path):
        store = JobExecutionStore(state_dir=temp_dir / "store")
        assert store.get_all_history() == []

    def test_get_all_history_with_data(self, daemon_config: DaemonConfig, temp_dir: Path):
        store = JobExecutionStore(state_dir=temp_dir / "store")
        from llm_wiki.daemon.models import JobExecution

        exec1 = JobExecution.create("export", "exec-1")
        exec2 = JobExecution.create("import", "exec-2")
        store.record_complete(exec1)
        store.record_complete(exec2)
        history = store.get_all_history()
        names = {h.job_name for h in history}
        assert names == {"export", "import"}

    def test_get_all_history_omits_empty_jobs(self, daemon_config: DaemonConfig, temp_dir: Path):
        """job_names() only returns jobs with actual history files."""
        store = JobExecutionStore(state_dir=temp_dir / "store")
        from llm_wiki.daemon.models import JobExecution

        exec1 = JobExecution.create("export", "exec-1")
        store.record_complete(exec1)
        # "inbox" has never been recorded — should not appear
        assert "inbox" not in store.job_names()


class TestHealthCommand:
    """Tests for the CLI health command (integration)."""

    def _write_minimal(self, config_dir: Path) -> None:
        (config_dir / "domains.yaml").write_text(
            "domains:\n  - id: general\n    title: General\n    description: General domain\n"
        )
        (config_dir / "daemon.yaml").write_text("daemon: {}\n")
        (config_dir / "routing.yaml").write_text("routing: {}\n")
        (config_dir / "models.yaml").write_text("models: {}\n")

    def test_health_command_valid_config(self, temp_dir: Path, capfd):
        from llm_wiki.cli import main

        config_dir = temp_dir / "wiki_base" / "config"
        config_dir.mkdir(parents=True)
        self._write_minimal(config_dir)

        main(
            ["health", "--wiki-base", str(temp_dir / "wiki_base")],
            standalone_mode=False,
        )
        captured = capfd.readouterr()
        assert "config: OK" in captured.out
        assert "overall: GREEN" in captured.out

    def test_health_command_invalid_config(self, temp_dir: Path, capfd):
        from llm_wiki.cli import main

        config_dir = temp_dir / "wiki_base" / "config"
        config_dir.mkdir(parents=True)
        # Intentionally wrong fallback domain
        (config_dir / "domains.yaml").write_text(
            "domains:\n  - id: general\n    title: General\n    description: General domain\n"
        )
        (config_dir / "daemon.yaml").write_text("daemon: {}\n")
        (config_dir / "routing.yaml").write_text("routing:\n  fallback_domain: missing\n")
        (config_dir / "models.yaml").write_text("models: {}\n")

        with pytest.raises(SystemExit):
            main(["health", "--wiki-base", str(temp_dir / "wiki_base")], standalone_mode=False)
        captured = capfd.readouterr()
        assert "ERROR" in captured.out or "missing" in captured.out

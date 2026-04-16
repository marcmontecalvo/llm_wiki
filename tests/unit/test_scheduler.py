"""Tests for job scheduler."""

import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from llm_wiki.daemon.execution_store import JobExecutionStore
from llm_wiki.daemon.models import JobDefinition, JobPriority, JobStatus
from llm_wiki.daemon.scheduler import JobScheduler
from llm_wiki.models.config import DaemonConfig


@pytest.fixture
def daemon_config() -> DaemonConfig:
    """Create daemon config for testing."""
    return DaemonConfig(
        max_parallel_jobs=2,
        inbox_poll_seconds=60,
        log_level="INFO",
    )


@pytest.fixture
def store(tmp_path: Path) -> JobExecutionStore:
    return JobExecutionStore(state_dir=tmp_path / "executions")


@pytest.fixture
def scheduler(daemon_config: DaemonConfig, store: JobExecutionStore) -> JobScheduler:
    return JobScheduler(daemon_config, execution_store=store)


class TestJobScheduler:
    """Tests for JobScheduler class."""

    def test_init(self, scheduler: JobScheduler, daemon_config: DaemonConfig):
        """Test scheduler initialization."""
        assert scheduler.config == daemon_config
        assert not scheduler.is_running()
        assert scheduler.get_jobs() == []

    def test_add_job(self, scheduler: JobScheduler):
        """Test adding a job."""
        mock_func = Mock()

        scheduler.add_job(
            func=mock_func,
            job_name="test_job",
            interval_seconds=10,
        )

        assert "test_job" in scheduler.get_jobs()
        assert len(scheduler.get_jobs()) == 1

    def test_add_job_with_kwargs(self, scheduler: JobScheduler):
        """Test adding job with keyword arguments."""
        mock_func = Mock()

        scheduler.add_job(
            func=mock_func,
            job_name="test_job",
            interval_seconds=10,
            param1="value1",
            param2=42,
        )

        assert "test_job" in scheduler.get_jobs()

    def test_add_disabled_job_skips_registration(self, scheduler: JobScheduler):
        """Test disabled job is not registered."""
        mock_func = Mock()

        scheduler.add_job(
            func=mock_func,
            job_name="disabled_job",
            interval_seconds=10,
            enabled=False,
        )

        assert "disabled_job" not in scheduler.get_jobs()
        assert len(scheduler.get_jobs()) == 0

    def test_add_duplicate_job_warns(self, scheduler: JobScheduler, caplog):
        """Test adding duplicate job logs warning."""
        mock_func = Mock()

        scheduler.add_job(
            func=mock_func,
            job_name="duplicate",
            interval_seconds=10,
        )

        scheduler.add_job(
            func=mock_func,
            job_name="duplicate",
            interval_seconds=20,
        )

        assert "already registered" in caplog.text
        assert len(scheduler.get_jobs()) == 1

    def test_remove_job(self, scheduler: JobScheduler):
        """Test removing a job."""
        mock_func = Mock()

        scheduler.add_job(
            func=mock_func,
            job_name="removable",
            interval_seconds=10,
        )

        assert "removable" in scheduler.get_jobs()

        scheduler.remove_job("removable")

        assert "removable" not in scheduler.get_jobs()

    def test_remove_nonexistent_job_warns(self, scheduler: JobScheduler, caplog):
        """Test removing nonexistent job logs warning."""
        scheduler.remove_job("nonexistent")

        assert "not found" in caplog.text

    def test_start(self, scheduler: JobScheduler):
        """Test starting the scheduler."""
        assert not scheduler.is_running()

        scheduler.start()

        assert scheduler.is_running()

        # Cleanup
        scheduler.shutdown(wait=False)

    def test_start_already_running_raises(self, scheduler: JobScheduler):
        """Test starting already running scheduler raises error."""
        scheduler.start()

        with pytest.raises(RuntimeError, match="already running"):
            scheduler.start()

        # Cleanup
        scheduler.shutdown(wait=False)

    def test_shutdown(self, scheduler: JobScheduler):
        """Test shutting down the scheduler."""
        scheduler.start()
        assert scheduler.is_running()

        scheduler.shutdown(wait=False)

        assert not scheduler.is_running()

    def test_shutdown_with_wait(self, scheduler: JobScheduler):
        """Test shutdown waits for jobs to complete."""
        mock_func = Mock()

        scheduler.add_job(
            func=mock_func,
            job_name="test_job",
            interval_seconds=1,
        )

        scheduler.start()
        time.sleep(0.1)  # Let job potentially start

        scheduler.shutdown(wait=True)

        assert not scheduler.is_running()

    def test_shutdown_not_running_warns(self, scheduler: JobScheduler, caplog):
        """Test shutting down non-running scheduler warns."""
        assert not scheduler.is_running()

        scheduler.shutdown()

        assert "not running" in caplog.text

    def test_get_job_info(self, scheduler: JobScheduler):
        """Test getting job information."""
        mock_func = Mock()

        scheduler.add_job(
            func=mock_func,
            job_name="info_job",
            interval_seconds=30,
        )

        info = scheduler.get_job_info("info_job")

        assert info is not None
        assert info["id"] == "info_job"
        assert info["name"] == "info_job"
        assert "trigger" in info
        assert "next_run_time" in info

    def test_get_job_info_nonexistent(self, scheduler: JobScheduler):
        """Test getting info for nonexistent job returns None."""
        info = scheduler.get_job_info("nonexistent")

        assert info is None

    def test_job_execution(self, scheduler: JobScheduler):
        """Test job actually executes."""
        mock_func = Mock()

        scheduler.add_job(
            func=mock_func,
            job_name="exec_job",
            interval_seconds=0.1,  # Very short interval for testing
        )

        scheduler.start()

        # Wait for job to execute at least once
        time.sleep(0.3)

        scheduler.shutdown(wait=True)

        # Job should have been called at least once
        assert mock_func.call_count >= 1

    def test_job_execution_with_kwargs(self, scheduler: JobScheduler):
        """Test job executes with keyword arguments."""
        mock_func = Mock()

        scheduler.add_job(
            func=mock_func,
            job_name="kwargs_job",
            interval_seconds=0.1,
            test_arg="test_value",
        )

        scheduler.start()
        time.sleep(0.3)
        scheduler.shutdown(wait=True)

        # Verify function was called with correct kwargs
        assert mock_func.call_count >= 1
        mock_func.assert_called_with(test_arg="test_value")

    def test_job_error_doesnt_crash_scheduler(self, scheduler: JobScheduler, caplog):
        """Test job errors don't crash the scheduler."""

        def failing_job():
            raise ValueError("Job failed!")

        scheduler.add_job(
            func=failing_job,
            job_name="failing_job",
            interval_seconds=0.1,
        )

        scheduler.start()
        time.sleep(0.3)

        # Scheduler should still be running despite job failures
        assert scheduler.is_running()

        scheduler.shutdown(wait=False)

    def test_multiple_jobs(self, scheduler: JobScheduler):
        """Test scheduler handles multiple jobs."""
        mock_func1 = Mock()
        mock_func2 = Mock()
        mock_func3 = Mock()

        scheduler.add_job(func=mock_func1, job_name="job1", interval_seconds=0.1)
        scheduler.add_job(func=mock_func2, job_name="job2", interval_seconds=0.1)
        scheduler.add_job(func=mock_func3, job_name="job3", interval_seconds=0.1)

        assert len(scheduler.get_jobs()) == 3

        scheduler.start()
        time.sleep(0.3)
        scheduler.shutdown(wait=True)

        # All jobs should have executed
        assert mock_func1.call_count >= 1
        assert mock_func2.call_count >= 1
        assert mock_func3.call_count >= 1

    def test_get_jobs_returns_copy(self, scheduler: JobScheduler):
        """Test get_jobs returns a copy of job list."""
        mock_func = Mock()

        scheduler.add_job(func=mock_func, job_name="test", interval_seconds=10)

        jobs1 = scheduler.get_jobs()
        jobs2 = scheduler.get_jobs()

        assert jobs1 == jobs2
        assert jobs1 is not jobs2  # Different list objects


class TestCronScheduling:
    """Tests for cron-based scheduling."""

    def test_add_job_cron_registers(self, scheduler: JobScheduler):
        mock_func = Mock()
        scheduler.add_job_cron(mock_func, "cron_job", "*/5 * * * *")
        assert "cron_job" in scheduler.get_jobs()

    def test_add_job_cron_disabled_skips(self, scheduler: JobScheduler):
        mock_func = Mock()
        scheduler.add_job_cron(mock_func, "disabled_cron", "0 * * * *", enabled=False)
        assert "disabled_cron" not in scheduler.get_jobs()

    def test_add_job_cron_invalid_expression_raises(self, scheduler: JobScheduler):
        mock_func = Mock()
        with pytest.raises(ValueError, match="Invalid cron expression"):
            scheduler.add_job_cron(mock_func, "bad_cron", "not a cron")

    def test_add_job_cron_duplicate_warns(self, scheduler: JobScheduler, caplog):
        mock_func = Mock()
        scheduler.add_job_cron(mock_func, "dup_cron", "0 * * * *")
        scheduler.add_job_cron(mock_func, "dup_cron", "0 2 * * *")
        assert "already registered" in caplog.text
        assert scheduler.get_jobs().count("dup_cron") == 1

    def test_add_job_cron_job_info_has_trigger(self, scheduler: JobScheduler):
        mock_func = Mock()
        scheduler.add_job_cron(mock_func, "cron_info", "0 6 * * *")
        info = scheduler.get_job_info("cron_info")
        assert info is not None
        assert "cron" in info["trigger"].lower()


class TestJobDefinition:
    """Tests for add_job_definition."""

    def test_add_interval_definition(self, scheduler: JobScheduler):
        mock_func = Mock()
        job_def = JobDefinition(
            name="interval_def",
            func=mock_func,
            interval_seconds=60.0,
            priority=JobPriority.HIGH,
        )
        scheduler.add_job_definition(job_def)
        assert "interval_def" in scheduler.get_jobs()

    def test_add_cron_definition(self, scheduler: JobScheduler):
        mock_func = Mock()
        job_def = JobDefinition(
            name="cron_def",
            func=mock_func,
            schedule="0 3 * * *",
        )
        scheduler.add_job_definition(job_def)
        assert "cron_def" in scheduler.get_jobs()

    def test_definition_disabled_skips(self, scheduler: JobScheduler):
        mock_func = Mock()
        job_def = JobDefinition(
            name="off_def",
            func=mock_func,
            interval_seconds=30.0,
            enabled=False,
        )
        scheduler.add_job_definition(job_def)
        assert "off_def" not in scheduler.get_jobs()

    def test_definition_priority_in_job_info(self, scheduler: JobScheduler):
        mock_func = Mock()
        job_def = JobDefinition(
            name="prio_job",
            func=mock_func,
            interval_seconds=10.0,
            priority=JobPriority.CRITICAL,
        )
        scheduler.add_job_definition(job_def)
        info = scheduler.get_job_info("prio_job")
        assert info is not None
        assert info["priority"] == JobPriority.CRITICAL

    def test_definition_no_schedule_or_interval_raises(self, scheduler: JobScheduler):
        mock_func = Mock()
        job_def = JobDefinition(name="bad", func=mock_func, interval_seconds=1)
        # Bypass post-init validation to simulate a bad state
        job_def.schedule = None
        job_def.interval_seconds = None
        with pytest.raises(ValueError, match="neither schedule nor interval_seconds"):
            scheduler.add_job_definition(job_def)


class TestExecutionTracking:
    """Tests that execution tracking records results in the store."""

    def test_successful_job_records_completed(
        self, scheduler: JobScheduler, store: JobExecutionStore
    ):
        mock_func = Mock(return_value={"ok": True})
        scheduler.add_job(mock_func, "tracked_job", interval_seconds=0.1)
        scheduler.start()
        time.sleep(0.35)
        scheduler.shutdown(wait=True)

        last = store.get_last_execution("tracked_job")
        assert last is not None
        assert last.status == JobStatus.COMPLETED

    def test_failing_job_records_failed(self, scheduler: JobScheduler, store: JobExecutionStore):
        def boom():
            raise RuntimeError("explode")

        scheduler.add_job(boom, "failing_tracked", interval_seconds=0.1)
        scheduler.start()
        time.sleep(0.35)
        scheduler.shutdown(wait=False)

        last = store.get_last_execution("failing_tracked")
        assert last is not None
        assert last.status == JobStatus.FAILED
        assert last.error is not None

    def test_get_execution_history_newest_first(
        self, scheduler: JobScheduler, store: JobExecutionStore
    ):
        mock_func = Mock(return_value={})
        scheduler.add_job(mock_func, "history_job", interval_seconds=0.05)
        scheduler.start()
        time.sleep(0.4)
        scheduler.shutdown(wait=True)

        history = scheduler.get_execution_history("history_job")
        assert len(history) >= 2
        # Newest first: started_at of first entry >= second entry
        assert history[0]["started_at"] >= history[1]["started_at"]

    def test_job_info_includes_last_status(self, scheduler: JobScheduler, store: JobExecutionStore):
        mock_func = Mock(return_value={})
        scheduler.add_job(mock_func, "info_tracked", interval_seconds=0.1)
        scheduler.start()
        time.sleep(0.3)
        scheduler.shutdown(wait=True)

        info = scheduler.get_job_info("info_tracked")
        assert info is not None
        assert "last_status" in info
        assert info["last_status"] == "completed"


class TestPauseResumeRunNow:
    """Tests for pause, resume, and run_now."""

    def test_pause_and_resume(self, scheduler: JobScheduler):
        mock_func = Mock()
        scheduler.add_job(mock_func, "pauseable", interval_seconds=10)
        scheduler.start()

        scheduler.pause_job("pauseable")
        # A paused job's next_run_time is None
        job = scheduler.scheduler.get_job("pauseable")
        assert job.next_run_time is None

        scheduler.resume_job("pauseable")
        job = scheduler.scheduler.get_job("pauseable")
        assert job.next_run_time is not None

        scheduler.shutdown(wait=False)

    def test_pause_nonexistent_raises(self, scheduler: JobScheduler):
        with pytest.raises(KeyError):
            scheduler.pause_job("ghost")

    def test_resume_nonexistent_raises(self, scheduler: JobScheduler):
        with pytest.raises(KeyError):
            scheduler.resume_job("ghost")

    def test_run_now_nonexistent_raises(self, scheduler: JobScheduler):
        with pytest.raises(KeyError):
            scheduler.run_now("ghost")

    def test_run_now_triggers_execution(self, scheduler: JobScheduler, store: JobExecutionStore):
        mock_func = Mock(return_value={})
        # Long interval so it won't fire on its own
        scheduler.add_job(mock_func, "run_now_job", interval_seconds=9999)
        scheduler.start()

        scheduler.run_now("run_now_job")
        time.sleep(0.3)
        scheduler.shutdown(wait=True)

        assert mock_func.call_count >= 1

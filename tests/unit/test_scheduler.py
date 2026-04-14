"""Tests for job scheduler."""

import time
from unittest.mock import Mock

import pytest

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
def scheduler(daemon_config: DaemonConfig) -> JobScheduler:
    """Create job scheduler for testing."""
    return JobScheduler(daemon_config)


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

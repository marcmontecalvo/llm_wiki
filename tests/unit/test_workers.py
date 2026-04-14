"""Tests for worker pool."""

import time
from unittest.mock import Mock

import pytest

from llm_wiki.daemon.workers import WorkerPool, create_worker_pool
from llm_wiki.models.config import DaemonConfig


@pytest.fixture
def daemon_config() -> DaemonConfig:
    """Create daemon config for testing."""
    return DaemonConfig(
        max_parallel_jobs=2,
        log_level="INFO",
    )


@pytest.fixture
def worker_pool(daemon_config: DaemonConfig) -> WorkerPool:
    """Create worker pool for testing."""
    return WorkerPool(daemon_config)


class TestWorkerPool:
    """Tests for WorkerPool class."""

    def test_init(self, worker_pool: WorkerPool, daemon_config: DaemonConfig):
        """Test worker pool initialization."""
        assert worker_pool.config == daemon_config
        assert worker_pool.max_workers == daemon_config.max_parallel_jobs
        assert not worker_pool.is_running()

    def test_start(self, worker_pool: WorkerPool):
        """Test starting the worker pool."""
        assert not worker_pool.is_running()

        worker_pool.start()

        assert worker_pool.is_running()

        # Cleanup
        worker_pool.shutdown(wait=False)

    def test_start_already_started_raises(self, worker_pool: WorkerPool):
        """Test starting already started pool raises error."""
        worker_pool.start()

        with pytest.raises(RuntimeError, match="already started"):
            worker_pool.start()

        # Cleanup
        worker_pool.shutdown(wait=False)

    def test_shutdown(self, worker_pool: WorkerPool):
        """Test shutting down the worker pool."""
        worker_pool.start()
        assert worker_pool.is_running()

        worker_pool.shutdown(wait=False)

        assert not worker_pool.is_running()

    def test_shutdown_with_wait(self, worker_pool: WorkerPool):
        """Test shutdown waits for jobs to complete."""

        def slow_job():
            time.sleep(0.2)
            return "done"

        worker_pool.start()
        future = worker_pool.submit(slow_job)

        worker_pool.shutdown(wait=True)

        # Job should have completed
        assert future.done()
        assert future.result() == "done"

    def test_shutdown_not_started_warns(self, worker_pool: WorkerPool, caplog):
        """Test shutting down non-started pool warns."""
        worker_pool.shutdown()

        assert "not started" in caplog.text

    def test_submit_job(self, worker_pool: WorkerPool):
        """Test submitting a job."""
        mock_func = Mock(return_value=42)

        worker_pool.start()
        future = worker_pool.submit(mock_func)

        # Wait for completion
        result = future.result(timeout=1.0)

        assert result == 42
        mock_func.assert_called_once()

        # Cleanup
        worker_pool.shutdown(wait=False)

    def test_submit_job_with_args(self, worker_pool: WorkerPool):
        """Test submitting job with arguments."""

        def add(a, b):
            return a + b

        worker_pool.start()
        future = worker_pool.submit(add, 5, 3)

        result = future.result(timeout=1.0)

        assert result == 8

        worker_pool.shutdown(wait=False)

    def test_submit_job_with_kwargs(self, worker_pool: WorkerPool):
        """Test submitting job with keyword arguments."""

        def multiply(x, y):
            return x * y

        worker_pool.start()
        future = worker_pool.submit(multiply, x=7, y=6)

        result = future.result(timeout=1.0)

        assert result == 42

        worker_pool.shutdown(wait=False)

    def test_submit_without_start_raises(self, worker_pool: WorkerPool):
        """Test submitting job without starting pool raises error."""
        mock_func = Mock()

        with pytest.raises(RuntimeError, match="not started"):
            worker_pool.submit(mock_func)

    def test_job_exception_doesnt_crash_pool(self, worker_pool: WorkerPool):
        """Test job exceptions don't crash the pool."""

        def failing_job():
            raise ValueError("Job failed!")

        worker_pool.start()
        future = worker_pool.submit(failing_job)

        with pytest.raises(ValueError, match="Job failed"):
            future.result(timeout=1.0)

        # Pool should still be running
        assert worker_pool.is_running()

        worker_pool.shutdown(wait=False)

    def test_concurrent_jobs(self, worker_pool: WorkerPool):
        """Test multiple jobs run concurrently."""
        results = []

        def job(value):
            time.sleep(0.1)
            results.append(value)
            return value

        worker_pool.start()

        futures = [worker_pool.submit(job, i) for i in range(4)]

        # Wait for all jobs
        for future in futures:
            future.result(timeout=2.0)

        assert len(results) == 4
        assert set(results) == {0, 1, 2, 3}

        worker_pool.shutdown(wait=False)

    def test_respects_max_workers(self, daemon_config: DaemonConfig):
        """Test pool respects max_workers limit."""
        # Create pool with max_workers=2
        pool = WorkerPool(daemon_config)
        assert pool.max_workers == 2

        running_count = []

        def job():
            running_count.append(1)
            time.sleep(0.2)
            running_count.pop()

        pool.start()

        # Submit more jobs than max_workers
        futures = [pool.submit(job) for _ in range(4)]

        # Brief wait to let some jobs start
        time.sleep(0.1)

        # Should never exceed max_workers
        assert len(running_count) <= 2

        # Wait for completion
        for future in futures:
            future.result(timeout=2.0)

        pool.shutdown(wait=False)

    def test_get_active_count(self, worker_pool: WorkerPool):
        """Test getting active worker count."""
        worker_pool.start()

        # Initially no active jobs
        assert worker_pool.get_active_count() == 0

        def slow_job():
            time.sleep(0.3)

        # Submit jobs
        future1 = worker_pool.submit(slow_job)
        future2 = worker_pool.submit(slow_job)

        time.sleep(0.1)  # Let jobs start

        # Should have active jobs
        active = worker_pool.get_active_count()
        assert active >= 1  # At least one running

        # Wait for completion
        future1.result(timeout=1.0)
        future2.result(timeout=1.0)

        # Eventually no active jobs
        time.sleep(0.1)
        assert worker_pool.get_active_count() == 0

        worker_pool.shutdown(wait=False)

    def test_get_active_count_not_started(self, worker_pool: WorkerPool):
        """Test get_active_count returns 0 when not started."""
        assert worker_pool.get_active_count() == 0

    def test_wait_for_completion(self, worker_pool: WorkerPool):
        """Test waiting for all jobs to complete."""
        completed = []

        def job(value):
            time.sleep(0.1)
            completed.append(value)

        worker_pool.start()

        for i in range(3):
            worker_pool.submit(job, i)

        # Wait for all to complete
        success = worker_pool.wait_for_completion(timeout=2.0)

        assert success
        assert len(completed) == 3

        worker_pool.shutdown(wait=False)

    def test_wait_for_completion_timeout(self, worker_pool: WorkerPool):
        """Test wait_for_completion with timeout."""

        def slow_job():
            time.sleep(2.0)

        worker_pool.start()
        worker_pool.submit(slow_job)

        # Short timeout
        success = worker_pool.wait_for_completion(timeout=0.2)

        assert not success

        worker_pool.shutdown(wait=False, cancel_futures=True)

    def test_wait_for_completion_no_jobs(self, worker_pool: WorkerPool):
        """Test wait_for_completion with no jobs returns True."""
        worker_pool.start()

        success = worker_pool.wait_for_completion(timeout=1.0)

        assert success

        worker_pool.shutdown(wait=False)

    def test_shutdown_with_cancel_futures(self, worker_pool: WorkerPool):
        """Test shutdown cancels pending futures."""

        def slow_job():
            time.sleep(2.0)
            return "done"

        worker_pool.start()

        # Submit more jobs than workers
        futures = [worker_pool.submit(slow_job) for _ in range(4)]

        # Shutdown immediately with cancel
        worker_pool.shutdown(wait=False, cancel_futures=True)

        # Some futures should be cancelled
        cancelled_count = sum(1 for f in futures if f.cancelled())
        assert cancelled_count > 0

    def test_future_cleanup(self, worker_pool: WorkerPool):
        """Test futures are cleaned up after completion."""

        def quick_job():
            return "done"

        worker_pool.start()

        # Submit and complete a job
        future = worker_pool.submit(quick_job)
        future.result(timeout=1.0)

        # Give cleanup callback time to run
        time.sleep(0.1)

        # Future should be removed from tracking
        assert future not in worker_pool._futures  # noqa: SLF001

        worker_pool.shutdown(wait=False)


class TestCreateWorkerPool:
    """Tests for create_worker_pool factory function."""

    def test_create_worker_pool(self, daemon_config: DaemonConfig):
        """Test factory creates worker pool."""
        pool = create_worker_pool(daemon_config)

        assert isinstance(pool, WorkerPool)
        assert pool.config == daemon_config
        assert not pool.is_running()

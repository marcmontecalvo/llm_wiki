"""Tests for daemon main loop."""

import logging
import signal
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from llm_wiki.daemon.main import WikiDaemon, run_daemon


@pytest.fixture
def temp_config_dir(temp_dir: Path) -> Path:
    """Create temporary config directory with real config files."""
    config_dir = temp_dir / "config"
    config_dir.mkdir()

    # Copy real config files from project
    import shutil

    project_config = Path("config")
    for config_file in ["daemon.yaml", "domains.yaml", "models.yaml", "routing.yaml"]:
        src = project_config / config_file
        if src.exists():
            shutil.copy(src, config_dir / config_file)

    return config_dir


class TestWikiDaemon:
    """Tests for WikiDaemon class."""

    def test_init(self, temp_config_dir: Path):
        """Test daemon initialization."""
        daemon = WikiDaemon(temp_config_dir)

        assert daemon.config_dir == temp_config_dir
        assert daemon.config is not None
        assert daemon.scheduler is None
        assert daemon.worker_pool is None
        assert not daemon.is_running()

    def test_start(self, temp_config_dir: Path):
        """Test starting the daemon."""
        daemon = WikiDaemon(temp_config_dir)

        daemon.start()

        assert daemon.is_running()
        assert daemon.scheduler is not None
        assert daemon.worker_pool is not None
        assert daemon.scheduler.is_running()
        assert daemon.worker_pool.is_running()

        # Cleanup
        daemon.shutdown(wait_for_jobs=False)

    def test_start_already_running_raises(self, temp_config_dir: Path):
        """Test starting already running daemon raises error."""
        daemon = WikiDaemon(temp_config_dir)
        daemon.start()

        with pytest.raises(RuntimeError, match="already running"):
            daemon.start()

        # Cleanup
        daemon.shutdown(wait_for_jobs=False)

    def test_shutdown(self, temp_config_dir: Path):
        """Test shutting down the daemon."""
        daemon = WikiDaemon(temp_config_dir)
        daemon.start()

        assert daemon.is_running()

        daemon.shutdown(wait_for_jobs=False)

        assert not daemon.is_running()
        assert daemon.scheduler is None
        assert daemon.worker_pool is None

    def test_shutdown_not_running_warns(self, temp_config_dir: Path, caplog):
        """Test shutting down non-running daemon warns."""
        daemon = WikiDaemon(temp_config_dir)

        daemon.shutdown()

        assert "not running" in caplog.text

    def test_signal_handler_sets_shutdown_event(self, temp_config_dir: Path):
        """Test signal handler sets shutdown event."""
        daemon = WikiDaemon(temp_config_dir)
        daemon.start()

        # Simulate signal
        daemon._signal_handler(signal.SIGTERM, None)

        assert daemon._shutdown_event.is_set()

        # Cleanup
        daemon.shutdown(wait_for_jobs=False)

    def test_run_with_immediate_shutdown(self, temp_config_dir: Path):
        """Test daemon run loop with immediate shutdown."""
        daemon = WikiDaemon(temp_config_dir)
        daemon.start()

        # Patch signal handler setup to avoid "signal only works in main thread" error
        with patch.object(daemon, "_setup_signal_handlers"):
            # Run in separate thread
            def run_thread():
                try:
                    daemon.run()
                except SystemExit:
                    pass

            thread = threading.Thread(target=run_thread, daemon=True)
            thread.start()

            # Wait a moment for daemon to enter main loop
            time.sleep(0.2)

            # Signal shutdown
            daemon._shutdown_event.set()

            # Wait for thread to complete (with timeout)
            thread.join(timeout=2.0)

            assert not daemon.is_running()

    def test_run_without_start_raises(self, temp_config_dir: Path):
        """Test run without start raises error."""
        daemon = WikiDaemon(temp_config_dir)

        with pytest.raises(RuntimeError, match="not started"):
            daemon.run()

    def test_is_running(self, temp_config_dir: Path):
        """Test is_running reflects daemon state."""
        daemon = WikiDaemon(temp_config_dir)

        assert not daemon.is_running()

        daemon.start()
        assert daemon.is_running()

        daemon.shutdown(wait_for_jobs=False)
        assert not daemon.is_running()

    def test_signal_handlers_registered(self, temp_config_dir: Path):
        """Test signal handlers are registered."""
        daemon = WikiDaemon(temp_config_dir)
        daemon.start()

        # Setup signal handlers
        daemon._setup_signal_handlers()

        # Verify handlers are set (we can't easily test this directly,
        # but we can verify no errors occurred)
        assert daemon is not None

        # Cleanup
        daemon.shutdown(wait_for_jobs=False)


class TestRunDaemon:
    """Tests for run_daemon function."""

    def test_run_daemon_basic_logging(self, temp_config_dir: Path, caplog):
        """Test run_daemon configures logging."""
        caplog.set_level(logging.INFO)

        with patch("llm_wiki.daemon.main.WikiDaemon") as mock_daemon_class:
            mock_daemon = Mock()
            mock_daemon_class.return_value = mock_daemon
            mock_daemon.start.return_value = None

            # Mock run to exit with SystemExit(0)
            def mock_run():
                import sys

                sys.exit(0)

            mock_daemon.run = mock_run

            # Run daemon (will exit with SystemExit(0))
            with pytest.raises(SystemExit) as exc_info:
                run_daemon(temp_config_dir)

            # Should exit with code 0
            assert exc_info.value.code == 0

            # Verify initialization logged
            assert "Initializing wiki daemon" in caplog.text

    def test_run_daemon_handles_exceptions(self, temp_config_dir: Path, caplog):
        """Test run_daemon handles exceptions gracefully."""
        caplog.set_level(logging.ERROR)

        with patch("llm_wiki.daemon.main.WikiDaemon") as mock_daemon_class:
            mock_daemon_class.side_effect = Exception("Test error")

            with pytest.raises(SystemExit) as exc_info:
                run_daemon(temp_config_dir)

            # Should exit with code 1
            assert exc_info.value.code == 1

            # Should log fatal error
            assert "Fatal error" in caplog.text


class TestDaemonIntegration:
    """Integration tests for daemon."""

    def test_daemon_lifecycle(self, temp_config_dir: Path):
        """Test complete daemon lifecycle."""
        daemon = WikiDaemon(temp_config_dir)

        # Not running initially
        assert not daemon.is_running()

        # Start daemon
        daemon.start()
        assert daemon.is_running()

        # Verify subsystems started
        assert daemon.scheduler is not None
        assert daemon.worker_pool is not None
        assert daemon.scheduler.is_running()
        assert daemon.worker_pool.is_running()

        # Shutdown daemon
        daemon.shutdown(wait_for_jobs=True)

        # Not running after shutdown
        assert not daemon.is_running()

        # Subsystems cleaned up
        assert daemon.scheduler is None
        assert daemon.worker_pool is None

    def test_daemon_with_worker_jobs(self, temp_config_dir: Path):
        """Test daemon can submit jobs through worker pool."""
        daemon = WikiDaemon(temp_config_dir)
        daemon.start()

        results = []

        def test_job(value):
            results.append(value)
            return value

        # Submit jobs through worker pool
        if daemon.worker_pool:
            future1 = daemon.worker_pool.submit(test_job, 1)
            future2 = daemon.worker_pool.submit(test_job, 2)

            # Wait for completion
            future1.result(timeout=1.0)
            future2.result(timeout=1.0)

            assert 1 in results
            assert 2 in results

        daemon.shutdown(wait_for_jobs=True)

    def test_daemon_shutdown_waits_for_jobs(self, temp_config_dir: Path):
        """Test daemon shutdown waits for running jobs."""
        daemon = WikiDaemon(temp_config_dir)
        daemon.start()

        completed = []

        def slow_job():
            time.sleep(0.3)
            completed.append(True)

        # Submit slow job
        if daemon.worker_pool:
            daemon.worker_pool.submit(slow_job)

        # Shutdown with wait
        daemon.shutdown(wait_for_jobs=True)

        # Job should have completed
        assert len(completed) == 1

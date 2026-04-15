"""Daemon main loop and lifecycle management."""

import logging
import signal
import sys
import threading
from pathlib import Path
from typing import NoReturn

from llm_wiki.config.loader import load_config
from llm_wiki.daemon.logging_config import setup_logging
from llm_wiki.daemon.scheduler import JobScheduler
from llm_wiki.daemon.workers import WorkerPool

logger = logging.getLogger(__name__)


class WikiDaemon:
    """Main daemon class for wiki maintenance."""

    def __init__(self, config_dir: Path | str = "config"):
        """Initialize daemon.

        Args:
            config_dir: Path to configuration directory
        """
        self.config_dir = Path(config_dir)
        self.config = load_config(self.config_dir)
        self.scheduler: JobScheduler | None = None
        self.worker_pool: WorkerPool | None = None
        self._shutdown_event = threading.Event()
        self._running = False

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        logger.info("Signal handlers registered (SIGINT, SIGTERM)")

    def _signal_handler(self, signum: int, frame: object) -> None:
        """Handle shutdown signals.

        Args:
            signum: Signal number
            frame: Current stack frame
        """
        sig_name = signal.Signals(signum).name
        logger.info(f"Received {sig_name}, initiating graceful shutdown...")
        self._shutdown_event.set()

    def start(self) -> None:
        """Start the daemon.

        Raises:
            RuntimeError: If daemon is already running
        """
        if self._running:
            raise RuntimeError("Daemon is already running")

        logger.info("Starting wiki daemon...")

        # Initialize subsystems
        self.worker_pool = WorkerPool(self.config.daemon.daemon)
        self.scheduler = JobScheduler(self.config.daemon.daemon)

        # Start worker pool
        self.worker_pool.start()
        logger.info("Worker pool started")

        # Register jobs
        wiki_base = Path("wiki_system")

        # Register governance job
        from llm_wiki.daemon.jobs.governance import run_governance_check

        self.scheduler.add_job(
            func=run_governance_check,
            job_name="governance_check",
            interval_seconds=self.config.daemon.daemon.lint_every_minutes * 60,
            wiki_base=wiki_base,
        )

        # Register promotion job
        if self.config.daemon.daemon.promotion.enabled:
            from llm_wiki.daemon.jobs.promotion import run_promotion_check

            self.scheduler.add_job(
                func=run_promotion_check,
                job_name="promotion_check",
                interval_seconds=self.config.daemon.daemon.promotion_every_hours * 3600,
                wiki_base=wiki_base,
                config=self.config.daemon.daemon.promotion,
            )

        # Start scheduler
        self.scheduler.start()
        logger.info("Scheduler started")

        self._running = True
        logger.info("Wiki daemon started successfully")

    def run(self) -> NoReturn:
        """Run the daemon main loop.

        This is a blocking call that runs until a shutdown signal is received.

        Raises:
            RuntimeError: If daemon is not started
        """
        if not self._running:
            raise RuntimeError("Daemon not started. Call start() first.")

        logger.info("Entering main loop...")

        # Set up signal handlers
        self._setup_signal_handlers()

        # Wait for shutdown signal
        try:
            while not self._shutdown_event.is_set():
                self._shutdown_event.wait(timeout=1.0)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            self._shutdown_event.set()

        finally:
            self.shutdown()
            logger.info("Daemon shutdown complete")
            sys.exit(0)

    def shutdown(self, wait_for_jobs: bool = True) -> None:
        """Shutdown the daemon gracefully.

        Args:
            wait_for_jobs: If True, wait for running jobs to complete
        """
        if not self._running:
            logger.warning("Daemon is not running")
            return

        logger.info(f"Shutting down daemon (wait_for_jobs={wait_for_jobs})...")

        # Stop scheduler first (prevents new jobs from starting)
        if self.scheduler:
            logger.info("Stopping scheduler...")
            self.scheduler.shutdown(wait=wait_for_jobs)
            self.scheduler = None
            logger.info("Scheduler stopped")

        # Stop worker pool (completes or cancels running jobs)
        if self.worker_pool:
            logger.info("Stopping worker pool...")
            self.worker_pool.shutdown(wait=wait_for_jobs, cancel_futures=not wait_for_jobs)
            self.worker_pool = None
            logger.info("Worker pool stopped")

        self._running = False
        logger.info("Daemon shutdown complete")

    def is_running(self) -> bool:
        """Check if daemon is running.

        Returns:
            True if daemon is running
        """
        return self._running


def run_daemon(config_dir: Path | str = "config") -> NoReturn:
    """Run the wiki daemon.

    This is the main entry point for the daemon.

    Args:
        config_dir: Path to configuration directory

    Raises:
        SystemExit: On shutdown
    """
    logger.info("Initializing wiki daemon...")

    try:
        daemon = WikiDaemon(config_dir)

        # Configure logging with daemon config
        setup_logging(daemon.config.daemon.daemon)

        daemon.start()
        daemon.run()

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

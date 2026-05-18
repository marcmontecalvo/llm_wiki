"""Daemon main loop and lifecycle management."""

import logging
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Any, NoReturn

from llm_wiki.config.loader import load_config
from llm_wiki.config.validator import validate_config
from llm_wiki.daemon.errors import ConfigError
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
        report = validate_config(self.config_dir)
        for w in report.warnings:
            logger.warning("Config warning: %s", w)
        if not report.is_valid:
            for e in report.errors:
                logger.error("Config error: %s", e)
            raise ConfigError(f"Invalid configuration: {'; '.join(report.errors)}")
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

        # Register duplicate detection job
        if self.config.daemon.daemon.duplicates.enabled:
            from llm_wiki.daemon.jobs.duplicates import run_duplicate_detection

            self.scheduler.add_job(
                func=run_duplicate_detection,
                job_name="duplicates_check",
                interval_seconds=self.config.daemon.daemon.duplicates.duplicates_check_every_hours
                * 3600,
                wiki_base=wiki_base,
                config=self.config.daemon.daemon.duplicates,
            )
            logger.info(
                f"Registered duplicates_check job "
                f"(every {self.config.daemon.daemon.duplicates.duplicates_check_every_hours}h)"
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

        # Register retry failed ingests job
        from llm_wiki.daemon.jobs.retry_failed_ingests import run_retry_failed_ingests

        self.scheduler.add_job(
            func=run_retry_failed_ingests,
            job_name="retry_failed_ingests",
            interval_seconds=self.config.daemon.daemon.retry_failed_ingests_every_minutes * 60,
            wiki_base=wiki_base,
        )

        # Register review queue population job
        if self.config.daemon.daemon.review_queue_enabled:
            from llm_wiki.daemon.jobs.review_queue import run_review_queue_job

            self.scheduler.add_job(
                func=run_review_queue_job,
                job_name="review_queue_population",
                interval_seconds=self.config.daemon.daemon.review_queue_every_minutes * 60,
                wiki_base=wiki_base,
            )

        # Register inbox scan job (runs after scheduler starts to avoid races)
        from llm_wiki.ingest.watcher import run_inbox_scan

        self.scheduler.add_job(
            func=run_inbox_scan,
            job_name="inbox_scan",
            interval_seconds=self.config.daemon.daemon.inbox_poll_seconds,
            wiki_base=wiki_base,
        )
        logger.info(
            f"Registered inbox_scan job (every {self.config.daemon.daemon.inbox_poll_seconds}s)"
        )

        # Register queue-to-pages job
        from llm_wiki.daemon.jobs.queue_to_pages import run_queue_to_pages

        self.scheduler.add_job(
            func=run_queue_to_pages,
            job_name="queue_to_pages",
            interval_seconds=self.config.daemon.daemon.migrate_queue_every_minutes * 60,
            wiki_base=wiki_base,
        )
        logger.info(
            f"Registered queue_to_pages job "
            f"(every {self.config.daemon.daemon.migrate_queue_every_minutes}m)"
        )

        # Register export job
        from llm_wiki.daemon.jobs.export import run_export_job

        self.scheduler.add_job(
            func=run_export_job,
            job_name="export",
            interval_seconds=self.config.daemon.daemon.export_every_minutes * 60,
            wiki_base=wiki_base,
        )
        logger.info(
            f"Registered export job (every {self.config.daemon.daemon.export_every_minutes}m)"
        )

        # Register index-rebuild job
        from llm_wiki.daemon.jobs.index_rebuild import run_index_rebuild

        self.scheduler.add_job(
            func=run_index_rebuild,
            job_name="index_rebuild",
            interval_seconds=self.config.daemon.daemon.rebuild_index_every_minutes * 60,
            wiki_base=wiki_base,
        )
        logger.info(
            f"Registered index_rebuild job "
            f"(every {self.config.daemon.daemon.rebuild_index_every_minutes}m)"
        )

        # Startup recovery: move orphaned processing/ files back to inbox
        from llm_wiki.ingest.watcher import InboxWatcher

        watcher = InboxWatcher(inbox_dir=wiki_base / "inbox", config_dir=self.config_dir)
        recovered = watcher.recover_processing_dir()
        if recovered:
            logger.warning(
                "Startup inbox recovery: moved %d orphaned file(s) back to inbox/new/",
                recovered,
            )

        # Index integrity check: trigger synchronous rebuild if corruption detected
        from llm_wiki.startup import check_index_integrity

        corrupt_files = check_index_integrity(wiki_base)
        if corrupt_files:
            logger.warning(
                "Index integrity check failed for %d file(s): %s — triggering synchronous rebuild",
                len(corrupt_files),
                corrupt_files,
            )
            try:
                from llm_wiki.daemon.jobs.index_rebuild import IndexRebuildJob

                job = IndexRebuildJob(wiki_base=wiki_base)
                result = job.execute()
                logger.info("Synchronous index rebuild complete: %s", result)
            except Exception as e:
                logger.error(
                    "Synchronous index rebuild failed: %s — "
                    "starting with potentially stale indexes",
                    e,
                )
        else:
            logger.info("Index integrity check passed")

        # Start scheduler
        self.scheduler.start()
        logger.info("Scheduler started")

        self._running = True
        logger.info("Wiki daemon started successfully")

        # Write PID file so /v1/health can track daemon liveness (best-effort)
        pid_path = Path(os.environ.get("WIKI_ROOT", "/wiki")) / "state" / "daemon.pid"
        try:
            pid_path.parent.mkdir(parents=True, exist_ok=True)
            pid_path.write_text(str(os.getpid()))
        except OSError:
            logger.warning("Could not write daemon PID file at %s", pid_path)

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

        # Remove PID file
        pid_path = Path(os.environ.get("WIKI_ROOT", "/wiki")) / "state" / "daemon.pid"
        try:
            pid_path.unlink(missing_ok=True)
        except OSError:
            pass
        logger.info("Daemon shutdown complete")

    def is_running(self) -> bool:
        """Check if daemon is running.

        Returns:
            True if daemon is running
        """
        return self._running

    def health(self) -> dict[str, Any]:
        """Return comprehensive health status.

        Returns:
            Dict with daemon-level and subsystem health data.
        """
        parts: dict[str, Any] = {"running": self._running}
        if self.scheduler:
            parts["scheduler"] = self.scheduler.health()
        if self.worker_pool:
            parts["worker_pool"] = self.worker_pool.health()
        parts["ok"] = self._running and all(
            s.get("running", False)
            for s in (parts.get("scheduler") or {}).values()
            if isinstance(s, dict) and "running" in s
        )
        return parts


def run_daemon(config_dir: Path | str | None = None) -> NoReturn:
    """Run the wiki daemon.

    This is the main entry point for the daemon.

    Args:
        config_dir: Path to configuration directory.
            Defaults to ``WIKI_CONFIG_DIR`` environment variable,
            falling back to ``"config"``.

    Raises:
        SystemExit: On shutdown
    """
    if config_dir is None:
        config_dir = os.environ.get("WIKI_CONFIG_DIR", "config")
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

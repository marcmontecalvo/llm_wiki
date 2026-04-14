"""Worker pool for daemon job execution."""

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Any

from llm_wiki.models.config import DaemonConfig

logger = logging.getLogger(__name__)


class WorkerPool:
    """Thread pool for executing daemon jobs concurrently."""

    def __init__(self, config: DaemonConfig):
        """Initialize worker pool.

        Args:
            config: Daemon configuration
        """
        self.config = config
        self.max_workers = config.max_parallel_jobs
        self._executor: ThreadPoolExecutor | None = None
        self._futures: set[Future[Any]] = set()

    def start(self) -> None:
        """Start the worker pool.

        Raises:
            RuntimeError: If pool is already started
        """
        if self._executor is not None:
            raise RuntimeError("Worker pool is already started")

        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="wiki-worker",
        )
        logger.info(f"Worker pool started with {self.max_workers} workers")

    def shutdown(self, wait: bool = True, cancel_futures: bool = False) -> None:
        """Shutdown the worker pool.

        Args:
            wait: If True, wait for all submitted jobs to complete
            cancel_futures: If True, cancel pending jobs
        """
        if self._executor is None:
            logger.warning("Worker pool is not started")
            return

        try:
            logger.info(
                f"Shutting down worker pool (wait={wait}, cancel_futures={cancel_futures})..."
            )

            # Cancel pending futures if requested
            if cancel_futures:
                # Iterate over a copy to avoid "Set changed size during iteration"
                for future in list(self._futures):
                    if not future.done():
                        future.cancel()
                        logger.debug(f"Cancelled pending future: {future}")

            self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)
            logger.info("Worker pool shutdown complete")

        except Exception as e:
            logger.error(f"Error during worker pool shutdown: {e}")
            raise

        finally:
            self._executor = None
            self._futures.clear()

    def submit(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Future[Any]:
        """Submit a job to the worker pool.

        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Future representing the job execution

        Raises:
            RuntimeError: If pool is not started
        """
        if self._executor is None:
            raise RuntimeError("Worker pool is not started. Call start() first.")

        try:
            future = self._executor.submit(func, *args, **kwargs)
            self._futures.add(future)

            # Add callback to remove completed futures
            future.add_done_callback(self._cleanup_future)

            func_name = getattr(func, "__name__", str(func))
            logger.debug(f"Submitted job {func_name} to worker pool")
            return future

        except Exception as e:
            func_name = getattr(func, "__name__", str(func))
            logger.error(f"Failed to submit job {func_name}: {e}")
            raise

    def _cleanup_future(self, future: Future[Any]) -> None:
        """Remove completed future from tracking.

        Args:
            future: Completed future
        """
        try:
            self._futures.discard(future)
            logger.debug(f"Cleaned up completed future: {future}")
        except Exception as e:
            logger.warning(f"Error cleaning up future: {e}")

    def is_running(self) -> bool:
        """Check if worker pool is running.

        Returns:
            True if pool is running
        """
        return self._executor is not None and not self._executor._shutdown  # noqa: SLF001

    def get_active_count(self) -> int:
        """Get number of active workers.

        Returns:
            Number of active threads, or 0 if pool not started
        """
        if self._executor is None:
            return 0

        # Count active futures
        return sum(1 for f in self._futures if not f.done())

    def get_queue_size(self) -> int:
        """Get number of pending jobs.

        Returns:
            Number of jobs waiting to execute
        """
        if self._executor is None:
            return 0

        # Pending = total futures - completed
        return len([f for f in self._futures if not f.running() and not f.done()])

    def wait_for_completion(self, timeout: float | None = None) -> bool:
        """Wait for all submitted jobs to complete.

        Args:
            timeout: Maximum time to wait in seconds (None for indefinite)

        Returns:
            True if all jobs completed, False if timeout occurred
        """
        if not self._futures:
            return True

        try:
            # Take snapshot of futures to wait for
            futures_to_wait = list(self._futures)
            total_count = len(futures_to_wait)

            completed = set()
            for future in as_completed(futures_to_wait, timeout=timeout):
                completed.add(future)
                try:
                    # Get result to propagate exceptions
                    future.result()
                except Exception as e:
                    logger.error(f"Job failed with exception: {e}")

            return len(completed) == total_count

        except TimeoutError:
            logger.warning(f"Timeout waiting for jobs to complete (timeout={timeout}s)")
            return False


def create_worker_pool(config: DaemonConfig) -> WorkerPool:
    """Factory function to create a worker pool.

    Args:
        config: Daemon configuration

    Returns:
        Initialized worker pool (not started)
    """
    return WorkerPool(config)

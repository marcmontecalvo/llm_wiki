"""Retry logic with exponential backoff."""

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 3600.0  # 1 hour
    exponential_base: float = 2.0
    jitter: bool = True  # Add randomness to prevent thundering herd

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if self.initial_delay_seconds < 0.1:
            raise ValueError("initial_delay_seconds must be at least 0.1")
        if self.max_delay_seconds < self.initial_delay_seconds:
            raise ValueError("max_delay_seconds must be >= initial_delay_seconds")
        if self.exponential_base <= 1:
            raise ValueError("exponential_base must be > 1")


class RetryScheduler:
    """Manages retry scheduling with exponential backoff."""

    def __init__(self, config: RetryConfig | None = None):
        """Initialize retry scheduler.

        Args:
            config: Retry configuration
        """
        self.config = config or RetryConfig()

    def get_retry_delay(self, attempt: int) -> float:
        """Calculate delay for a retry attempt using exponential backoff.

        Args:
            attempt: Retry attempt number (0-based)

        Returns:
            Delay in seconds

        Formula:
            delay = initial_delay * (exponential_base ^ attempt)
            delay = min(delay, max_delay)
            if jitter: delay += random between 0 and delay/2
        """
        if attempt < 0 or attempt >= self.config.max_retries:
            raise ValueError(f"Invalid attempt: {attempt}")

        # Exponential backoff: base^attempt
        delay = self.config.initial_delay_seconds * (self.config.exponential_base**attempt)

        # Cap at max delay
        delay = min(delay, self.config.max_delay_seconds)

        # Add jitter
        if self.config.jitter:
            jitter = random.uniform(0, delay / 2)
            delay += jitter

        return delay

    def should_retry(self, attempt: int, exception: Exception) -> bool:
        """Determine if a retry should be attempted.

        Args:
            attempt: Current attempt number (0-based)
            exception: Exception that occurred

        Returns:
            True if retry should be attempted
        """
        if attempt >= self.config.max_retries:
            logger.debug(f"Max retries ({self.config.max_retries}) exceeded, not retrying")
            return False

        # Could add exception type filtering here if needed
        return True

    def get_next_retry_info(self, attempt: int) -> dict[str, Any]:
        """Get information about the next retry attempt.

        Args:
            attempt: Current attempt number (0-based)

        Returns:
            Dictionary with retry information
        """
        next_attempt = attempt + 1

        if next_attempt >= self.config.max_retries:
            return {
                "will_retry": False,
                "reason": "Max retries exceeded",
            }

        if not self.should_retry(attempt, Exception("Generic")):
            return {
                "will_retry": False,
                "reason": "Retry not allowed",
            }

        delay = self.get_retry_delay(next_attempt)

        return {
            "will_retry": True,
            "attempt": next_attempt,
            "delay_seconds": delay,
            "attempts_remaining": self.config.max_retries - next_attempt,
        }


class RetryableFunction:
    """Wrapper for a function that implements retry logic."""

    def __init__(
        self,
        func: Callable[..., Any],
        config: RetryConfig | None = None,
        on_retry: Callable[[int, Exception, float], None] | None = None,
    ):
        """Initialize retryable function.

        Args:
            func: Function to retry
            config: Retry configuration
            on_retry: Callback when a retry is about to happen
                      (attempt, exception, delay_seconds)
        """
        self.func = func
        self.config = config or RetryConfig()
        self.on_retry = on_retry
        self.scheduler = RetryScheduler(self.config)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute function with retry logic.

        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            Exception: If all retries exhausted
        """
        last_exception = None

        for attempt in range(self.config.max_retries + 1):
            try:
                return self.func(*args, **kwargs)
            except Exception as e:
                last_exception = e

                if not self.scheduler.should_retry(attempt, e):
                    logger.error(
                        f"Function {self.func.__name__} failed (attempt {attempt + 1}): {e}"
                    )
                    raise

                delay = self.scheduler.get_retry_delay(attempt)

                if self.on_retry:
                    self.on_retry(attempt, e, delay)

                logger.warning(
                    f"Function {self.func.__name__} failed (attempt {attempt + 1}), "
                    f"retrying in {delay:.1f}s: {e}"
                )

                # Sleep before retrying
                time.sleep(delay)

        # All retries exhausted
        if last_exception:
            raise last_exception
        raise RuntimeError(f"Function {self.func.__name__} failed after all retries")


def retry(
    config: RetryConfig | None = None,
    on_retry: Callable[[int, Exception, float], None] | None = None,
) -> Callable:
    """Decorator to add retry logic to a function.

    Args:
        config: Retry configuration
        on_retry: Callback for retry events

    Returns:
        Decorator function

    Example:
        @retry(RetryConfig(max_retries=3))
        def my_function():
            ...
    """
    cfg = config or RetryConfig()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        return RetryableFunction(func, cfg, on_retry)

    return decorator

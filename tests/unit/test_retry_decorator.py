"""Tests for retry decorator and RetryableFunction."""

import time
from unittest.mock import MagicMock

import pytest

from llm_wiki.daemon.retry import (
    RetryableFunction,
    RetryConfig,
    RetryScheduler,
    retry,
)


class TestRetryConfig:
    """Test RetryConfig data class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RetryConfig()

        assert config.max_retries == 3
        assert config.initial_delay_seconds == 1.0
        assert config.max_delay_seconds == 3600.0
        assert config.exponential_base == 2.0
        assert config.jitter is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = RetryConfig(
            max_retries=5,
            initial_delay_seconds=2.0,
            max_delay_seconds=120.0,
            exponential_base=3.0,
            jitter=False,
        )

        assert config.max_retries == 5
        assert config.initial_delay_seconds == 2.0
        assert config.max_delay_seconds == 120.0
        assert config.exponential_base == 3.0
        assert config.jitter is False

    def test_validation_negative_max_retries(self):
        """Test validation of negative max_retries."""
        with pytest.raises(ValueError, match="max_retries cannot be negative"):
            RetryConfig(max_retries=-1)

    def test_validation_low_initial_delay(self):
        """Test validation of too-low initial delay."""
        with pytest.raises(ValueError, match="initial_delay_seconds must be at least 0.1"):
            RetryConfig(initial_delay_seconds=0.05)

    def test_validation_max_delay_less_than_initial(self):
        """Test validation of max_delay < initial_delay."""
        with pytest.raises(ValueError, match="max_delay_seconds must be >= initial_delay_seconds"):
            RetryConfig(
                initial_delay_seconds=10.0,
                max_delay_seconds=5.0,
            )

    def test_validation_invalid_exponential_base(self):
        """Test validation of exponential_base <= 1."""
        with pytest.raises(ValueError, match="exponential_base must be > 1"):
            RetryConfig(exponential_base=1.0)


class TestRetryScheduler:
    """Test RetryScheduler."""

    def test_initialization(self):
        """Test scheduler initialization."""
        config = RetryConfig(max_retries=3)
        scheduler = RetryScheduler(config)

        assert scheduler.config == config

    def test_get_retry_delay_first_attempt(self):
        """Test delay calculation for first retry attempt."""
        config = RetryConfig(
            initial_delay_seconds=1.0,
            exponential_base=2.0,
            jitter=False,
        )
        scheduler = RetryScheduler(config)

        delay = scheduler.get_retry_delay(0)
        assert delay == 1.0

    def test_get_retry_delay_second_attempt(self):
        """Test delay calculation for second retry attempt."""
        config = RetryConfig(
            initial_delay_seconds=1.0,
            exponential_base=2.0,
            jitter=False,
        )
        scheduler = RetryScheduler(config)

        delay = scheduler.get_retry_delay(1)
        assert delay == 2.0

    def test_get_retry_delay_exponential_growth(self):
        """Test exponential delay growth."""
        config = RetryConfig(
            initial_delay_seconds=1.0,
            exponential_base=2.0,
            jitter=False,
        )
        scheduler = RetryScheduler(config)

        delays = [scheduler.get_retry_delay(i) for i in range(3)]
        assert delays == [1.0, 2.0, 4.0]

    def test_get_retry_delay_capped_at_max(self):
        """Test that delay is capped at max_delay."""
        config = RetryConfig(
            max_retries=4,
            initial_delay_seconds=1.0,
            max_delay_seconds=5.0,
            exponential_base=2.0,
            jitter=False,
        )
        scheduler = RetryScheduler(config)

        delay = scheduler.get_retry_delay(3)  # Would be 8.0 without cap (2^3)
        assert delay == 5.0

    def test_get_retry_delay_with_jitter(self):
        """Test that jitter adds randomness."""
        config = RetryConfig(
            initial_delay_seconds=1.0,
            exponential_base=2.0,
            jitter=True,
        )
        scheduler = RetryScheduler(config)

        delays = [scheduler.get_retry_delay(0) for _ in range(5)]
        # All should be between 1.0 and 1.5 (base + jitter)
        assert all(1.0 <= d <= 1.5 for d in delays)
        # At least some should be different due to randomness
        assert len(set(delays)) > 1

    def test_should_retry_valid_attempt(self):
        """Test should_retry for valid attempt."""
        config = RetryConfig(max_retries=3)
        scheduler = RetryScheduler(config)

        assert scheduler.should_retry(0, Exception("Test"))
        assert scheduler.should_retry(2, Exception("Test"))

    def test_should_retry_max_retries_exceeded(self):
        """Test should_retry when max retries exceeded."""
        config = RetryConfig(max_retries=3)
        scheduler = RetryScheduler(config)

        assert not scheduler.should_retry(3, Exception("Test"))

    def test_get_next_retry_info_with_remaining_retries(self):
        """Test get_next_retry_info when retries remain."""
        config = RetryConfig(max_retries=3, initial_delay_seconds=1.0, jitter=False)
        scheduler = RetryScheduler(config)

        info = scheduler.get_next_retry_info(0)

        assert info["will_retry"]
        assert info["attempt"] == 1
        assert info["delay_seconds"] == 2.0
        assert info["attempts_remaining"] == 2

    def test_get_next_retry_info_no_retries_left(self):
        """Test get_next_retry_info when no retries remain."""
        config = RetryConfig(max_retries=3)
        scheduler = RetryScheduler(config)

        info = scheduler.get_next_retry_info(3)

        assert not info["will_retry"]
        assert "reason" in info


class TestRetryableFunction:
    """Test RetryableFunction."""

    def test_successful_first_attempt(self):
        """Test function that succeeds on first attempt."""
        func = MagicMock(return_value="success")
        config = RetryConfig(max_retries=3)

        retryable = RetryableFunction(func, config)
        result = retryable()

        assert result == "success"
        assert func.call_count == 1

    def test_successful_after_retry(self):
        """Test function that succeeds after retries."""
        func = MagicMock(side_effect=[ValueError("Fail"), ValueError("Fail"), "success"])
        func.__name__ = "test_func"
        config = RetryConfig(max_retries=3, initial_delay_seconds=0.1, jitter=False)

        retryable = RetryableFunction(func, config)
        result = retryable()

        assert result == "success"
        assert func.call_count == 3

    def test_exhausted_retries(self):
        """Test function that exhausts all retries."""
        func = MagicMock(side_effect=ValueError("Always fails"))
        func.__name__ = "test_func"
        config = RetryConfig(max_retries=2, initial_delay_seconds=0.1, jitter=False)

        retryable = RetryableFunction(func, config)

        with pytest.raises(ValueError, match="Always fails"):
            retryable()

        assert func.call_count == 3  # Initial + 2 retries

    def test_on_retry_callback(self):
        """Test on_retry callback is called."""
        func = MagicMock(side_effect=[ValueError("Fail"), "success"])
        func.__name__ = "test_func"
        callback = MagicMock()
        config = RetryConfig(max_retries=3, initial_delay_seconds=0.1, jitter=False)

        retryable = RetryableFunction(func, config, on_retry=callback)
        result = retryable()

        assert result == "success"
        assert callback.call_count == 1
        # Check callback was called with correct arguments
        args, kwargs = callback.call_args
        assert args[0] == 0  # attempt number
        assert isinstance(args[1], ValueError)  # exception
        assert args[2] > 0  # delay

    def test_decorator(self):
        """Test @retry decorator."""
        call_count = 0

        @retry(RetryConfig(max_retries=2, initial_delay_seconds=0.1, jitter=False))
        def my_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Fail")
            return "success"

        result = my_function()

        assert result == "success"
        assert call_count == 3

    def test_decorator_with_default_config(self):
        """Test @retry decorator with default config."""
        call_count = 0

        @retry()
        def my_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Fail")
            return "success"

        result = my_function()

        assert result == "success"
        assert call_count == 2

    def test_retryable_function_preserves_function_name(self):
        """Test that RetryableFunction preserves wrapped function name."""

        def my_func():
            return "result"

        config = RetryConfig(max_retries=1)
        retryable = RetryableFunction(my_func, config)

        # Access the wrapped function via the RetryableFunction
        assert retryable.func.__name__ == "my_func"

    def test_retryable_with_arguments(self):
        """Test RetryableFunction with function arguments."""
        func = MagicMock(return_value="result")
        func.__name__ = "test_func"
        config = RetryConfig(max_retries=1, initial_delay_seconds=0.1, jitter=False)

        retryable = RetryableFunction(func, config)
        result = retryable(1, 2, 3, key="value")

        assert result == "result"
        func.assert_called_once_with(1, 2, 3, key="value")

    def test_sleep_is_called(self):
        """Test that time.sleep is actually called during retry."""
        func = MagicMock(side_effect=[ValueError("Fail"), "success"])
        func.__name__ = "test_func"
        config = RetryConfig(max_retries=2, initial_delay_seconds=0.1, jitter=False)

        retryable = RetryableFunction(func, config)

        start = time.time()
        result = retryable()
        elapsed = time.time() - start

        assert result == "success"
        # Should have slept at least the delay time (allowing for timing variations)
        assert elapsed >= 0.005  # Be lenient for timing variations

    def test_exception_propagates_correctly(self):
        """Test that the actual exception is propagated."""

        class CustomError(Exception):
            pass

        func = MagicMock(side_effect=CustomError("Custom message"))
        func.__name__ = "test_func"
        config = RetryConfig(max_retries=1, initial_delay_seconds=0.1, jitter=False)

        retryable = RetryableFunction(func, config)

        with pytest.raises(CustomError, match="Custom message"):
            retryable()

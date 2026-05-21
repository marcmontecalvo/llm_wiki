"""Tests for daemon logging configuration."""

import logging
from pathlib import Path

import pytest

from llm_wiki.daemon.logging_config import get_logger, setup_logging
from llm_wiki.models.config import DaemonConfig


@pytest.fixture
def daemon_config() -> DaemonConfig:
    """Create daemon config for testing."""
    return DaemonConfig(log_level="INFO")


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging configuration after each test to avoid interference."""
    yield
    # Clean up after test — close file handles to avoid ResourceWarning
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        if handler.__class__.__name__ != "LogCaptureHandler":
            handler.close()
            root_logger.removeHandler(handler)
    root_logger.setLevel(logging.WARNING)


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_creates_log_file(self, daemon_config: DaemonConfig, temp_dir: Path):
        """Test setup_logging creates log file."""
        log_file = temp_dir / "test.log"

        setup_logging(daemon_config, log_file=log_file, console_output=False)

        assert log_file.exists()

    def test_setup_logging_respects_log_level(self, temp_dir: Path):
        """Test setup_logging respects configured log level."""
        config = DaemonConfig(log_level="DEBUG")
        log_file = temp_dir / "test.log"

        setup_logging(config, log_file=log_file, console_output=False)

        # Root logger should be at DEBUG level
        assert logging.getLogger().level == logging.DEBUG

    def test_setup_logging_writes_to_file(self, daemon_config: DaemonConfig, temp_dir: Path):
        """Test logging writes to file."""
        log_file = temp_dir / "test.log"

        setup_logging(daemon_config, log_file=log_file, console_output=False)

        # Write a log message
        logger = logging.getLogger("test")
        logger.info("Test message")

        # Verify message in file
        content = log_file.read_text()
        assert "Test message" in content
        assert "INFO" in content

    def test_setup_logging_creates_parent_directories(
        self, daemon_config: DaemonConfig, temp_dir: Path
    ):
        """Test setup_logging creates parent directories."""
        log_file = temp_dir / "nested" / "dir" / "test.log"

        setup_logging(daemon_config, log_file=log_file, console_output=False)

        assert log_file.exists()
        assert log_file.parent.exists()

    def test_setup_logging_with_console_output(
        self, daemon_config: DaemonConfig, temp_dir: Path, caplog
    ):
        """Test setup_logging with console output enabled."""
        from logging.handlers import RotatingFileHandler

        log_file = temp_dir / "test.log"

        setup_logging(daemon_config, log_file=log_file, console_output=True)

        # Should have both file and console handlers (plus pytest's handlers)
        root_logger = logging.getLogger()
        # Count non-pytest handlers
        non_pytest_handlers = [
            h for h in root_logger.handlers if h.__class__.__name__ != "LogCaptureHandler"
        ]
        assert len(non_pytest_handlers) >= 2
        # Verify we have file handler
        assert any(isinstance(h, RotatingFileHandler) for h in non_pytest_handlers)

    def test_setup_logging_without_console_output(
        self, daemon_config: DaemonConfig, temp_dir: Path
    ):
        """Test setup_logging without console output."""
        from logging.handlers import RotatingFileHandler

        log_file = temp_dir / "test.log"

        setup_logging(daemon_config, log_file=log_file, console_output=False)

        # Should have only file handler (plus pytest's handlers)
        root_logger = logging.getLogger()
        # Count non-pytest handlers
        non_pytest_handlers = [
            h for h in root_logger.handlers if h.__class__.__name__ != "LogCaptureHandler"
        ]
        assert len(non_pytest_handlers) == 1
        assert isinstance(non_pytest_handlers[0], RotatingFileHandler)

    def test_setup_logging_default_path(self, daemon_config: DaemonConfig):
        """Test setup_logging uses default path when none provided."""
        setup_logging(daemon_config, console_output=False)

        # Should create wiki_system/logs/daemon.log
        log_file = Path("wiki_system") / "logs" / "daemon.log"
        assert log_file.exists()

        # Cleanup
        log_file.unlink()

    def test_setup_logging_removes_old_handlers(self, daemon_config: DaemonConfig, temp_dir: Path):
        """Test setup_logging removes existing handlers."""
        log_file = temp_dir / "test.log"

        # Setup logging twice
        setup_logging(daemon_config, log_file=log_file, console_output=False)
        # Count non-pytest handlers
        handler_count_1 = len(
            [h for h in logging.getLogger().handlers if h.__class__.__name__ != "LogCaptureHandler"]
        )

        setup_logging(daemon_config, log_file=log_file, console_output=False)
        handler_count_2 = len(
            [h for h in logging.getLogger().handlers if h.__class__.__name__ != "LogCaptureHandler"]
        )

        # Should have same number of handlers (old ones removed)
        assert handler_count_1 == handler_count_2

    def test_setup_logging_rotation_config(self, daemon_config: DaemonConfig, temp_dir: Path):
        """Test setup_logging configures rotation correctly."""
        from logging.handlers import RotatingFileHandler

        log_file = temp_dir / "test.log"

        setup_logging(daemon_config, log_file=log_file, console_output=False)

        # Find the RotatingFileHandler
        root_logger = logging.getLogger()
        file_handler = None
        for handler in root_logger.handlers:
            if isinstance(handler, RotatingFileHandler):
                file_handler = handler
                break

        assert file_handler is not None
        assert file_handler.maxBytes == 10 * 1024 * 1024  # 10 MB
        assert file_handler.backupCount == 5  # Keep 5 files

    def test_setup_logging_different_levels(self, temp_dir: Path):
        """Test setup_logging with different log levels."""
        from typing import Literal

        levels: list[Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]] = [
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        ]

        for level in levels:
            config = DaemonConfig(log_level=level)
            log_file = temp_dir / f"{level.lower()}.log"

            setup_logging(config, log_file=log_file, console_output=False)

            expected_level = getattr(logging, level)
            assert logging.getLogger().level == expected_level


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger(self):
        """Test get_logger returns logger."""
        logger = get_logger("test.module")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"

    def test_get_logger_unique_names(self):
        """Test get_logger returns different loggers for different names."""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")

        assert logger1.name != logger2.name

    def test_get_logger_same_name_returns_same_instance(self):
        """Test get_logger returns same instance for same name."""
        logger1 = get_logger("test.module")
        logger2 = get_logger("test.module")

        assert logger1 is logger2


class TestJSONFormatter:
    """Tests for the JSONFormatter used in file logging."""

    def test_format_basic_record(self, daemon_config: DaemonConfig, temp_dir: Path):
        """Test JSONFormatter emits valid JSON with core fields."""
        import json

        from llm_wiki.daemon.logging_config import JSONFormatter

        formatter = JSONFormatter("test-service")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="hello world",
            args=(),
            exc_info=None,
        )
        line = formatter.format(record)
        entry = json.loads(line)

        assert entry["logger"] == "test"
        assert entry["level"] == "INFO"
        assert entry["msg"] == "hello world"
        assert "ts" in entry
        # Timestamp should be parseable ISO-8601
        assert entry["ts"].endswith("Z")

    def test_format_with_extra_data(self, daemon_config: DaemonConfig, temp_dir: Path):
        """Test JSONFormatter includes extra_data fields in output."""
        import json

        from llm_wiki.daemon.logging_config import JSONFormatter

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="job completed",
            args=(),
            exc_info=None,
        )
        record.extra_data = {"job": "export", "duration_seconds": 3.14}  # type: ignore[attr-defined]

        entry = json.loads(formatter.format(record))

        assert entry["msg"] == "job completed"
        assert entry["job"] == "export"
        assert entry["duration_seconds"] == 3.14

    def test_format_with_exception(self, daemon_config: DaemonConfig, temp_dir: Path):
        """Test JSONFormatter includes exception info."""
        import json

        from llm_wiki.daemon.logging_config import JSONFormatter

        formatter = JSONFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            excetype, excvalue, tb = sys.exc_info()
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="job failed",
                args=(),
                exc_info=(excetype, excvalue, tb),
            )

        entry = json.loads(formatter.format(record))
        assert "exception" in entry
        assert "ValueError" in entry["exception"]

    def test_format_empty_extra_data_ignored(self, daemon_config: DaemonConfig, temp_dir: Path):
        """Test empty extra_data does not pollute the JSON output."""
        import json

        from llm_wiki.daemon.logging_config import JSONFormatter

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="plain",
            args=(),
            exc_info=None,
        )
        record.extra_data = {}  # type: ignore[attr-defined]

        entry = json.loads(formatter.format(record))
        assert len([k for k in entry if k not in ("ts", "level", "logger", "msg")]) == 0

    def test_file_logs_are_json(self, daemon_config: DaemonConfig, temp_dir: Path):
        """Test that file log entries are valid JSON."""
        import json

        log_file = temp_dir / "test.log"
        setup_logging(daemon_config, log_file=log_file, console_output=False)

        logger = logging.getLogger("json_test")
        logger.info("structured message")

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) >= 1
        # The first line is from setup_logging itself, then our message
        entry = json.loads(lines[-1])
        assert entry["msg"] == "structured message"
        assert entry["logger"] == "json_test"

    def test_file_logs_include_extra_data(self, daemon_config: DaemonConfig, temp_dir: Path):
        """Test file logs carry structured extra_data."""
        import json

        log_file = temp_dir / "test.log"
        setup_logging(daemon_config, log_file=log_file, console_output=False)

        logger = logging.getLogger("json_extra")
        logger.info(
            "job done",
            extra={"extra_data": {"execution_id": "abc-123", "duration_seconds": 7}},
        )

        lines = log_file.read_text().strip().splitlines()
        entry = json.loads(lines[-1])
        assert entry["execution_id"] == "abc-123"
        assert entry["duration_seconds"] == 7

"""Logging configuration for daemon."""

import json
import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from llm_wiki.models.config import DaemonConfig


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter.

    Emits one JSON object per log record with fields suitable for log aggregation
    (e.g. Splunk, Datadog, Loki).
    """

    def __init__(self, logger_name: str = "llm_wiki") -> None:
        """Initialize JSON formatter.

        Args:
            logger_name: Name attributed to the service producing logs.
        """
        super().__init__()
        self.logger_name = logger_name

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string."""
        # Capture extra fields if present
        extra: dict = {}
        if hasattr(record, "extra_data") and record.extra_data:
            extra = record.extra_data  # type: ignore[assignment]

        if record.exc_info and record.exc_info[0] is not None:
            extra["exception"] = self.formatException(record.exc_info)

        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.created % 1 * 1000):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            **extra,
        }
        return json.dumps(entry)


def setup_logging(
    config: DaemonConfig,
    log_file: Path | str | None = None,
    console_output: bool = True,
) -> None:
    """Configure logging with text and JSON formatters for both console and file.

    File logs use JSON for structured aggregation. Console uses text for readability
    during development.

    Args:
        config: Daemon configuration with log_level setting
        log_file: Path to log file (default: wiki_system/logs/daemon.log)
        console_output: If True, also log to console (default: True)
    """
    # Determine log file path
    if log_file is None:
        log_dir = Path("wiki_system") / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "daemon.log"
    else:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)

    # Get log level from config
    log_level = getattr(logging, config.log_level, logging.INFO)

    # Text formatter for console
    text_formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # JSON formatter for file logs
    json_formatter = JSONFormatter()

    # Create handlers
    handlers: list[logging.Handler] = []

    # File handler with rotation (JSON)
    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,  # Keep 5 old files
        encoding="utf-8",
    )
    file_handler.setFormatter(json_formatter)
    file_handler.setLevel(log_level)
    handlers.append(file_handler)

    # Console handler (text)
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(text_formatter)
        console_handler.setLevel(log_level)
        handlers.append(console_handler)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove any existing handlers (except pytest's caplog handler)
    for handler in root_logger.handlers[:]:
        # Preserve pytest's LogCaptureHandler
        if handler.__class__.__name__ != "LogCaptureHandler":
            root_logger.removeHandler(handler)

    # Add our handlers
    for handler in handlers:
        root_logger.addHandler(handler)

    # Log configuration
    logging.info(f"Logging configured: level={config.log_level}, file={log_file}")


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)

"""Logging configuration for daemon."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from llm_wiki.models.config import DaemonConfig


def setup_logging(
    config: DaemonConfig,
    log_file: Path | str | None = None,
    console_output: bool = True,
) -> None:
    """Configure logging for the daemon.

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

    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Create handlers
    handlers: list[logging.Handler] = []

    # File handler with rotation
    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,  # Keep 5 old files
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)
    handlers.append(file_handler)

    # Console handler for development
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
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

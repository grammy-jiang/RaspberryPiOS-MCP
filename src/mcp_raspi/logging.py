"""
Structured logging framework for the Raspberry Pi MCP Server.

This module provides JSON-formatted structured logging following the design
specifications in doc 09 (Logging, Observability & Diagnostics).

Features:
- JSON-formatted log output for machine-readable logs
- Consistent field structure across all log entries
- Debug mode support for development
- Thread-safe logging
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp_raspi.config import LoggingConfig

# Default log format for fallback
DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class JSONFormatter(logging.Formatter):
    """
    A logging formatter that outputs log records as JSON objects.

    Each log record is formatted as a JSON object with consistent fields:
    - timestamp: ISO 8601 formatted timestamp in UTC
    - level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - logger: Logger name
    - message: Log message
    - Additional fields from the record's extra dict
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record as a JSON string.

        Args:
            record: The log record to format.

        Returns:
            JSON-formatted string representation of the log record.
        """
        # Build the base log entry
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add any extra fields passed to the logger
        # These are fields added via the `extra` parameter in logging calls
        extra_keys = set(record.__dict__.keys()) - {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "exc_info",
            "exc_text",
            "thread",
            "threadName",
            "taskName",
            "message",
        }

        for key in extra_keys:
            value = getattr(record, key, None)
            if value is not None:
                log_entry[key] = value

        return json.dumps(log_entry, default=str)


def setup_logging(
    config: LoggingConfig | None = None,
    *,
    level: str = "INFO",
    json_format: bool = True,
    log_to_stdout: bool = True,
) -> logging.Logger:
    """
    Configure the logging system for the MCP server.

    This function sets up structured logging with JSON formatting by default,
    suitable for both development and production environments.

    Args:
        config: Optional LoggingConfig object with logging settings.
            If provided, overrides other parameters.
        level: Default log level if no config is provided.
        json_format: Whether to use JSON formatting (default: True).
        log_to_stdout: Whether to log to stdout (default: True).

    Returns:
        The root logger configured for the mcp_raspi package.

    Example:
        >>> from mcp_raspi.logging import setup_logging
        >>> logger = setup_logging(level="DEBUG")
        >>> logger.info("Server started", extra={"port": 8000})
    """
    # Determine log level from config or parameter
    if config is not None:
        log_level = config.level.upper()
        json_format = True  # Always use JSON in production
        log_to_stdout = config.log_to_stdout
    else:
        log_level = level.upper()

    # Get the root logger for our package
    logger = logging.getLogger("mcp_raspi")
    logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create handler(s)
    if log_to_stdout:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(getattr(logging, log_level, logging.INFO))

        if json_format:
            handler.setFormatter(JSONFormatter())
        else:
            handler.setFormatter(logging.Formatter(DEFAULT_LOG_FORMAT))

        logger.addHandler(handler)

    # Prevent propagation to root logger to avoid duplicate logs
    logger.propagate = False

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.

    This function returns a child logger of the main mcp_raspi logger,
    ensuring consistent configuration across all modules.

    Args:
        name: The name for the logger, typically __name__ of the calling module.
            The "mcp_raspi." prefix is added automatically if not present.

    Returns:
        A configured logger instance.

    Example:
        >>> from mcp_raspi.logging import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("Module initialized")
    """
    # Ensure the name is prefixed with mcp_raspi
    if not name.startswith("mcp_raspi"):
        name = f"mcp_raspi.{name}"

    return logging.getLogger(name)

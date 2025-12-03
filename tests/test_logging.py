"""
Tests for the logging module.

This test module validates:
- JSON-formatted structured logging output
- Logger configuration and setup
- Log level handling
- Extra fields in log entries
"""

from __future__ import annotations

import json
import logging
from io import StringIO

import pytest

from mcp_raspi.logging import JSONFormatter, get_logger, setup_logging

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def string_handler() -> logging.StreamHandler[StringIO]:
    """Create a string handler for capturing log output."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter())
    return handler


@pytest.fixture(autouse=True)
def _cleanup_loggers() -> None:
    """Clean up loggers after each test (autouse fixture)."""
    yield
    # Remove all handlers from mcp_raspi logger
    logger = logging.getLogger("mcp_raspi")
    logger.handlers.clear()


# =============================================================================
# Tests for JSONFormatter
# =============================================================================


class TestJSONFormatter:
    """Tests for JSONFormatter class."""

    def test_format_basic_log_record(self) -> None:
        """Test formatting a basic log record as JSON."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        parsed = json.loads(result)

        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test_logger"
        assert parsed["message"] == "Test message"
        assert "timestamp" in parsed

    def test_format_with_extra_fields(self) -> None:
        """Test formatting with extra fields."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Server started",
            args=(),
            exc_info=None,
        )
        # Add extra fields
        record.port = 8000
        record.host = "localhost"

        result = formatter.format(record)
        parsed = json.loads(result)

        assert parsed["message"] == "Server started"
        assert parsed["port"] == 8000
        assert parsed["host"] == "localhost"

    def test_format_with_message_args(self) -> None:
        """Test formatting with message arguments."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Value is %d",
            args=(42,),
            exc_info=None,
        )

        result = formatter.format(record)
        parsed = json.loads(result)

        assert parsed["message"] == "Value is 42"

    def test_format_with_exception(self) -> None:
        """Test formatting with exception info."""
        formatter = JSONFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test_logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="An error occurred",
            args=(),
            exc_info=exc_info,
        )

        result = formatter.format(record)
        parsed = json.loads(result)

        assert parsed["level"] == "ERROR"
        assert parsed["message"] == "An error occurred"
        assert "exception" in parsed
        assert "ValueError: Test error" in parsed["exception"]

    def test_format_all_log_levels(self) -> None:
        """Test formatting for all log levels."""
        formatter = JSONFormatter()
        levels = [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
            ("CRITICAL", logging.CRITICAL),
        ]

        for level_name, level_no in levels:
            record = logging.LogRecord(
                name="test_logger",
                level=level_no,
                pathname="test.py",
                lineno=10,
                msg="Test",
                args=(),
                exc_info=None,
            )

            result = formatter.format(record)
            parsed = json.loads(result)

            assert parsed["level"] == level_name

    def test_format_timestamp_is_iso8601(self) -> None:
        """Test that timestamp is in ISO 8601 format."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        parsed = json.loads(result)

        # ISO 8601 format check
        timestamp = parsed["timestamp"]
        assert "T" in timestamp  # ISO 8601 separator
        assert timestamp.endswith("+00:00") or timestamp.endswith("Z")  # UTC timezone


# =============================================================================
# Tests for setup_logging
# =============================================================================


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_returns_logger(self) -> None:
        """Test that setup_logging returns a logger."""
        logger = setup_logging()
        assert isinstance(logger, logging.Logger)
        assert logger.name == "mcp_raspi"

    def test_setup_logging_sets_level(self) -> None:
        """Test that setup_logging sets the correct log level."""
        logger = setup_logging(level="DEBUG")
        assert logger.level == logging.DEBUG

        logger = setup_logging(level="ERROR")
        assert logger.level == logging.ERROR

    def test_setup_logging_json_format(self) -> None:
        """Test that setup_logging uses JSON formatting by default."""
        logger = setup_logging(json_format=True)

        # Check that at least one handler has JSONFormatter
        assert len(logger.handlers) > 0
        json_handlers = [
            h for h in logger.handlers if isinstance(h.formatter, JSONFormatter)
        ]
        assert len(json_handlers) > 0

    def test_setup_logging_non_json_format(self) -> None:
        """Test that setup_logging can use non-JSON format."""
        logger = setup_logging(json_format=False)

        assert len(logger.handlers) > 0
        # None of the handlers should use JSONFormatter
        json_handlers = [
            h for h in logger.handlers if isinstance(h.formatter, JSONFormatter)
        ]
        assert len(json_handlers) == 0

    def test_setup_logging_clears_existing_handlers(self) -> None:
        """Test that setup_logging clears existing handlers."""
        # Setup once
        logger = setup_logging()
        initial_handlers = len(logger.handlers)

        # Setup again - should not add more handlers
        logger = setup_logging()
        assert len(logger.handlers) == initial_handlers

    def test_setup_logging_no_propagation(self) -> None:
        """Test that logger does not propagate to root logger."""
        logger = setup_logging()
        assert logger.propagate is False


# =============================================================================
# Tests for get_logger
# =============================================================================


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_with_module_name(self) -> None:
        """Test getting logger with module name."""
        logger = get_logger("mcp_raspi.config")
        assert logger.name == "mcp_raspi.config"

    def test_get_logger_adds_prefix(self) -> None:
        """Test that get_logger adds mcp_raspi prefix."""
        logger = get_logger("my_module")
        assert logger.name == "mcp_raspi.my_module"

    def test_get_logger_does_not_duplicate_prefix(self) -> None:
        """Test that prefix is not duplicated."""
        logger = get_logger("mcp_raspi.config")
        assert logger.name == "mcp_raspi.config"

    def test_get_logger_is_child_of_main_logger(self) -> None:
        """Test that child loggers inherit from parent."""
        # Setup parent logger
        setup_logging(level="DEBUG")

        # Get child logger
        child_logger = get_logger("config")

        # Child should inherit parent's effective level
        assert child_logger.getEffectiveLevel() == logging.DEBUG


# =============================================================================
# Tests for Structured Logging Output
# =============================================================================


class TestStructuredLoggingOutput:
    """Tests for actual structured logging output."""

    def test_log_output_is_valid_json(
        self, string_handler: logging.StreamHandler[StringIO]
    ) -> None:
        """Test that log output is valid JSON."""
        logger = logging.getLogger("test.json")
        logger.addHandler(string_handler)
        logger.setLevel(logging.INFO)

        logger.info("Test message")

        output = string_handler.stream.getvalue()
        parsed = json.loads(output.strip())

        assert parsed["message"] == "Test message"
        assert parsed["level"] == "INFO"

    def test_log_with_extra_dict(
        self, string_handler: logging.StreamHandler[StringIO]
    ) -> None:
        """Test logging with extra dictionary."""
        logger = logging.getLogger("test.extra")
        logger.addHandler(string_handler)
        logger.setLevel(logging.INFO)

        logger.info("Request received", extra={"method": "GET", "path": "/api/health"})

        output = string_handler.stream.getvalue()
        parsed = json.loads(output.strip())

        assert parsed["message"] == "Request received"
        assert parsed["method"] == "GET"
        assert parsed["path"] == "/api/health"

    def test_multiple_log_entries(
        self, string_handler: logging.StreamHandler[StringIO]
    ) -> None:
        """Test multiple log entries are all valid JSON."""
        logger = logging.getLogger("test.multiple")
        logger.addHandler(string_handler)
        logger.setLevel(logging.INFO)

        logger.info("First message")
        logger.warning("Second message")
        logger.error("Third message")

        output = string_handler.stream.getvalue()
        lines = output.strip().split("\n")

        assert len(lines) == 3
        for line in lines:
            parsed = json.loads(line)
            assert "message" in parsed
            assert "level" in parsed
            assert "timestamp" in parsed


# =============================================================================
# Tests for LoggingConfig Integration
# =============================================================================


class TestLoggingConfigIntegration:
    """Tests for LoggingConfig integration with setup_logging."""

    def test_setup_with_logging_config(self) -> None:
        """Test setup_logging with LoggingConfig object."""
        from mcp_raspi.config import LoggingConfig

        config = LoggingConfig(
            level="debug",
            log_to_stdout=True,
            debug_mode=True,
        )

        logger = setup_logging(config=config)

        assert logger.level == logging.DEBUG
        assert len(logger.handlers) > 0

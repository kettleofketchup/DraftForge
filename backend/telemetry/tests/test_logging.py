"""Tests for telemetry logging configuration."""

import logging
from unittest import TestCase

import structlog
from structlog.testing import capture_logs

from telemetry.logging import configure_logging, get_logger


class ConfigureLoggingTest(TestCase):
    """Tests for configure_logging function."""

    def setUp(self):
        """Reset structlog state before each test."""
        from telemetry import logging as telem_logging

        telem_logging._configured = False
        structlog.reset_defaults()

    def tearDown(self):
        """Clean up structlog state after each test."""
        structlog.reset_defaults()
        structlog.contextvars.clear_contextvars()

    def test_configure_logging_captures_event(self):
        """Logging captures event name."""
        configure_logging(level="INFO", format="json")
        log = get_logger("test")

        with capture_logs() as cap_logs:
            log.info("test_event", key="value")

        self.assertEqual(len(cap_logs), 1)
        self.assertEqual(cap_logs[0]["event"], "test_event")
        self.assertEqual(cap_logs[0]["key"], "value")

    def test_configure_logging_captures_level(self):
        """Logging captures log level."""
        configure_logging(level="INFO", format="json")
        log = get_logger("test")

        with capture_logs() as cap_logs:
            log.warning("warn_event")

        self.assertEqual(cap_logs[0]["log_level"], "warning")

    def test_configure_logging_sets_root_logger_level(self):
        """configure_logging sets the root logger level correctly."""
        configure_logging(level="WARNING", format="json")

        root_logger = logging.getLogger()
        self.assertEqual(root_logger.level, logging.WARNING)

    def test_configure_logging_sets_debug_level(self):
        """configure_logging can set DEBUG level."""
        configure_logging(level="DEBUG", format="json")

        root_logger = logging.getLogger()
        self.assertEqual(root_logger.level, logging.DEBUG)

    def test_configure_logging_quiets_noisy_loggers(self):
        """configure_logging sets third-party loggers to WARNING."""
        configure_logging(level="DEBUG", format="json")

        # These loggers should be quieted to WARNING
        for logger_name in ["urllib3", "requests", "httpx", "httpcore"]:
            logger = logging.getLogger(logger_name)
            self.assertEqual(logger.level, logging.WARNING)


class GetLoggerTest(TestCase):
    """Tests for get_logger function."""

    def setUp(self):
        from telemetry import logging as telem_logging

        telem_logging._configured = False
        structlog.reset_defaults()

    def tearDown(self):
        structlog.reset_defaults()
        structlog.contextvars.clear_contextvars()

    def test_get_logger_returns_bound_logger(self):
        """get_logger returns a structlog logger."""
        configure_logging(level="INFO", format="json")
        log = get_logger("mymodule")

        # Should have standard logging methods
        self.assertTrue(hasattr(log, "info"))
        self.assertTrue(hasattr(log, "warning"))
        self.assertTrue(hasattr(log, "error"))

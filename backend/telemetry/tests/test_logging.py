"""Tests for telemetry logging configuration."""

import logging
import unittest
from typing import Any
from unittest import TestCase

import structlog
from structlog.testing import capture_logs

from telemetry import logging as telem_logging
from telemetry.logging import configure_logging, get_logger

LoggingState = tuple[dict[str, Any], bool, list[logging.Handler], int, dict[str, int]]


def _snapshot() -> LoggingState:
    root = logging.getLogger()
    levels = {
        name: logger.level
        for name, logger in logging.root.manager.loggerDict.items()
        if isinstance(logger, logging.Logger)
    }
    return (
        structlog.get_config(),
        telem_logging._configured,
        list(root.handlers),
        root.level,
        levels,
    )


def _restore(state: LoggingState) -> None:
    config, configured, handlers, level, levels = state
    structlog.reset_defaults()
    structlog.configure(**config)
    telem_logging._configured = configured
    root = logging.getLogger()
    root.handlers = handlers
    root.setLevel(level)
    for name, logger_level in levels.items():
        logging.getLogger(name).setLevel(logger_level)


class ConfigureLoggingTest(TestCase):
    """Tests for configure_logging function."""

    def setUp(self):
        self._saved = _snapshot()
        telem_logging._configured = False
        structlog.reset_defaults()

    def tearDown(self):
        _restore(self._saved)
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
        """configure_logging sets third-party loggers to ERROR."""
        configure_logging(level="DEBUG", format="json")

        for logger_name in [
            "urllib3",
            "requests",
            "httpx",
            "httpcore",
            "opentelemetry.attributes",
            "opentelemetry.exporter.otlp.proto.http._log_exporter",
            "opentelemetry.sdk.metrics._internal.export",
        ]:
            logger = logging.getLogger(logger_name)
            self.assertEqual(logger.level, logging.ERROR, logger_name)


class GetLoggerTest(TestCase):
    """Tests for get_logger function."""

    def setUp(self):
        self._saved = _snapshot()
        telem_logging._configured = False
        structlog.reset_defaults()

    def tearDown(self):
        _restore(self._saved)
        structlog.contextvars.clear_contextvars()

    def test_get_logger_returns_bound_logger(self):
        """get_logger returns a structlog logger."""
        configure_logging(level="INFO", format="json")
        log = get_logger("mymodule")

        # Should have standard logging methods
        self.assertTrue(hasattr(log, "info"))
        self.assertTrue(hasattr(log, "warning"))
        self.assertTrue(hasattr(log, "error"))


class LoggingTestsRestoreStructlogTest(TestCase):
    """Loggers cached on first use keep the processor list they were built with."""

    def test_app_structlog_config_survives_the_logging_tests(self) -> None:
        before = structlog.get_config()
        root = logging.getLogger()
        handlers, level = list(root.handlers), root.level
        result = unittest.TestResult()
        ConfigureLoggingTest("test_configure_logging_sets_debug_level").run(result)
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
        self.assertIs(structlog.get_config()["processors"], before["processors"])
        self.assertEqual(root.handlers, handlers)
        self.assertEqual(root.level, level)

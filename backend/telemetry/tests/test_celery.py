"""Tests for Celery telemetry base task."""

from unittest import TestCase, mock

import structlog

from telemetry.celery import TelemetryTask


class MockRequest:
    """Mock Celery request object."""

    id = "task-123"


class TelemetryTaskTest(TestCase):
    """Tests for TelemetryTask."""

    def setUp(self):
        """Reset structlog state."""
        structlog.contextvars.clear_contextvars()

    def tearDown(self):
        """Clean up."""
        structlog.contextvars.clear_contextvars()

    def test_binds_task_context(self):
        """Task binds task.id and task.name to context."""
        task = TelemetryTask()
        task.name = "test_task"

        bound_context = {}

        def capture_context():
            ctx = structlog.contextvars.get_contextvars()
            bound_context.update(ctx)
            return "result"

        with mock.patch.object(
            TelemetryTask, "request", new_callable=mock.PropertyMock
        ) as mock_request:
            mock_request.return_value = MockRequest()
            with mock.patch.object(task, "run", capture_context):
                task()

        self.assertEqual(bound_context.get("task.id"), "task-123")
        self.assertEqual(bound_context.get("task.name"), "test_task")

    def test_accepts_propagated_request_id(self):
        """Task accepts _request_id from kwargs."""
        task = TelemetryTask()
        task.name = "test_task"

        bound_context = {}

        def capture_context():
            ctx = structlog.contextvars.get_contextvars()
            bound_context.update(ctx)
            return "result"

        with mock.patch.object(
            TelemetryTask, "request", new_callable=mock.PropertyMock
        ) as mock_request:
            mock_request.return_value = MockRequest()
            with mock.patch.object(task, "run", capture_context):
                task(_request_id="propagated-123")

        self.assertEqual(bound_context.get("request.id"), "propagated-123")

    def test_accepts_propagated_user_id(self):
        """Task accepts _user_id from kwargs."""
        task = TelemetryTask()
        task.name = "test_task"

        bound_context = {}

        def capture_context():
            ctx = structlog.contextvars.get_contextvars()
            bound_context.update(ctx)
            return "result"

        with mock.patch.object(
            TelemetryTask, "request", new_callable=mock.PropertyMock
        ) as mock_request:
            mock_request.return_value = MockRequest()
            with mock.patch.object(task, "run", capture_context):
                task(_user_id=42)

        self.assertEqual(bound_context.get("user.id"), 42)

    def test_clears_context_after_task(self):
        """Task clears context after completion."""
        task = TelemetryTask()
        task.name = "test_task"

        with mock.patch.object(
            TelemetryTask, "request", new_callable=mock.PropertyMock
        ) as mock_request:
            mock_request.return_value = MockRequest()
            with mock.patch.object(task, "run", return_value="result"):
                task()

        ctx = structlog.contextvars.get_contextvars()
        self.assertNotIn("task.id", ctx)

    def test_clears_context_on_error(self):
        """Task clears context even on error."""
        task = TelemetryTask()
        task.name = "test_task"

        def raise_error():
            raise ValueError("test error")

        with mock.patch.object(
            TelemetryTask, "request", new_callable=mock.PropertyMock
        ) as mock_request:
            mock_request.return_value = MockRequest()
            with mock.patch.object(task, "run", raise_error):
                with self.assertRaises(ValueError):
                    task()

        ctx = structlog.contextvars.get_contextvars()
        self.assertNotIn("task.id", ctx)

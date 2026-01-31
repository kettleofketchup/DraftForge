"""Celery telemetry base task with context binding."""

import uuid
from typing import Any, Optional

import structlog
from celery import Task

from telemetry.logging import get_logger

log = get_logger(__name__)


class TelemetryTask(Task):
    """
    Celery base task that binds telemetry context.

    Usage:
        @app.task(base=TelemetryTask)
        def my_task(arg1, arg2):
            log.info("doing work")
            return result

    Context Propagation:
        When calling the task, you can propagate context from a request:

        my_task.delay(
            arg1,
            arg2,
            _request_id=structlog.contextvars.get_contextvars().get("request.id"),
            _user_id=request.user.pk,
        )

    Bound Context:
        - task.id: Celery task ID
        - task.name: Task function name
        - request.id: Propagated or generated request ID
        - user.id: Propagated user ID (if provided)
    """

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute task with telemetry context."""
        # Extract telemetry kwargs (pop so they don't go to task)
        request_id = kwargs.pop("_request_id", None) or str(uuid.uuid4())
        user_id = kwargs.pop("_user_id", None)

        # Build context
        context: dict[str, Any] = {
            "task.id": self.request.id,
            "task.name": self.name,
            "request.id": request_id,
        }
        if user_id is not None:
            context["user.id"] = user_id

        # Bind context
        structlog.contextvars.bind_contextvars(**context)

        log.info("task_started")

        try:
            result = self.run(*args, **kwargs)
            log.info("task_completed")
            return result
        except Exception as e:
            log.error("task_failed", error=str(e), exc_info=True)
            raise
        finally:
            structlog.contextvars.clear_contextvars()

"""Async-capable variant of the OpenTelemetry Django middleware.

Upstream ``_DjangoMiddleware`` (0.62b0) is sync-only and DjangoInstrumentor puts it
first in MIDDLEWARE, so under ASGI every request would run the whole chain through
sync_to_async -> async_to_sync. process_request/process_response do no I/O, so they
run directly on the event loop here.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.http import HttpRequest, HttpResponse
from opentelemetry.instrumentation.django.middleware.otel_middleware import (
    _DjangoMiddleware,
)

OTEL_MIDDLEWARE_PATH = "telemetry.otel_django.AsyncCapableDjangoMiddleware"


class AsyncCapableDjangoMiddleware(_DjangoMiddleware):
    sync_capable = True
    async_capable = True

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse]
        | Callable[[HttpRequest], Awaitable[HttpResponse]],
    ) -> None:
        super().__init__(get_response)
        self.is_async = iscoroutinefunction(get_response)
        if self.is_async:
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest) -> Any:
        if self.is_async:
            return self.__acall__(request)
        return super().__call__(request)

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        self.process_request(request)
        response = await self.get_response(request)
        return self.process_response(request, response)

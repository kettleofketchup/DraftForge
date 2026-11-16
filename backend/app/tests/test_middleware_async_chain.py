"""The ASGI middleware chain must not hop sync_to_async -> async_to_sync per request.

A sync-only middleware forces Django to run the inner chain through async_to_sync from
a worker thread; a cancelled request then parks that thread on the event loop (the
0.14.1 prod freeze). Every MIDDLEWARE entry is async capable, so the chain built by
ASGIHandler has no adapter at all.
"""

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest import mock

import structlog
from asgiref.sync import iscoroutinefunction
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.handlers import base
from django.core.handlers.base import BaseHandler
from django.db import connection
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import path
from opentelemetry.instrumentation.django import DjangoInstrumentor

from app.middleware import (
    CSRF_COOKIE_NAME_HEADER,
    AsyncSocialAuthExceptionMiddleware,
    AsyncWhiteNoiseMiddleware,
    CsrfCookieNameHeaderMiddleware,
)
from telemetry.otel_django import OTEL_MIDDLEWARE_PATH, AsyncCapableDjangoMiddleware

_seen: dict[str, Any] = {}


def _query_view(request: HttpRequest) -> HttpResponse:
    _seen["context"] = structlog.contextvars.get_contextvars()
    # Raw SQL bypasses cacheops, so it always reaches the DB.
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.execute("SELECT 2")
    return HttpResponse("ok")


urlpatterns = [path("api/chain-probe/", _query_view)]


class SyncOnlyMiddleware:
    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)


@contextmanager
def _adapter_spy() -> Iterator[mock.MagicMock]:
    with mock.patch.object(
        base, "async_to_sync", wraps=base.async_to_sync
    ) as async_to_sync_spy:
        yield async_to_sync_spy


@override_settings(DEBUG=True)
class MiddlewareChainAdapterTest(SimpleTestCase):
    def _assert_no_chain_adapter(self, is_async: bool) -> None:
        with (
            _adapter_spy() as async_to_sync_spy,
            self.assertNoLogs("django.request", "DEBUG"),
        ):
            BaseHandler().load_middleware(is_async=is_async)
        async_to_sync_spy.assert_not_called()

    def test_asgi_chain_has_no_adapter(self) -> None:
        self._assert_no_chain_adapter(is_async=True)

    def test_wsgi_chain_has_no_adapter(self) -> None:
        self._assert_no_chain_adapter(is_async=False)

    def test_asgi_chain_with_otel_middleware_has_no_adapter(self) -> None:
        with override_settings(MIDDLEWARE=[OTEL_MIDDLEWARE_PATH, *settings.MIDDLEWARE]):
            self._assert_no_chain_adapter(is_async=True)

    def test_spy_detects_a_sync_only_middleware(self) -> None:
        sync_only = f"{__name__}.SyncOnlyMiddleware"
        with override_settings(MIDDLEWARE=[*settings.MIDDLEWARE, sync_only]):
            with (
                _adapter_spy() as async_to_sync_spy,
                self.assertLogs("django.request", "DEBUG") as logs,
            ):
                BaseHandler().load_middleware(is_async=True)
        async_to_sync_spy.assert_called()
        self.assertTrue(
            any("Asynchronous handler adapted for middleware" in m for m in logs.output)
        )

    def test_instrumentor_still_exposes_middleware_path_override(self) -> None:
        # telemetry.tracing swaps the inserted middleware through this attribute.
        self.assertTrue(hasattr(DjangoInstrumentor, "_opentelemetry_middleware"))


@override_settings(ROOT_URLCONF=__name__)
class MiddlewareChainRequestTest(TestCase):
    def setUp(self) -> None:
        _seen.clear()
        self.user = get_user_model().objects.create_user(
            username="chain_probe_user", password="x"
        )

    def _assert_request_telemetry(
        self,
        response: HttpResponse,
        telemetry_log: mock.MagicMock,
        db_log: mock.MagicMock,
    ) -> None:
        self.assertEqual(response.status_code, 200)
        self.assertIn("X-Request-ID", response)
        self.assertEqual(response[CSRF_COOKIE_NAME_HEADER], settings.CSRF_COOKIE_NAME)

        self.assertEqual(_seen["context"]["user.id"], self.user.pk)
        self.assertEqual(_seen["context"]["request.id"], response["X-Request-ID"])

        completed = telemetry_log.info.call_args
        self.assertEqual(completed[0][0], "request_completed")
        self.assertEqual(completed[1]["http.status_code"], 200)
        self.assertEqual(completed[1]["http.route"], "/api/chain-probe/")

        stats = [c for c in db_log.info.call_args_list if c[0][0] == "db_query_stats"]
        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0][1]["db.query_count"], 2)
        self.assertFalse(connection.force_debug_cursor)

    def test_sync_client_request(self) -> None:
        self.client.force_login(self.user)
        with (
            mock.patch("telemetry.middleware.log") as telemetry_log,
            mock.patch("telemetry.db.log") as db_log,
        ):
            response = self.client.get("/api/chain-probe/")
        self._assert_request_telemetry(response, telemetry_log, db_log)

    async def test_async_client_request(self) -> None:
        await self.async_client.aforce_login(self.user)
        with (
            mock.patch("telemetry.middleware.log") as telemetry_log,
            mock.patch("telemetry.db.log") as db_log,
        ):
            response = await self.async_client.get("/api/chain-probe/")
        self._assert_request_telemetry(response, telemetry_log, db_log)


async def _async_ok(request: HttpRequest) -> HttpResponse:
    return HttpResponse("view")


class AsyncCapableShimTest(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_shims_mark_async_when_chain_is_async(self) -> None:
        for cls in (
            CsrfCookieNameHeaderMiddleware,
            AsyncSocialAuthExceptionMiddleware,
            AsyncWhiteNoiseMiddleware,
            AsyncCapableDjangoMiddleware,
        ):
            with self.subTest(cls=cls.__name__):
                self.assertTrue(cls.sync_capable)
                self.assertTrue(cls.async_capable)
                self.assertTrue(iscoroutinefunction(cls(_async_ok)))
                self.assertFalse(iscoroutinefunction(cls(lambda r: HttpResponse())))

    async def test_csrf_cookie_name_header_async(self) -> None:
        response = await CsrfCookieNameHeaderMiddleware(_async_ok)(
            self.factory.get("/api/anything/")
        )
        self.assertEqual(response[CSRF_COOKIE_NAME_HEADER], settings.CSRF_COOKIE_NAME)

    async def test_otel_middleware_async_wraps_request(self) -> None:
        middleware = AsyncCapableDjangoMiddleware(_async_ok)
        request = self.factory.get("/api/anything/")
        with (
            mock.patch.object(middleware, "process_request") as process_request,
            mock.patch.object(
                middleware, "process_response", side_effect=lambda req, resp: resp
            ) as process_response,
        ):
            response = await middleware(request)
        process_request.assert_called_once_with(request)
        process_response.assert_called_once()
        self.assertEqual(response.content, b"view")

    async def test_whitenoise_async_serves_static_and_passes_through(self) -> None:
        static_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, static_root)
        with open(f"{static_root}/probe.txt", "w") as f:
            f.write("static-body")
        fake_settings = SimpleNamespace(
            DEBUG=False,
            STATIC_URL="/static/",
            STATIC_ROOT=static_root,
            FORCE_SCRIPT_NAME=None,
        )
        middleware = AsyncWhiteNoiseMiddleware(_async_ok, settings=fake_settings)

        static = await middleware(self.factory.get("/static/probe.txt"))
        self.assertEqual(static.status_code, 200)
        self.assertEqual(b"".join(static.streaming_content), b"static-body")
        static.close()

        passthrough = await middleware(self.factory.get("/api/anything/"))
        self.assertEqual(passthrough.content, b"view")

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from app.middleware import CSRF_COOKIE_NAME_HEADER, CsrfCookieNameHeaderMiddleware


def _ok(request: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")


class CsrfCookieNameHeaderTests(SimpleTestCase):
    def _get(self) -> HttpResponse:
        return CsrfCookieNameHeaderMiddleware(_ok)(RequestFactory().get("/api/anything/"))

    def test_installed(self) -> None:
        self.assertIn("app.middleware.CsrfCookieNameHeaderMiddleware", settings.MIDDLEWARE)

    @override_settings(CSRF_COOKIE_NAME="csrftoken")
    def test_header_carries_default_cookie_name(self) -> None:
        self.assertEqual(self._get()[CSRF_COOKIE_NAME_HEADER], "csrftoken")

    @override_settings(CSRF_COOKIE_NAME="csrftoken-s4")
    def test_header_carries_slot_cookie_name(self) -> None:
        self.assertEqual(self._get()[CSRF_COOKIE_NAME_HEADER], "csrftoken-s4")

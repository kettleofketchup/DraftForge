from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

CSRF_COOKIE_NAME_HEADER = "X-CSRF-Cookie-Name"


class CsrfCookieNameHeaderMiddleware:
    """Tell the frontend which cookie holds the CSRF token, so a frontend built with a different name can't drift."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response[CSRF_COOKIE_NAME_HEADER] = settings.CSRF_COOKIE_NAME
        return response

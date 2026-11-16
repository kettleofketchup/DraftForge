from collections.abc import Awaitable, Callable
from typing import Any

from asgiref.sync import iscoroutinefunction, markcoroutinefunction, sync_to_async
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from social_django.middleware import SocialAuthExceptionMiddleware
from whitenoise.middleware import WhiteNoiseMiddleware

CSRF_COOKIE_NAME_HEADER = "X-CSRF-Cookie-Name"

GetResponse = (
    Callable[[HttpRequest], HttpResponse]
    | Callable[[HttpRequest], Awaitable[HttpResponse]]
)


class CsrfCookieNameHeaderMiddleware:
    """Tell the frontend which cookie holds the CSRF token, so a frontend built with a different name can't drift."""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response
        self.is_async = iscoroutinefunction(get_response)
        if self.is_async:
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest) -> Any:
        if self.is_async:
            return self.__acall__(request)
        response = self.get_response(request)
        response[CSRF_COOKIE_NAME_HEADER] = settings.CSRF_COOKIE_NAME
        return response

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        response = await self.get_response(request)
        response[CSRF_COOKIE_NAME_HEADER] = settings.CSRF_COOKIE_NAME
        return response


class AsyncWhiteNoiseMiddleware(WhiteNoiseMiddleware):
    """WhiteNoiseMiddleware (sync-only upstream) made async capable."""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response: GetResponse, settings: Any = settings) -> None:
        super().__init__(get_response, settings)
        self.is_async = iscoroutinefunction(get_response)
        if self.is_async:
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest) -> Any:
        if self.is_async:
            return self.__acall__(request)
        return super().__call__(request)

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        if self.autorefresh:
            static_file = await sync_to_async(self.find_file, thread_sensitive=False)(
                request.path_info
            )
        else:
            static_file = self.files.get(request.path_info)
        if static_file is not None:
            return await sync_to_async(self.serve, thread_sensitive=False)(
                static_file, request
            )
        return await self.get_response(request)


class AsyncSocialAuthExceptionMiddleware(SocialAuthExceptionMiddleware):
    """SocialAuthExceptionMiddleware (sync-only upstream) made async capable; its process_exception is unchanged."""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response: GetResponse) -> None:
        super().__init__(get_response)
        self.is_async = iscoroutinefunction(get_response)
        if self.is_async:
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest) -> Any:
        if self.is_async:
            return self.__acall__(request)
        return super().__call__(request)

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        return await self.get_response(request)

from collections.abc import Callable
from functools import wraps
from typing import Any

from django.core.files.uploadhandler import FileUploadHandler, StopUpload
from django.http import HttpRequest, HttpResponse, JsonResponse

from org.mmr_requests.screenshots import MAX_BYTES
from telemetry.logging import get_logger

log = get_logger(__name__)

MAX_BODY_BYTES = 9 * 1024 * 1024
HANDLER_ATTR = "mmr_upload_guard"


class MaxSizeUploadHandler(FileUploadHandler):
    def __init__(self, request: HttpRequest | None = None) -> None:
        super().__init__(request)
        self.tripped = False

    def receive_data_chunk(self, raw_data: bytes, start: int) -> bytes:
        if start + len(raw_data) > MAX_BYTES:
            self.tripped = True
            raise StopUpload(connection_reset=True)
        return raw_data

    def file_complete(self, file_size: int) -> None:
        return None


def _content_length(request: HttpRequest) -> int:
    try:
        return int(request.META.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        return 0


def upload_tripped(request: HttpRequest) -> bool:
    handler = getattr(request, HANDLER_ATTR, None)
    return bool(handler and handler.tripped)


def guard_upload(
    view_func: Callable[..., HttpResponse],
) -> Callable[..., HttpResponse]:
    @wraps(view_func)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        length = _content_length(request)
        if length > MAX_BODY_BYTES:
            log.warning(
                "mmr_upload_body_too_large",
                system="org",
                subsystem="mmr_requests",
                content_length=length,
                path=request.path,
            )
            return JsonResponse({"error": "too_large"}, status=413)
        handler = MaxSizeUploadHandler(request)
        request.upload_handlers.insert(0, handler)
        setattr(request, HANDLER_ATTR, handler)
        return view_func(request, *args, **kwargs)

    wrapped.csrf_exempt = getattr(view_func, "csrf_exempt", False)  # type: ignore[attr-defined]
    return wrapped

import shutil
import threading
import warnings
from io import BytesIO
from pathlib import Path
from typing import Literal

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from PIL import Image, ImageOps, UnidentifiedImageError

from telemetry.logging import get_logger

log = get_logger(__name__)

ALLOWED_FORMATS = {"PNG": "png", "JPEG": "jpeg", "WEBP": "webp"}
MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 25_000_000
MAX_EDGE = 8192
OUTPUT_MAX_EDGE = 3840
MIN_FREE_BYTES = 512 * 1024 * 1024
SANITIZE_ACQUIRE_TIMEOUT = 2.0
_SANITIZE_SLOTS = threading.BoundedSemaphore(2)

Image.MAX_IMAGE_PIXELS = MAX_PIXELS

RejectionCode = Literal["unsupported_type", "too_large", "invalid_image"]


class ScreenshotRejected(Exception):
    def __init__(self, code: RejectionCode) -> None:
        super().__init__(code)
        self.code: RejectionCode = code


class StorageFull(Exception):
    pass


class SanitizerBusy(Exception):
    pass


def _check_free_space() -> None:
    root = Path(settings.MEDIA_ROOT)
    try:
        root.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(root).free
    except OSError as exc:
        log.error(
            "mmr_screenshot_storage_unavailable",
            system="org",
            subsystem="mmr_requests",
            error=str(exc),
        )
        raise StorageFull from exc
    if free < MIN_FREE_BYTES:
        log.error(
            "mmr_screenshot_storage_full",
            system="org",
            subsystem="mmr_requests",
            free_bytes=free,
        )
        raise StorageFull


def _read_header(upload: UploadedFile) -> str:
    upload.seek(0)
    try:
        with warnings.catch_warnings(), Image.open(upload) as img:
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            fmt = img.format
            width, height = img.size
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        OSError,
        ValueError,
        SyntaxError,
    ) as exc:
        raise ScreenshotRejected("invalid_image") from exc
    if fmt not in ALLOWED_FORMATS:
        raise ScreenshotRejected("unsupported_type")
    if max(width, height) > MAX_EDGE or width * height > MAX_PIXELS:
        raise ScreenshotRejected("invalid_image")
    return fmt


def _verify(upload: UploadedFile) -> None:
    upload.seek(0)
    try:
        with Image.open(upload) as img:
            img.verify()
    except Exception as exc:
        raise ScreenshotRejected("invalid_image") from exc


def _reencode(upload: UploadedFile, fmt: str) -> bytes:
    upload.seek(0)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload) as src:
                if src.format != fmt:
                    raise ScreenshotRejected("invalid_image")
                src.load()
                img = ImageOps.exif_transpose(src)
                img.thumbnail(
                    (OUTPUT_MAX_EDGE, OUTPUT_MAX_EDGE), Image.Resampling.LANCZOS
                )
                if fmt == "JPEG":
                    img = img.convert("RGB")
                elif img.mode not in ("RGB", "RGBA"):
                    img = img.convert(
                        "RGBA"
                        if "A" in img.getbands() or "transparency" in img.info
                        else "RGB"
                    )
                img.info = {}
                out = BytesIO()
                if fmt == "PNG":
                    img.save(out, format="PNG")
                else:
                    img.save(out, format=fmt, quality=85)
                return out.getvalue()
    except ScreenshotRejected:
        raise
    except Exception as exc:
        raise ScreenshotRejected("invalid_image") from exc


def sanitize_screenshot(upload: UploadedFile) -> tuple[ContentFile, str]:
    if upload.size is None or upload.size > MAX_BYTES:
        raise ScreenshotRejected("too_large")
    _check_free_space()
    fmt = _read_header(upload)
    _verify(upload)
    if not _SANITIZE_SLOTS.acquire(timeout=SANITIZE_ACQUIRE_TIMEOUT):
        log.warning(
            "mmr_screenshot_sanitizer_busy", system="org", subsystem="mmr_requests"
        )
        raise SanitizerBusy
    try:
        data = _reencode(upload, fmt)
    finally:
        _SANITIZE_SLOTS.release()
    if len(data) > MAX_BYTES:
        raise ScreenshotRejected("too_large")
    ext = ALLOWED_FORMATS[fmt]
    return ContentFile(data, name=f"upload.{ext}"), f"image/{ext}"

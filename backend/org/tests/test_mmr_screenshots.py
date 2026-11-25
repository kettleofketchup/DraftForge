import shutil
import struct
import tempfile
import zlib
from collections import namedtuple
from io import BytesIO
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from PIL import Image

from org.mmr_requests import screenshots
from org.mmr_requests.screenshots import (
    MAX_BYTES,
    MIN_FREE_BYTES,
    OUTPUT_MAX_EDGE,
    SanitizerBusy,
    ScreenshotRejected,
    StorageFull,
    sanitize_screenshot,
)
from org.mmr_requests.storage import PrivateFileSystemStorage, private_media_storage

DiskUsage = namedtuple("DiskUsage", ["total", "used", "free"])


def _image_bytes(
    fmt: str, size: tuple[int, int] = (40, 20), mode: str = "RGB", **save_kwargs: object
) -> bytes:
    buf = BytesIO()
    Image.new(mode, size, color=0 if mode == "1" else (10, 120, 200)).save(
        buf, format=fmt, **save_kwargs
    )
    return buf.getvalue()


def _upload(
    data: bytes, name: str = "shot.png", content_type: str = "image/png"
) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, data, content_type=content_type)


def _png_header_only(width: int, height: int) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 1, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b"\x00"))
        + chunk(b"IEND", b"")
    )


def _fail_load(*args: object, **kwargs: object) -> None:
    raise AssertionError("Image.load() must not run for an oversized header")


class SanitizeScreenshotTests(SimpleTestCase):
    def setUp(self) -> None:
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, True)
        override = override_settings(MEDIA_ROOT=self.media_root)
        override.enable()
        self.addCleanup(override.disable)

    def _reopen(self, data: bytes) -> Image.Image:
        return Image.open(BytesIO(data))

    def test_png_jpeg_webp_accepted_and_reencoded(self) -> None:
        for fmt, ext in (("PNG", "png"), ("JPEG", "jpeg"), ("WEBP", "webp")):
            with self.subTest(fmt=fmt):
                out, content_type = sanitize_screenshot(
                    _upload(_image_bytes(fmt), name=f"x.{ext}")
                )
                self.assertEqual(content_type, f"image/{ext}")
                self.assertEqual(out.name, f"upload.{ext}")
                self.assertEqual(self._reopen(out.read()).format, fmt)

    def test_exif_gps_stripped(self) -> None:
        exif = Image.Exif()
        exif[0x8825] = {2: (40.0, 26.0, 46.0), 1: "N"}
        exif[0x010F] = "PhoneMaker"
        data = _image_bytes("JPEG", exif=exif.tobytes())
        self.assertIn("exif", Image.open(BytesIO(data)).info)
        out, _ = sanitize_screenshot(
            _upload(data, name="x.jpg", content_type="image/jpeg")
        )
        img = self._reopen(out.read())
        self.assertEqual(len(img.getexif()), 0)
        self.assertNotIn("exif", img.info)

    def test_exif_orientation_applied(self) -> None:
        exif = Image.Exif()
        exif[0x0112] = 6
        data = _image_bytes("JPEG", size=(100, 50), exif=exif.tobytes())
        out, _ = sanitize_screenshot(
            _upload(data, name="x.jpg", content_type="image/jpeg")
        )
        img = self._reopen(out.read())
        self.assertEqual(img.size, (50, 100))
        self.assertEqual(len(img.getexif()), 0)

    def test_gif_svg_text_rejected(self) -> None:
        cases = [
            (_image_bytes("GIF", mode="P"), "x.gif", {"unsupported_type"}),
            (
                b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                "x.svg",
                {"invalid_image", "unsupported_type"},
            ),
            (b"hello", "x.png", {"invalid_image"}),
        ]
        for data, name, codes in cases:
            with self.subTest(name=name):
                with self.assertRaises(ScreenshotRejected) as ctx:
                    sanitize_screenshot(_upload(data, name=name))
                self.assertIn(ctx.exception.code, codes)

    def test_oversize_rejected_before_decode(self) -> None:
        upload = _upload(b"\x00" * (MAX_BYTES + 1))
        with mock.patch.object(screenshots.Image, "open") as opener:
            with self.assertRaises(ScreenshotRejected) as ctx:
                sanitize_screenshot(upload)
        opener.assert_not_called()
        self.assertEqual(ctx.exception.code, "too_large")

    def test_polyglot_trailing_bytes_removed(self) -> None:
        data = _image_bytes("PNG") + b"<script>alert(1)</script>PK\x03\x04"
        out, _ = sanitize_screenshot(_upload(data))
        body = out.read()
        self.assertNotIn(b"<script>", body)
        self.assertNotIn(b"PK\x03\x04", body)
        self.assertEqual(self._reopen(body).format, "PNG")

    def test_edge_over_8192_rejected(self) -> None:
        data = _image_bytes("PNG", size=(8193, 1), mode="1")
        with mock.patch.object(Image.Image, "load", _fail_load):
            with self.assertRaises(ScreenshotRejected) as ctx:
                sanitize_screenshot(_upload(data))
        self.assertEqual(ctx.exception.code, "invalid_image")

    def test_pixels_over_25mp_rejected_before_load(self) -> None:
        data = _png_header_only(6000, 5000)
        with mock.patch.object(Image.Image, "load", _fail_load):
            with self.assertRaises(ScreenshotRejected) as ctx:
                sanitize_screenshot(_upload(data))
        self.assertEqual(ctx.exception.code, "invalid_image")

    def test_sanitize_busy_raises(self) -> None:
        data = _image_bytes("PNG")
        held = 0
        try:
            while screenshots._SANITIZE_SLOTS.acquire(blocking=False):
                held += 1
            self.assertEqual(held, 2)
            with mock.patch.object(screenshots, "SANITIZE_ACQUIRE_TIMEOUT", 0.01):
                with self.assertRaises(SanitizerBusy):
                    sanitize_screenshot(_upload(data))
        finally:
            for _ in range(held):
                screenshots._SANITIZE_SLOTS.release()

    def test_downscale_above_3840(self) -> None:
        out, _ = sanitize_screenshot(_upload(_image_bytes("PNG", size=(4000, 100))))
        self.assertEqual(self._reopen(out.read()).size[0], OUTPUT_MAX_EDGE)

    def test_storage_full(self) -> None:
        usage = DiskUsage(total=10 * MIN_FREE_BYTES, used=0, free=MIN_FREE_BYTES - 1)
        with mock.patch.object(screenshots.shutil, "disk_usage", return_value=usage):
            with self.assertRaises(StorageFull):
                sanitize_screenshot(_upload(_image_bytes("PNG")))


class PrivateStorageTests(SimpleTestCase):
    def test_private_storage_url_raises(self) -> None:
        with self.assertRaises(NotImplementedError):
            private_media_storage().url("x")

    def test_private_storage_follows_media_root_override(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            with override_settings(MEDIA_ROOT=root):
                storage = private_media_storage()
                self.assertIsInstance(storage, PrivateFileSystemStorage)
                self.assertEqual(storage.location, root)
                self.assertEqual(storage.file_permissions_mode, 0o640)
                self.assertEqual(storage.directory_permissions_mode, 0o750)

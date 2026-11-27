import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, ClassVar

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image

from league.models import LeagueUser
from org.mmr import LEAGUE_GAME
from org.mmr_requests.screenshots import sanitize_screenshot
from org.models import MmrChangeRequest, OrgUser

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


class MmrRequestTestMixin:
    media_root: ClassVar[str]
    _media_override: ClassVar[override_settings]

    @classmethod
    def setUpClass(cls) -> None:
        cls.media_root = tempfile.mkdtemp(prefix="mmr-media-")
        cls._media_override = override_settings(
            MEDIA_ROOT=cls.media_root, CACHES=LOCMEM_CACHES
        )
        cls._media_override.enable()
        # Class cleanups unwind LIFO, after Django's own class-level overrides.
        cls.addClassCleanup(shutil.rmtree, cls.media_root, ignore_errors=True)  # type: ignore[attr-defined]
        cls.addClassCleanup(cls._media_override.disable)  # type: ignore[attr-defined]
        super().setUpClass()  # type: ignore[misc]

    def setUp(self) -> None:
        super().setUp()  # type: ignore[misc]
        cache.clear()
        shutil.rmtree(self.media_root, ignore_errors=True)
        Path(self.media_root).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def png_upload(name: str = "s.png") -> SimpleUploadedFile:
        buf = BytesIO()
        Image.new("RGB", (40, 20), color=(10, 120, 200)).save(buf, format="PNG")
        return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")

    def media_files(self) -> list[Path]:
        return sorted(p for p in Path(self.media_root).rglob("*") if p.is_file())

    def make_request(
        self,
        *,
        org_user: OrgUser,
        league_user: LeagueUser | None = None,
        with_screenshot: bool = True,
        **kwargs: Any,
    ) -> MmrChangeRequest:
        is_league = league_user is not None
        fields: dict[str, Any] = {
            "requester": org_user.user,
            "subject_user": org_user.user,
            "organization": org_user.organization,
            "org_user": org_user,
            "league": league_user.league if league_user else None,
            "league_user": league_user,
            "target": (
                MmrChangeRequest.Target.LEAGUE
                if is_league
                else MmrChangeRequest.Target.ORG
            ),
            "game_type": LEAGUE_GAME,
            "requested_mmr": 4000,
            "previous_mmr": 3000,
        }
        fields.update(kwargs)
        req = MmrChangeRequest(**fields)
        if with_screenshot:
            content, content_type = sanitize_screenshot(self.png_upload())
            req.screenshot_content_type = content_type
            req.screenshot.save(content.name, content, save=False)
        req.save()
        return req

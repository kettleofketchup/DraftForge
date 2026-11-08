import json
import os
import subprocess
import sys
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase

from backend.env_utils import env_list


class EnvListTests(SimpleTestCase):
    def test_unset(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(env_list("X"), [])

    def test_split_strip_drop_empty(self) -> None:
        with mock.patch.dict(os.environ, {"X": " https://a:1 , ,https://b "}):
            self.assertEqual(env_list("X"), ["https://a:1", "https://b"])

    def test_settings_base_list_intact(self) -> None:
        self.assertIn("https://localhost", settings.CSRF_TRUSTED_ORIGINS)

    def _origins(self, extra: str | None) -> tuple[list[str], list[str]]:
        env = {k: v for k, v in os.environ.items() if k != "DF_EXTRA_CSRF_ORIGINS"}
        if extra is not None:
            env["DF_EXTRA_CSRF_ORIGINS"] = extra
        env["DJANGO_SETTINGS_MODULE"] = "backend.settings"
        code = (
            "import django, json; django.setup(); from django.conf import settings as s; "
            "print(json.dumps([list(s.CSRF_TRUSTED_ORIGINS), list(s.CORS_ORIGIN_WHITELIST)]))"
        )
        r = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            cwd=settings.BASE_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        csrf, cors = json.loads(r.stdout.strip().splitlines()[-1])
        return csrf, cors

    def test_extra_origin_reaches_both_lists(self) -> None:
        csrf, cors = self._origins("https://localhost:13443")
        self.assertIn("https://localhost:13443", csrf)
        self.assertIn("https://localhost:13443", cors)

    def test_extra_origin_absent_when_unset(self) -> None:
        csrf, cors = self._origins(None)
        self.assertNotIn("https://localhost:13443", csrf)
        self.assertNotIn("https://localhost:13443", cors)

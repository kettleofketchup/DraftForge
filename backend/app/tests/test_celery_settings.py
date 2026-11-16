"""The celery worker and beat boot config.celery_light under config.settings_celery."""

import json
import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[2]


class CelerySettingsBootTest(SimpleTestCase):
    def test_celery_light_imports_under_settings_celery(self) -> None:
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings_celery"}
        result = subprocess.run(
            [sys.executable, "-c", "import config.celery_light"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])

    def test_settings_modules_agree_on_discord_api(self) -> None:
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings_celery"}
        code = (
            "import json, config.settings_celery as c; "
            "print(json.dumps([c.DISCORD_API_BASE_URL, c.DISCORD_GUILD_ID]))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        celery_vals = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(celery_vals, [settings.DISCORD_API_BASE_URL, settings.DISCORD_GUILD_ID])
        self.assertEqual(settings.DISCORD_API_BASE_URL, "https://discord.com/api/v10")

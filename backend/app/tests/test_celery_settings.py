"""The celery worker and beat boot config.celery_light under config.settings_celery."""

import os
import subprocess
import sys
from pathlib import Path

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

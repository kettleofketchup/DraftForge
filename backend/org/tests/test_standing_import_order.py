import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase

ENTRY_POINTS = (
    "org.contributions.services",
    "org.contributions.views",
    "org.promotion.services",
    "org.standing.ledger",
    "org.standing.scoring",
    "org.standing.api",
    "events.services",
    "events.completion",
)


class ImportOrderTest(SimpleTestCase):
    def test_each_entry_point_imports_first(self) -> None:
        env = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": os.environ.get(
                "DJANGO_SETTINGS_MODULE", "backend.settings"
            ),
        }
        for module in ENTRY_POINTS:
            with self.subTest(module=module):
                proc = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        f"import django; django.setup(); import {module}",
                    ],
                    cwd=settings.BASE_DIR,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])

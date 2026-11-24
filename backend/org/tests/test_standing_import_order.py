import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENTRY_POINTS = (
    "org.contributions.services",
    "org.contributions.views",
    "org.contributions.adapter",
    "org.promotion.services",
    "org.standing.ledger",
    "org.standing.scoring",
    "org.standing.api",
    "events.services",
    "events.completion",
    "events.reopen",
    "user.discord_accounts",
    "org.conduct.adapter",
    "org.leadership.adapter",
    "org.leadership.reviews",
    "org.conduct.eligibility",
    "org.conduct.services",
    "events.eligibility.checks.conduct",
    "events.eligibility.store",
    "events.admission",
)
WEB_SETTINGS = "backend.settings"
RESTAMP_ENTRY_POINTS = (
    "events.completion",
    "events.reopen",
    "app.views.internal",
    "backend.urls",
)


class StandingImportOrderTest(SimpleTestCase):
    """Some entry points (the eligibility chain) are first imported by
    django.setup() itself through app.models; setup succeeding covers them."""

    def _import_first(
        self, module: str, then: str = "", settings: str = "config.settings_celery"
    ) -> subprocess.CompletedProcess[str]:
        code = f"import django; django.setup(); import {module}; {then}"
        env = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": settings,
            "DISABLE_CACHE": "true",
        }
        return subprocess.run(
            [sys.executable, "-c", code],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_each_entry_point_imports_first(self) -> None:
        for module in ENTRY_POINTS:
            with self.subTest(module=module):
                proc = self._import_first(module)
                self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_entry_points_register_restamp(self) -> None:
        for module in RESTAMP_ENTRY_POINTS:
            with self.subTest(module=module):
                proc = self._import_first(
                    module,
                    "from org.standing import restamp; "
                    "assert restamp.registered(), 'restamp not registered'",
                    settings=WEB_SETTINGS,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)

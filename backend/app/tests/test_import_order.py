"""app.serializers must load without pulling team_management into a cycle (#544)."""

import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[2]


class ImportOrderTests(SimpleTestCase):
    def _import_first(self, module: str) -> subprocess.CompletedProcess[str]:
        code = f"import django; django.setup(); import {module}"
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "backend.settings"}
        return subprocess.run(
            [sys.executable, "-c", code],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_serializers_first(self) -> None:
        result = self._import_first("app.serializers")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_broadcast_first(self) -> None:
        result = self._import_first("app.broadcast")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_serializers_never_import_team_management(self) -> None:
        source = (BACKEND_DIR / "app" / "serializers.py").read_text()
        self.assertNotIn("team_management", source)

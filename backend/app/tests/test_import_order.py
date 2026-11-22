"""Serializers must load without pulling team_management into a cycle (#544)."""

import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[2]
TOURNAMENT_SERIALIZER_MODULES = tuple(
    f"tournament.serializers.{name}"
    for name in ("users", "team", "draft", "game", "tournament")
)


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

    def test_tournament_serializers_first(self) -> None:
        for module in TOURNAMENT_SERIALIZER_MODULES:
            with self.subTest(module=module):
                result = self._import_first(module)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_broadcast_first(self) -> None:
        result = self._import_first("draft.services.team_broadcast")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_exception_handler_first(self) -> None:
        result = self._import_first("app.exception_handler")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_serializers_never_import_team_management(self) -> None:
        paths = [
            BACKEND_DIR / "app" / "serializers.py",
            *sorted((BACKEND_DIR / "tournament" / "serializers").glob("*.py")),
        ]
        self.assertGreater(len(paths), len(TOURNAMENT_SERIALIZER_MODULES))
        for path in paths:
            with self.subTest(path=path.name):
                self.assertNotIn("team_management", path.read_text())

    def test_tournament_serializers_never_import_functions(self) -> None:
        paths = sorted((BACKEND_DIR / "tournament" / "serializers").glob("*.py"))
        self.assertGreaterEqual(len(paths), len(TOURNAMENT_SERIALIZER_MODULES))
        for path in paths:
            with self.subTest(path=path.name):
                self.assertNotIn("tournament.functions", path.read_text())

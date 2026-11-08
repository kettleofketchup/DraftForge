#!/usr/bin/env python3
"""Tests for scripts/version.py. Needs the project venv (invoke):
`.venv/bin/python -m unittest scripts/test_version.py` from the repo root.
"""

import re
import unittest
from pathlib import Path
from unittest import mock

from invoke.context import MockContext

import paths
from scripts import version

REPO = Path(__file__).resolve().parent.parent
COMPOSE_RE = re.compile(r"docker-compose[\w.-]*\.ya?ml")


def task_sources() -> list[Path]:
    return [
        *sorted((REPO / "scripts").glob("*.py")),
        REPO / "tasks.py",
        REPO / "paths.py",
        REPO / "backend" / "tasks.py",
        *sorted((REPO / "just").rglob("*.just")),
    ]


class ComposeReferencesTest(unittest.TestCase):
    def test_every_referenced_compose_file_exists(self) -> None:
        missing = [
            f"{src.relative_to(REPO)}: {name}"
            for src in task_sources()
            if src.name != "test_version.py"
            for name in COMPOSE_RE.findall(src.read_text())
            if not (paths.DOCKER_PATH / name).exists()
        ]
        self.assertEqual(missing, [])


@mock.patch.object(version, "docker_release_build")
@mock.patch.object(version, "update_env_version")
@mock.patch.object(version, "update_pyproject_version")
class BuildWithVersionTest(unittest.TestCase):
    def test_explicit_version_syncs_files_then_builds_release_images(
        self,
        update_pyproject: mock.MagicMock,
        update_env: mock.MagicMock,
        release_build: mock.MagicMock,
    ) -> None:
        c = MockContext()
        version.build_with_version(c, version="9.9.9")

        update_pyproject.assert_called_once_with("9.9.9")
        self.assertEqual(
            update_env.call_args_list,
            [
                mock.call(paths.PROD_ENV_FILE, "9.9.9"),
                mock.call(paths.RELEASE_ENV_FILE, "9.9.9"),
            ],
        )
        release_build.assert_called_once_with(c)

    def test_default_reads_version_from_release_env_file(
        self,
        update_pyproject: mock.MagicMock,
        update_env: mock.MagicMock,
        release_build: mock.MagicMock,
    ) -> None:
        with mock.patch.object(
            version, "get_version_from_env", return_value="1.2.3"
        ) as from_env:
            version.build_with_version(MockContext())

        from_env.assert_called_once_with(paths.RELEASE_ENV_FILE)
        update_pyproject.assert_called_once_with("1.2.3")
        release_build.assert_called_once()


if __name__ == "__main__":
    unittest.main()

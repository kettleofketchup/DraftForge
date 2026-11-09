#!/usr/bin/env python3
"""Tests for scripts/version.py. Run from the repo root with the project venv:
`.venv/bin/python -m unittest scripts/test_version.py`.
"""

import re
import unittest
from pathlib import Path
from unittest import mock

import paths
from scripts import version

REPO = Path(__file__).resolve().parent.parent
COMPOSE_RE = re.compile(r"docker-compose[\w.-]*\.ya?ml")


def task_sources() -> list[Path]:
    return [
        *sorted((REPO / "scripts").glob("*.py")),
        *sorted((REPO / "scripts").glob("*.sh")),
        REPO / "paths.py",
        REPO / "justfile",
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


@mock.patch.object(version, "update_env_version")
@mock.patch.object(version, "update_pyproject_version")
class SyncTest(unittest.TestCase):
    def test_explicit_version_writes_pyproject_and_env_files(
        self, update_pyproject: mock.MagicMock, update_env: mock.MagicMock
    ) -> None:
        self.assertEqual(version.main(["sync", "--version", "9.9.9"]), 0)

        update_pyproject.assert_called_once_with("9.9.9")
        self.assertEqual(
            update_env.call_args_list,
            [
                mock.call(paths.PROD_ENV_FILE, "9.9.9"),
                mock.call(paths.RELEASE_ENV_FILE, "9.9.9"),
            ],
        )

    def test_default_reads_version_from_release_env_file(
        self, update_pyproject: mock.MagicMock, update_env: mock.MagicMock
    ) -> None:
        with mock.patch.object(
            version, "get_version_from_env", return_value="1.2.3"
        ) as from_env:
            self.assertEqual(version.main(["sync"]), 0)

        from_env.assert_called_once_with(paths.RELEASE_ENV_FILE)
        update_pyproject.assert_called_once_with("1.2.3")


class FromEnvTest(unittest.TestCase):
    def test_defaults_to_the_release_env_file(self) -> None:
        with (
            mock.patch.object(version, "get_version_from_env", return_value="4.5.6") as from_env,
            mock.patch.object(version, "update_pyproject_version") as update_pyproject,
        ):
            self.assertEqual(version.main(["from-env"]), 0)
        from_env.assert_called_once_with(paths.RELEASE_ENV_FILE)
        update_pyproject.assert_called_once_with("4.5.6")


class SetVersionTest(unittest.TestCase):
    def test_no_commit_writes_files_and_tags_locally(self) -> None:
        with (
            mock.patch.object(version, "write_version_files") as write,
            mock.patch.object(version.subprocess, "run") as run,
            mock.patch.object(version.changelog, "release") as release,
        ):
            run.return_value.returncode = 0
            self.assertEqual(version.main(["set", "7.7.7", "--no-commit"]), 0)
        write.assert_called_once_with("7.7.7")
        run.assert_called_once_with(["git", "tag", "7.7.7"], cwd=paths.PROJECT_PATH)
        release.assert_not_called()

    def test_preflight_failure_exits_nonzero_without_writing(self) -> None:
        with (
            mock.patch.object(
                version.changelog,
                "release_preflight",
                side_effect=version.changelog.ChangelogError("main is dirty"),
            ),
            mock.patch.object(version, "write_version_files") as write,
        ):
            self.assertEqual(version.main(["set", "7.7.7"]), 1)
        write.assert_not_called()


if __name__ == "__main__":
    unittest.main()

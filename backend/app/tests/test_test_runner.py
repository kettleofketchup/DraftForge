"""Path-based discovery (bare `manage.py test`) must name modules from backend/.

The image has /app/__init__.py and /app/backend/__init__.py, so unittest walks
the top-level directory up to / and imports `app.backend...`, which fails.
"""

import unittest
from collections.abc import Iterator
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.test.utils import get_runner

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _test_ids(suite: unittest.TestSuite) -> Iterator[str]:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _test_ids(item)
        else:
            yield item.id()


class TestRunnerDiscoveryTests(SimpleTestCase):
    def test_path_label_discovers_importable_module_names(self) -> None:
        runner = get_runner(settings)(verbosity=0, interactive=False)
        suite = runner.build_suite([str(BACKEND_ROOT / "app" / "tests")])
        ids = list(_test_ids(suite))
        self.assertIn(
            "app.tests.test_test_runner.TestRunnerDiscoveryTests."
            "test_path_label_discovers_importable_module_names",
            ids,
        )
        failed = [i for i in ids if i.startswith("unittest.loader._FailedTest")]
        self.assertEqual(failed, [])


class DotaLobbyDefaultsTests(SimpleTestCase):
    """The test stack turns dota_lobby on; unit tests start with it off."""

    def test_lobbies_are_off_whatever_the_environment_says(self) -> None:
        import os

        from config.dota_lobby import DotaLobbyConfig

        self.assertFalse(settings.DOTA_LOBBY_ENABLED)
        self.assertEqual(settings.DOTA_LOBBY_URL, "")
        self.assertEqual(settings.DOTA_LOBBY_API_KEY, "")
        self.assertEqual(settings.DOTA_LOBBY_WEBHOOK_SECRETS, ())
        self.assertEqual([k for k in os.environ if k.startswith("DOTA_LOBBY_")], [])
        self.assertFalse(DotaLobbyConfig.from_env().is_configured)

    def test_runner_restores_the_environment(self) -> None:
        import os
        from unittest import mock

        from backend.test_runner import BackendDiscoverRunner

        runner = BackendDiscoverRunner(verbosity=0, interactive=False)
        with (
            mock.patch.dict(
                os.environ, {"DOTA_LOBBY_ENABLED": "true", "DOTA_LOBBY_URL": "http://x"}
            ),
            mock.patch("django.test.runner.setup_test_environment"),
            mock.patch("django.test.runner.teardown_test_environment"),
        ):
            runner.setup_test_environment()
            self.assertNotIn("DOTA_LOBBY_URL", os.environ)
            self.assertFalse(settings.DOTA_LOBBY_ENABLED)
            runner.teardown_test_environment()
            self.assertEqual(os.environ["DOTA_LOBBY_URL"], "http://x")

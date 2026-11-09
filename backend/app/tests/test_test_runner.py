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

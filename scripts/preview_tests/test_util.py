import os
import unittest
from unittest import mock

from scripts.preview_tests import _util


class RequireTest(unittest.TestCase):
    def test_require_skips_locally(self):
        with mock.patch.dict(os.environ, clear=False):
            os.environ.pop("CI", None)
            with self.assertRaises(unittest.SkipTest) as ctx:
                _util.require(False, "widget")
        self.assertEqual(str(ctx.exception), "MISSING: widget")

    def test_require_fails_in_ci(self):
        with mock.patch.dict(os.environ, {"CI": "true"}):
            with self.assertRaises(AssertionError) as ctx:
                _util.require(False, "widget")
        self.assertIn("MISSING: widget", str(ctx.exception))

    def test_require_exempt_skips_in_ci(self):
        with mock.patch.dict(os.environ, {"CI": "true"}):
            with self.assertRaises(unittest.SkipTest) as ctx:
                _util.require(False, "widget", ci_exempt=True)
        self.assertEqual(str(ctx.exception), "MISSING: widget")

    def test_require_true_is_noop(self):
        with mock.patch.dict(os.environ, {"CI": "true"}):
            self.assertIsNone(_util.require(True, "widget"))


if __name__ == "__main__":
    unittest.main()

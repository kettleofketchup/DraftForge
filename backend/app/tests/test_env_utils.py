"""Unit tests for the env-var helpers in backend.env_utils."""

import os
from unittest import mock

from django.test import SimpleTestCase

from backend.env_utils import env_bool, env_list


class EnvListTests(SimpleTestCase):
    def test_env_list_unset_is_empty(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("X_UNSET", None)
            self.assertEqual(env_list("X_UNSET"), [])

    def test_env_list_splits_trims_drops_empty(self):
        with mock.patch.dict(os.environ, {"X_LIST": " a.example , ,b.example,"}):
            self.assertEqual(env_list("X_LIST"), ["a.example", "b.example"])

    def test_env_list_empty_string_is_empty(self):
        with mock.patch.dict(os.environ, {"X_LIST": ""}):
            self.assertEqual(env_list("X_LIST"), [])


class EnvBoolTests(SimpleTestCase):
    def test_env_bool_truthy_and_default(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("X_BOOL", None)
            self.assertIs(env_bool("X_BOOL"), False)
            self.assertIs(env_bool("X_BOOL", True), True)
        for value in ("1", "true", "TRUE", " yes ", "On"):
            with (
                self.subTest(value=value),
                mock.patch.dict(os.environ, {"X_BOOL": value}),
            ):
                self.assertIs(env_bool("X_BOOL"), True)
        for value in ("0", "false", "no", "off", "", "2"):
            with (
                self.subTest(value=value),
                mock.patch.dict(os.environ, {"X_BOOL": value}),
            ):
                # A set-but-unrecognised value is False even when default=True.
                self.assertIs(env_bool("X_BOOL", True), False)

    def test_settings_reexports_env_bool(self):
        import backend.settings

        self.assertIs(backend.settings.env_bool, env_bool)

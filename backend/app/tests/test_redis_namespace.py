"""Per-process Redis namespace for test runs, empty outside the test runner.

Concurrent `manage.py test` runs share one Redis and number their drafts from 1,
so group names and raw keys collide unless each run gets its own namespace.
"""

import importlib
import os
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from unittest import mock

from django.apps import apps
from django.conf import settings
from django.test import SimpleTestCase, override_settings

import backend.settings
from app.redis_keys import namespaced_key
from app.tasks.herodraft_tick import (
    captain_heartbeat_key,
    conn_count_key,
    tick_lock_key,
)
from app.tests.test_consumers_base import ConcreteDraftConsumer

_MISSING = object()


@contextmanager
def _quiet_reload_env() -> Iterator[None]:
    with (
        mock.patch("dotenv.load_dotenv", lambda *a, **k: False),
        mock.patch("telemetry.config.init_telemetry"),
    ):
        yield


@contextmanager
def _patched_runtime(argv: list[str], with_pytest: bool) -> Iterator[None]:
    saved = sys.modules.get("pytest", _MISSING)
    with (
        mock.patch.dict(os.environ, {"DISABLE_CACHE": "false"}),
        mock.patch.object(sys, "argv", argv),
        _quiet_reload_env(),
    ):
        if with_pytest:
            sys.modules.setdefault("pytest", types.ModuleType("pytest"))
        else:
            sys.modules.pop("pytest", None)
        try:
            yield
        finally:
            if saved is _MISSING:
                sys.modules.pop("pytest", None)
            else:
                sys.modules["pytest"] = saved


def _reload(argv: list[str], *, with_pytest: bool = False) -> types.ModuleType:
    with _patched_runtime(argv, with_pytest):
        backend.settings.is_docker.cache_clear()
        return importlib.reload(backend.settings)


def tearDownModule() -> None:
    with _quiet_reload_env():
        backend.settings.is_docker.cache_clear()
        importlib.reload(backend.settings)


def _layer_config(mod: types.ModuleType) -> dict[str, object]:
    return mod.CHANNEL_LAYERS["default"]["CONFIG"]


class RunningTestsSettingsTests(SimpleTestCase):
    def test_active_settings_flag_this_process_as_a_test_run(self) -> None:
        self.assertTrue(settings.RUNNING_TESTS)
        self.assertIn(str(os.getpid()), settings.REDIS_KEY_NAMESPACE)

    def test_manage_py_test_gets_a_namespace(self) -> None:
        mod = _reload(["manage.py", "test", "app.tests"])
        self.assertTrue(mod.RUNNING_TESTS)
        ns = mod.REDIS_KEY_NAMESPACE
        self.assertTrue(ns.startswith("test-") and ns.endswith(":"), ns)
        self.assertIn(str(os.getpid()), ns)
        self.assertEqual(_layer_config(mod)["prefix"], f"asgi:{ns}")
        self.assertEqual(
            mod.CACHEOPS_PREFIX(None), f"dtx-v{mod._deploy_version()}:{ns}"
        )
        self.assertEqual(mod.CACHES["default"].get("KEY_PREFIX"), ns)

    def test_pytest_gets_a_namespace(self) -> None:
        mod = _reload(["pytest"], with_pytest=True)
        self.assertTrue(mod.RUNNING_TESTS)
        self.assertNotEqual(mod.REDIS_KEY_NAMESPACE, "")

    def test_each_test_process_gets_a_distinct_namespace(self) -> None:
        first = _reload(["manage.py", "test"]).REDIS_KEY_NAMESPACE
        second = _reload(["manage.py", "test"]).REDIS_KEY_NAMESPACE
        self.assertNotEqual(first, second)

    def test_non_test_process_keeps_production_names(self) -> None:
        mod = _reload(["manage.py", "runserver"])
        self.assertFalse(mod.RUNNING_TESTS)
        self.assertEqual(mod.REDIS_KEY_NAMESPACE, "")
        self.assertNotIn("prefix", _layer_config(mod))
        self.assertEqual(mod.CACHEOPS_PREFIX(None), f"dtx-v{mod._deploy_version()}:")
        self.assertNotIn("KEY_PREFIX", mod.CACHES["default"])


class NamespacedKeyTests(SimpleTestCase):
    @override_settings(REDIS_KEY_NAMESPACE="")
    def test_key_unchanged_without_namespace(self) -> None:
        self.assertEqual(namespaced_key("herodraft:1:x"), "herodraft:1:x")

    @override_settings(REDIS_KEY_NAMESPACE="test-1-ab:")
    def test_key_prefixed_with_namespace(self) -> None:
        self.assertEqual(namespaced_key("herodraft:1:x"), "test-1-ab:herodraft:1:x")

    @override_settings(REDIS_KEY_NAMESPACE="")
    def test_tick_keys_keep_production_format(self) -> None:
        self.assertEqual(conn_count_key(5), "herodraft:connections:5")
        self.assertEqual(tick_lock_key(5), "herodraft:tick_lock:5")
        self.assertEqual(captain_heartbeat_key(5, 9), "herodraft:5:captain:9:heartbeat")

    @override_settings(REDIS_KEY_NAMESPACE="ns:")
    def test_tick_keys_include_namespace(self) -> None:
        self.assertEqual(conn_count_key(5), "ns:herodraft:connections:5")
        self.assertEqual(tick_lock_key(5), "ns:herodraft:tick_lock:5")
        self.assertEqual(
            captain_heartbeat_key(5, 9), "ns:herodraft:5:captain:9:heartbeat"
        )

    @override_settings(REDIS_KEY_NAMESPACE="ns:")
    def test_consumer_keys_include_namespace(self) -> None:
        consumer = ConcreteDraftConsumer.__new__(ConcreteDraftConsumer)
        self.assertEqual(
            consumer._heartbeat_key(1, 2), "ns:testdraft:1:captain:2:heartbeat"
        )
        self.assertEqual(
            consumer._captain_channel_key(1, 2), "ns:testdraft:1:captain:2:channel"
        )

    @override_settings(REDIS_KEY_NAMESPACE="ns:")
    def test_consumer_and_tick_heartbeat_keys_agree(self) -> None:
        class HeroPrefix(ConcreteDraftConsumer):
            def get_room_group_prefix(self) -> str:
                return "herodraft"

        consumer = HeroPrefix.__new__(HeroPrefix)
        self.assertEqual(consumer._heartbeat_key(3, 4), captain_heartbeat_key(3, 4))


@mock.patch.dict(os.environ, {"TEST": "true", "DISABLE_CACHE": "false"})
class CacheFlushOnBootTests(SimpleTestCase):
    @override_settings(RUNNING_TESTS=True)
    def test_test_run_does_not_flush_shared_cache_db(self) -> None:
        with mock.patch("cacheops.invalidate_all") as flush:
            apps.get_app_config("app").ready()
        flush.assert_not_called()

    @override_settings(RUNNING_TESTS=False)
    def test_test_stack_boot_still_flushes(self) -> None:
        with mock.patch("cacheops.invalidate_all") as flush:
            apps.get_app_config("app").ready()
        flush.assert_called_once_with()

    def test_settings_without_flag_still_flush(self) -> None:
        with self.settings(), mock.patch("cacheops.invalidate_all") as flush:
            del settings.RUNNING_TESTS
            apps.get_app_config("app").ready()
        flush.assert_called_once_with()

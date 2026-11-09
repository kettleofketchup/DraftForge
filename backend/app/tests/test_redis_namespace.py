"""Per-process Redis namespace for test runs, empty outside the test runner.

Concurrent `manage.py test` runs share one Redis and number their drafts from 1,
so group names and raw keys collide unless each run gets its own namespace.
"""

import ast
import importlib
import os
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from cacheops.redis import redis_client as cacheops_redis
from django.apps import apps
from django.conf import settings
from django.test import SimpleTestCase, override_settings

import backend.settings
from app.consumers import DraftConsumer, HeroDraftConsumer
from app.redis_keys import namespaced_key
from app.tasks import draft_tick, teamdraft_tick
from app.tasks.herodraft_tick import (
    captain_heartbeat_key,
    conn_count_key,
    tick_lock_key,
)
from app.tests.test_consumers_base import ConcreteDraftConsumer
from config.celery import app as celery_app
from discordbot.utils import _acquire_rate_limit_token, rate_limit_key
from tests.cache import flush_run_cache

BACKEND_ROOT = Path(__file__).resolve().parents[2]

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


class DraftTickKeyNamespaceTests(SimpleTestCase):
    PREFIXES: tuple[str, ...] = ("herodraft", "teamdraft")

    def _keys(self, prefix: str) -> list[str]:
        return [
            draft_tick.heartbeat_key(prefix, 5, 9),
            draft_tick.captain_channel_key(prefix, 5, 9),
            draft_tick.conn_count_key(prefix, 5),
            draft_tick.lock_key(prefix, 5),
        ]

    @override_settings(REDIS_KEY_NAMESPACE="")
    def test_shared_helpers_keep_production_format(self) -> None:
        for prefix in self.PREFIXES:
            self.assertEqual(
                self._keys(prefix),
                [
                    f"{prefix}:5:captain:9:heartbeat",
                    f"{prefix}:5:captain:9:channel",
                    f"{prefix}:connections:5",
                    f"{prefix}:tick_lock:5",
                ],
            )

    @override_settings(REDIS_KEY_NAMESPACE="ns:")
    def test_shared_helpers_include_namespace(self) -> None:
        for prefix in self.PREFIXES:
            for key in self._keys(prefix):
                self.assertTrue(key.startswith(f"ns:{prefix}:"), key)

    def test_active_run_namespace_applies_to_shared_helpers(self) -> None:
        self.assertNotEqual(settings.REDIS_KEY_NAMESPACE, "")
        for prefix in self.PREFIXES:
            for key in self._keys(prefix):
                self.assertTrue(key.startswith(settings.REDIS_KEY_NAMESPACE), key)

    @override_settings(REDIS_KEY_NAMESPACE="")
    def test_team_captain_conn_key_keeps_production_format(self) -> None:
        self.assertEqual(
            teamdraft_tick.captain_conn_key(5, 9), "teamdraft:5:captain:9:conns"
        )

    @override_settings(REDIS_KEY_NAMESPACE="ns:")
    def test_team_captain_conn_key_includes_namespace(self) -> None:
        self.assertEqual(
            teamdraft_tick.captain_conn_key(5, 9), "ns:teamdraft:5:captain:9:conns"
        )

    @override_settings(REDIS_KEY_NAMESPACE="ns:")
    def test_hero_compat_wrappers_match_shared_helpers(self) -> None:
        self.assertEqual(conn_count_key(5), draft_tick.conn_count_key("herodraft", 5))
        self.assertEqual(tick_lock_key(5), draft_tick.lock_key("herodraft", 5))
        self.assertEqual(
            captain_heartbeat_key(5, 9),
            draft_tick.heartbeat_key("herodraft", 5, 9),
        )

    @override_settings(REDIS_KEY_NAMESPACE="ns:")
    def test_real_consumer_keys_agree_with_tick_keys(self) -> None:
        hero = HeroDraftConsumer.__new__(HeroDraftConsumer)
        team = DraftConsumer.__new__(DraftConsumer)
        self.assertEqual(hero._heartbeat_key(3, 4), captain_heartbeat_key(3, 4))
        self.assertEqual(
            team._heartbeat_key(3, 4), draft_tick.heartbeat_key("teamdraft", 3, 4)
        )
        self.assertEqual(
            team._captain_channel_key(3, 4),
            "ns:teamdraft:3:captain:4:channel",
        )


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


class FlushRunCacheTests(SimpleTestCase):
    def setUp(self) -> None:
        own_cacheops = settings.CACHEOPS_PREFIX(None)
        self.own = [
            f"{own_cacheops}q:flush-probe",
            f"{own_cacheops}conj:app_league:flush-probe",
            f"{settings.REDIS_KEY_NAMESPACE}:1:flush-probe",
        ]
        self.foreign = [
            "dtx-v0.0.0:test-1-deadbeef:q:flush-probe",
            "dtx-v0.0.0:q:flush-probe",
            "celery-flush-probe",
        ]
        for key in (*self.own, *self.foreign):
            cacheops_redis.set(key, "1", ex=60)
        self.addCleanup(cacheops_redis.delete, *self.own, *self.foreign)

    def test_deletes_only_this_runs_keys(self) -> None:
        flush_run_cache()
        self.assertEqual(cacheops_redis.exists(*self.own), 0)
        self.assertEqual(cacheops_redis.exists(*self.foreign), len(self.foreign))

    @override_settings(REDIS_KEY_NAMESPACE="")
    def test_refuses_without_a_namespace(self) -> None:
        with self.assertRaises(RuntimeError):
            flush_run_cache()
        self.assertEqual(cacheops_redis.exists(*self.foreign), len(self.foreign))


class NoGlobalCacheFlushTests(SimpleTestCase):
    """invalidate_all() is FLUSHDB on the DB the live test stack shares."""

    ALLOWED: frozenset[str] = frozenset({"app/apps.py"})

    def test_no_invalidate_all_outside_app_ready(self) -> None:
        offenders: list[str] = []
        for path in sorted(BACKEND_ROOT.rglob("*.py")):
            rel = path.relative_to(BACKEND_ROOT).as_posix()
            if rel in self.ALLOWED or "/migrations/" in rel:
                continue
            tree = ast.parse(path.read_text(), filename=rel)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and any(
                    a.name == "invalidate_all" for a in node.names
                ):
                    offenders.append(f"{rel}:{node.lineno}")
                elif isinstance(node, ast.Attribute) and node.attr == "invalidate_all":
                    offenders.append(f"{rel}:{node.lineno}")
        self.assertEqual(offenders, [], "use tests.cache.flush_run_cache() instead")


class CeleryEagerUnderTestsTests(SimpleTestCase):
    def test_test_run_executes_tasks_in_process(self) -> None:
        mod = _reload(["manage.py", "test"])
        self.assertIs(mod.CELERY_TASK_ALWAYS_EAGER, True)
        self.assertIs(mod.CELERY_TASK_EAGER_PROPAGATES, True)

    def test_non_test_process_keeps_the_broker(self) -> None:
        # reload() re-executes into the old namespace; drop names a test run set.
        for name in ("CELERY_TASK_ALWAYS_EAGER", "CELERY_TASK_EAGER_PROPAGATES"):
            vars(backend.settings).pop(name, None)
        mod = _reload(["manage.py", "runserver"])
        self.assertFalse(hasattr(mod, "CELERY_TASK_ALWAYS_EAGER"))
        self.assertFalse(hasattr(mod, "CELERY_TASK_EAGER_PROPAGATES"))

    def test_active_celery_app_is_eager(self) -> None:
        self.assertIs(celery_app.conf.task_always_eager, True)
        self.assertIs(celery_app.conf.task_eager_propagates, True)


class DiscordRateLimitKeyTests(SimpleTestCase):
    @override_settings(REDIS_KEY_NAMESPACE="")
    def test_production_key_unchanged(self) -> None:
        self.assertEqual(rate_limit_key(), "discord:rate_limit:global")

    @override_settings(REDIS_KEY_NAMESPACE="ns:")
    def test_key_includes_namespace(self) -> None:
        self.assertEqual(rate_limit_key(), "ns:discord:rate_limit:global")

    @override_settings(REDIS_KEY_NAMESPACE="ns:")
    def test_token_bucket_uses_namespaced_key(self) -> None:
        with mock.patch("discordbot.utils.redis_client") as client:
            client.eval.return_value = 1
            _acquire_rate_limit_token()
        self.assertEqual(client.eval.call_args.args[2], "ns:discord:rate_limit:global")

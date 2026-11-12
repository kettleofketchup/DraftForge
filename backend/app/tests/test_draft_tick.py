"""Tests for the shared tick runner (app.tasks.draft_tick)."""

import asyncio
import contextvars
import threading
import time
from collections.abc import Callable
from unittest.mock import patch

from asgiref.sync import SyncToAsync
from channels.db import database_sync_to_async
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from structlog.testing import capture_logs

from app.tasks import draft_tick, herodraft_tick
from app.tasks.draft_tick import (
    TickDriver,
    captain_channel_key,
    conn_count_key,
    decrement_connection_count,
    get_connection_count,
    get_redis_client,
    heartbeat_key,
    increment_connection_count,
    lock_key,
    touch_connection,
)


@override_settings(REDIS_KEY_NAMESPACE="")
class KeyHelperTests(SimpleTestCase):
    def test_heartbeat_key_matches_hero_literal(self) -> None:
        self.assertEqual(
            heartbeat_key("herodraft", 1, 2), "herodraft:1:captain:2:heartbeat"
        )

    def test_captain_channel_key_matches_hero_literal(self) -> None:
        self.assertEqual(
            captain_channel_key("herodraft", 1, 2), "herodraft:1:captain:2:channel"
        )

    def test_conn_count_key_matches_hero_literal(self) -> None:
        self.assertEqual(conn_count_key("herodraft", 7), "herodraft:live_connections:7")

    def test_lock_key_matches_hero_literal(self) -> None:
        self.assertEqual(lock_key("herodraft", 7), "herodraft:tick_lock:7")

    def test_team_prefix_keys_are_distinct_from_hero(self) -> None:
        self.assertNotEqual(
            heartbeat_key("teamdraft", 1, 2), heartbeat_key("herodraft", 1, 2)
        )
        self.assertEqual(conn_count_key("teamdraft", 7), "teamdraft:live_connections:7")

    def test_constants_match_hero_values(self) -> None:
        self.assertEqual(draft_tick.LOCK_TIMEOUT, 10)
        self.assertEqual(draft_tick.HEARTBEAT_STALE_SECONDS, 9)
        self.assertEqual(draft_tick.HEARTBEAT_TTL, 30)
        self.assertEqual(draft_tick.HEARTBEAT_INTERVAL_SECONDS, 3)
        self.assertEqual(draft_tick.CAPTAIN_CHANNEL_TTL, 300)


class ConnectionCountTests(TransactionTestCase):
    DRAFT_ID = 987_001

    def tearDown(self) -> None:
        r = get_redis_client()
        r.delete(
            conn_count_key("herodraft", self.DRAFT_ID),
            conn_count_key("teamdraft", self.DRAFT_ID),
        )

    def test_counts_are_isolated_per_prefix(self) -> None:
        self.assertEqual(
            increment_connection_count("teamdraft", self.DRAFT_ID, "c1"), 1
        )
        self.assertEqual(
            increment_connection_count("teamdraft", self.DRAFT_ID, "c2"), 2
        )
        self.assertEqual(get_connection_count("herodraft", self.DRAFT_ID), 0)
        self.assertEqual(get_connection_count("teamdraft", self.DRAFT_ID), 2)

    def test_double_disconnect_never_goes_below_zero(self) -> None:
        increment_connection_count("teamdraft", self.DRAFT_ID, "c1")
        self.assertEqual(
            decrement_connection_count("teamdraft", self.DRAFT_ID, "c1"), 0
        )
        self.assertEqual(
            decrement_connection_count("teamdraft", self.DRAFT_ID, "c1"), 0
        )
        increment_connection_count("teamdraft", self.DRAFT_ID, "c2")
        self.assertEqual(get_connection_count("teamdraft", self.DRAFT_ID), 1)

    def test_live_connection_outlives_the_key_ttl(self) -> None:
        increment_connection_count("teamdraft", self.DRAFT_ID, "c1")
        get_redis_client().delete(conn_count_key("teamdraft", self.DRAFT_ID))
        self.assertEqual(get_connection_count("teamdraft", self.DRAFT_ID), 0)

        touch_connection("teamdraft", self.DRAFT_ID, "c1")

        self.assertEqual(get_connection_count("teamdraft", self.DRAFT_ID), 1)

    def test_connection_not_refreshed_within_the_stale_window_is_not_counted(
        self,
    ) -> None:
        increment_connection_count("teamdraft", self.DRAFT_ID, "c1")
        stale_at = time.time() - draft_tick.CONN_STALE_SECONDS - 1
        get_redis_client().zadd(
            conn_count_key("teamdraft", self.DRAFT_ID), {"c2": stale_at}
        )
        self.assertEqual(get_connection_count("teamdraft", self.DRAFT_ID), 1)

    def test_touch_prunes_members_past_the_stale_window(self) -> None:
        key = conn_count_key("teamdraft", self.DRAFT_ID)
        stale_at = time.time() - draft_tick.CONN_STALE_SECONDS - 1
        get_redis_client().zadd(key, {"crashed": stale_at})
        touch_connection("teamdraft", self.DRAFT_ID, "c1")
        self.assertEqual(get_redis_client().zrange(key, 0, -1), ["c1"])


class RecordingDriver:
    """Minimal TickDriver that records step order and stops after N iterations."""

    def __init__(self, prefix: str, iterations: int = 1, fail_step: str | None = None):
        self.prefix = prefix
        self.system = prefix
        self.calls: list[str] = []
        self._remaining = iterations
        self._fail_step = fail_step

    async def check_resume_countdown(self, draft_id: int) -> None:
        self._record("resume_countdown")

    async def check_captain_heartbeats(self, draft_id: int) -> None:
        self._record("captain_heartbeats")

    async def broadcast_tick(self, draft_id: int) -> None:
        self._record("broadcast_tick")

    async def check_timeout(self, draft_id: int) -> None:
        self._record("check_timeout")

    def should_continue(self, draft_id: int) -> tuple[bool, str]:
        if self._remaining <= 0:
            return False, "test_done"
        self._remaining -= 1
        return True, ""

    def _record(self, name: str) -> None:
        if self._fail_step == name:
            raise RuntimeError(f"boom in {name}")
        self.calls.append(name)


def _wait_for_thread(prefix: str, draft_id: int, timeout: float = 3.0) -> None:
    info = draft_tick.registry_for(prefix).get(draft_id)
    if info:
        info.thread.join(timeout=timeout)


class RegistryTests(TransactionTestCase):
    DRAFT_ID = 987_002

    def setUp(self):
        draft_tick.stop_all_broadcasters()  # joins any thread a previous test left running
        with draft_tick._lock:
            for reg in draft_tick._registries.values():
                reg.clear()
        get_redis_client().delete(
            lock_key("herodraft", self.DRAFT_ID), lock_key("teamdraft", self.DRAFT_ID)
        )

    tearDown = setUp

    def test_registry_for_returns_same_dict_object(self):
        self.assertIs(
            draft_tick.registry_for("herodraft"), draft_tick.registry_for("herodraft")
        )
        self.assertIsNot(
            draft_tick.registry_for("herodraft"), draft_tick.registry_for("teamdraft")
        )

    def test_registry_for_callable_while_holding_lock(self):
        result: list[dict] = []

        def call_under_lock() -> None:
            with draft_tick._lock:
                result.append(draft_tick.registry_for("fresh-prefix"))

        t = threading.Thread(target=call_under_lock, daemon=True)
        t.start()
        t.join(timeout=1)
        self.assertFalse(t.is_alive(), "registry_for() must not take _lock")
        self.assertEqual(result, [{}])

    def test_protocol_is_satisfied_by_recording_driver(self):
        self.assertIsInstance(RecordingDriver("x"), TickDriver)

    def test_same_draft_id_ticks_independently_per_prefix(self):
        hero = RecordingDriver("herodraft", iterations=10_000)
        team = RecordingDriver("teamdraft", iterations=10_000)
        self.assertTrue(draft_tick.start_tick_broadcaster(hero, self.DRAFT_ID))
        self.assertTrue(draft_tick.start_tick_broadcaster(team, self.DRAFT_ID))
        self.assertIn(self.DRAFT_ID, draft_tick.registry_for("herodraft"))
        self.assertIn(self.DRAFT_ID, draft_tick.registry_for("teamdraft"))
        self.assertEqual(
            get_redis_client().get(lock_key("teamdraft", self.DRAFT_ID)), "locked"
        )

        draft_tick.stop_tick_broadcaster("herodraft", self.DRAFT_ID)
        self.assertNotIn(self.DRAFT_ID, draft_tick.registry_for("herodraft"))
        self.assertIn(self.DRAFT_ID, draft_tick.registry_for("teamdraft"))
        self.assertIsNone(get_redis_client().get(lock_key("herodraft", self.DRAFT_ID)))
        self.assertEqual(
            get_redis_client().get(lock_key("teamdraft", self.DRAFT_ID)), "locked"
        )
        draft_tick.stop_tick_broadcaster("teamdraft", self.DRAFT_ID)

    def test_duplicate_start_same_prefix_returns_false(self):
        driver = RecordingDriver("teamdraft", iterations=10_000)
        self.assertTrue(draft_tick.start_tick_broadcaster(driver, self.DRAFT_ID))
        self.assertFalse(draft_tick.start_tick_broadcaster(driver, self.DRAFT_ID))
        draft_tick.stop_tick_broadcaster("teamdraft", self.DRAFT_ID)

    def test_loop_dispatches_steps_in_hero_order(self):
        driver = RecordingDriver("teamdraft", iterations=1)
        draft_tick.start_tick_broadcaster(driver, self.DRAFT_ID)
        _wait_for_thread("teamdraft", self.DRAFT_ID)
        self.assertEqual(
            driver.calls,
            [
                "resume_countdown",
                "captain_heartbeats",
                "broadcast_tick",
                "check_timeout",
            ],
        )
        self.assertNotIn(self.DRAFT_ID, draft_tick.registry_for("teamdraft"))
        self.assertIsNone(get_redis_client().get(lock_key("teamdraft", self.DRAFT_ID)))

    def test_step_exception_releases_lock_and_registry(self):
        driver = RecordingDriver("teamdraft", iterations=5, fail_step="broadcast_tick")
        with capture_logs() as logs:
            draft_tick.start_tick_broadcaster(driver, self.DRAFT_ID)
            _wait_for_thread("teamdraft", self.DRAFT_ID)
        errors = [e for e in logs if e["event"] == "tick_broadcaster_error"]
        self.assertEqual([e["error"] for e in errors], ["boom in broadcast_tick"])
        self.assertNotIn(self.DRAFT_ID, draft_tick.registry_for("teamdraft"))
        self.assertIsNone(get_redis_client().get(lock_key("teamdraft", self.DRAFT_ID)))

    def test_failed_thread_start_releases_lock_and_registry(self) -> None:
        driver = RecordingDriver("teamdraft", iterations=10_000)
        with (
            patch.object(
                draft_tick.threading.Thread,
                "start",
                side_effect=RuntimeError("can't start new thread"),
            ),
            self.assertRaises(RuntimeError),
        ):
            draft_tick.start_tick_broadcaster(driver, self.DRAFT_ID)
        self.assertNotIn(self.DRAFT_ID, draft_tick.registry_for("teamdraft"))
        self.assertIsNone(get_redis_client().get(lock_key("teamdraft", self.DRAFT_ID)))
        self.assertTrue(draft_tick.start_tick_broadcaster(driver, self.DRAFT_ID))
        draft_tick.stop_tick_broadcaster("teamdraft", self.DRAFT_ID)

    def test_stop_unknown_prefix_and_id_is_safe(self):
        draft_tick.stop_tick_broadcaster("never-registered", 1)
        draft_tick.stop_tick_broadcaster("teamdraft", 424242)

    def test_stop_all_covers_every_prefix(self):
        draft_tick.start_tick_broadcaster(
            RecordingDriver("herodraft", 10_000), self.DRAFT_ID
        )
        draft_tick.start_tick_broadcaster(
            RecordingDriver("teamdraft", 10_000), self.DRAFT_ID
        )
        draft_tick.stop_all_broadcasters()
        self.assertEqual(draft_tick.registry_for("herodraft"), {})
        self.assertEqual(draft_tick.registry_for("teamdraft"), {})


_STARTER_VAR: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_STARTER_VAR", default=None
)


class ContextRecordingDriver(RecordingDriver):
    def __init__(self, prefix: str) -> None:
        super().__init__(prefix, iterations=1)
        self.seen: list[str | None] = []

    async def check_resume_countdown(self, draft_id: int) -> None:
        self.seen.append(_STARTER_VAR.get())


class InheritingThread(threading.Thread):
    """Thread that runs its target in a copy of the starter's context.

    Mirrors runtimes where new threads inherit context variables
    (``sys.flags.thread_inherit_context``, the free-threaded 3.14 default).
    """

    def __init__(
        self, *args: object, target: Callable[..., object], **kwargs: object
    ) -> None:
        ctx = contextvars.copy_context()
        super().__init__(
            *args, target=lambda *a, **k: ctx.run(target, *a, **k), **kwargs
        )


class TickThreadContextTests(TransactionTestCase):
    DRAFT_ID = 987_003

    def setUp(self) -> None:
        draft_tick.stop_all_broadcasters()
        get_redis_client().delete(lock_key("teamdraft", self.DRAFT_ID))

    tearDown = setUp

    def test_tick_thread_does_not_see_the_starters_context(self) -> None:
        driver = ContextRecordingDriver("teamdraft")
        token = _STARTER_VAR.set("starter")
        try:
            with patch.object(draft_tick.threading, "Thread", InheritingThread):
                self.assertTrue(
                    draft_tick.start_tick_broadcaster(driver, self.DRAFT_ID)
                )
        finally:
            _STARTER_VAR.reset(token)
        _wait_for_thread("teamdraft", self.DRAFT_ID)
        self.assertEqual(driver.seen, [None])


class HeroDriverAliasTests(SimpleTestCase):
    def test_active_tick_tasks_is_the_hero_registry(self) -> None:
        self.assertIs(
            herodraft_tick._active_tick_tasks, draft_tick.registry_for("herodraft")
        )
        self.assertIs(herodraft_tick._lock, draft_tick._lock)

    def test_hero_driver_satisfies_protocol_with_hero_prefix(self) -> None:
        self.assertIsInstance(herodraft_tick.HERO_TICK_DRIVER, TickDriver)
        self.assertEqual(herodraft_tick.HeroDraftTickDriver.prefix, "herodraft")
        self.assertEqual(herodraft_tick.HeroDraftTickDriver.system, "herodraft")

    @override_settings(REDIS_KEY_NAMESPACE="")
    def test_hero_constants_still_exported(self) -> None:
        self.assertEqual(
            herodraft_tick.CONN_COUNT_KEY.format(draft_id=3),
            conn_count_key("herodraft", 3),
        )
        self.assertEqual(
            herodraft_tick.LOCK_KEY.format(draft_id=3), lock_key("herodraft", 3)
        )
        self.assertEqual(
            herodraft_tick.CAPTAIN_HEARTBEAT_KEY.format(draft_id=3, user_id=4),
            heartbeat_key("herodraft", 3, 4),
        )
        self.assertIs(herodraft_tick.get_redis_client, get_redis_client)

    @patch(
        "app.tasks.herodraft_tick.should_continue_ticking",
        return_value=(False, "patched"),
    )
    def test_driver_should_continue_is_patchable_at_module_level(self, mocked) -> None:
        self.assertEqual(
            herodraft_tick.HERO_TICK_DRIVER.should_continue(5), (False, "patched")
        )
        mocked.assert_called_once()


class TickLoopExecutorTests(SimpleTestCase):
    """A writer stuck on SQLite's lock must not stall every draft's ticks and sockets."""

    def test_tick_loop_db_work_does_not_share_the_global_single_thread(self) -> None:
        shared = SyncToAsync.single_thread_executor.submit(threading.get_ident).result()
        seen: list[int] = []

        async def body() -> None:
            seen.append(await database_sync_to_async(threading.get_ident)())

        thread = threading.Thread(
            target=lambda: asyncio.run(draft_tick.with_own_db_thread(body()))
        )
        thread.start()
        thread.join(timeout=5)

        self.assertEqual(len(seen), 1)
        self.assertNotEqual(seen[0], shared)

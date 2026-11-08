"""Tests for the shared tick runner (app.tasks.draft_tick)."""

import threading

from django.test import SimpleTestCase, TransactionTestCase

from app.tasks import draft_tick
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
)


class KeyHelperTests(SimpleTestCase):
    def test_heartbeat_key_matches_hero_literal(self) -> None:
        self.assertEqual(heartbeat_key("herodraft", 1, 2), "herodraft:1:captain:2:heartbeat")

    def test_captain_channel_key_matches_hero_literal(self) -> None:
        self.assertEqual(captain_channel_key("herodraft", 1, 2), "herodraft:1:captain:2:channel")

    def test_conn_count_key_matches_hero_literal(self) -> None:
        self.assertEqual(conn_count_key("herodraft", 7), "herodraft:connections:7")

    def test_lock_key_matches_hero_literal(self) -> None:
        self.assertEqual(lock_key("herodraft", 7), "herodraft:tick_lock:7")

    def test_team_prefix_keys_are_distinct_from_hero(self) -> None:
        self.assertNotEqual(heartbeat_key("teamdraft", 1, 2), heartbeat_key("herodraft", 1, 2))
        self.assertEqual(conn_count_key("teamdraft", 7), "teamdraft:connections:7")

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
        r.delete(conn_count_key("herodraft", self.DRAFT_ID), conn_count_key("teamdraft", self.DRAFT_ID))

    def test_counts_are_isolated_per_prefix(self) -> None:
        self.assertEqual(increment_connection_count("teamdraft", self.DRAFT_ID), 1)
        self.assertEqual(increment_connection_count("teamdraft", self.DRAFT_ID), 2)
        self.assertEqual(get_connection_count("herodraft", self.DRAFT_ID), 0)
        self.assertEqual(get_connection_count("teamdraft", self.DRAFT_ID), 2)

    def test_decrement_below_zero_deletes_key_and_returns_zero(self) -> None:
        increment_connection_count("teamdraft", self.DRAFT_ID)
        self.assertEqual(decrement_connection_count("teamdraft", self.DRAFT_ID), 0)
        self.assertEqual(decrement_connection_count("teamdraft", self.DRAFT_ID), 0)
        self.assertIsNone(get_redis_client().get(conn_count_key("teamdraft", self.DRAFT_ID)))

    def test_increment_sets_300s_expiry(self) -> None:
        increment_connection_count("teamdraft", self.DRAFT_ID)
        ttl = get_redis_client().ttl(conn_count_key("teamdraft", self.DRAFT_ID))
        self.assertTrue(0 < ttl <= 300)


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
        get_redis_client().delete(lock_key("herodraft", self.DRAFT_ID), lock_key("teamdraft", self.DRAFT_ID))

    tearDown = setUp

    def test_registry_for_returns_same_dict_object(self):
        self.assertIs(draft_tick.registry_for("herodraft"), draft_tick.registry_for("herodraft"))
        self.assertIsNot(draft_tick.registry_for("herodraft"), draft_tick.registry_for("teamdraft"))

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
        self.assertEqual(get_redis_client().get(lock_key("teamdraft", self.DRAFT_ID)), "locked")

        draft_tick.stop_tick_broadcaster("herodraft", self.DRAFT_ID)
        self.assertNotIn(self.DRAFT_ID, draft_tick.registry_for("herodraft"))
        self.assertIn(self.DRAFT_ID, draft_tick.registry_for("teamdraft"))
        self.assertIsNone(get_redis_client().get(lock_key("herodraft", self.DRAFT_ID)))
        self.assertEqual(get_redis_client().get(lock_key("teamdraft", self.DRAFT_ID)), "locked")
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
            ["resume_countdown", "captain_heartbeats", "broadcast_tick", "check_timeout"],
        )
        self.assertNotIn(self.DRAFT_ID, draft_tick.registry_for("teamdraft"))
        self.assertIsNone(get_redis_client().get(lock_key("teamdraft", self.DRAFT_ID)))

    def test_step_exception_releases_lock_and_registry(self):
        driver = RecordingDriver("teamdraft", iterations=5, fail_step="broadcast_tick")
        draft_tick.start_tick_broadcaster(driver, self.DRAFT_ID)
        _wait_for_thread("teamdraft", self.DRAFT_ID)
        self.assertNotIn(self.DRAFT_ID, draft_tick.registry_for("teamdraft"))
        self.assertIsNone(get_redis_client().get(lock_key("teamdraft", self.DRAFT_ID)))

    def test_stop_unknown_prefix_and_id_is_safe(self):
        draft_tick.stop_tick_broadcaster("never-registered", 1)
        draft_tick.stop_tick_broadcaster("teamdraft", 424242)

    def test_stop_all_covers_every_prefix(self):
        draft_tick.start_tick_broadcaster(RecordingDriver("herodraft", 10_000), self.DRAFT_ID)
        draft_tick.start_tick_broadcaster(RecordingDriver("teamdraft", 10_000), self.DRAFT_ID)
        draft_tick.stop_all_broadcasters()
        self.assertEqual(draft_tick.registry_for("herodraft"), {})
        self.assertEqual(draft_tick.registry_for("teamdraft"), {})

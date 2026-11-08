"""Tests for the shared tick runner (app.tasks.draft_tick)."""

from django.test import SimpleTestCase, TransactionTestCase

from app.tasks import draft_tick
from app.tasks.draft_tick import (
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

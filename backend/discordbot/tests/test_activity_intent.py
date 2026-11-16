import json
from unittest import mock

import redis
from django.test import TestCase
from structlog.testing import capture_logs

from discordbot import activity_intent
from discordbot.activity_intent import (
    INTENT_TTL_SECONDS,
    LaunchIntent,
    consume_intent,
    intent_key,
    peek_intent,
    record_intent,
)
from discordbot.tests.activity_helpers import ClearIntentsMixin
from discordbot.utils import redis_client


def _record(draft_id: int = 5, kind: str = "hero") -> str | None:
    return record_intent(
        "777",
        kind=kind,
        draft_id=draft_id,
        tournament_id=3,
        guild_id="1",
        channel_id="2",
    )


class LaunchIntentTests(ClearIntentsMixin, TestCase):
    def test_record_then_peek_round_trips(self) -> None:
        intent_id = _record()
        intent = peek_intent("777")
        assert intent is not None
        self.assertEqual(intent.intent_id, intent_id)
        self.assertEqual(intent.kind, "hero")
        self.assertEqual(intent.draft_id, 5)
        self.assertEqual(intent.tournament_id, 3)
        self.assertTrue(intent.applies_to("1", "2"))
        self.assertFalse(intent.applies_to("1", "9"))
        self.assertFalse(intent.applies_to("8", "2"))
        self.assertEqual(
            intent.ref(), {"intent_id": intent_id, "kind": "hero", "id": 5}
        )
        ttl = redis_client.ttl(intent_key("777"))
        self.assertTrue(0 < ttl <= INTENT_TTL_SECONDS, ttl)

    def test_peek_without_intent_is_none(self) -> None:
        self.assertIsNone(peek_intent("777"))

    def test_peek_does_not_consume(self) -> None:
        intent_id = _record()
        first = peek_intent("777")
        second = peek_intent("777")
        assert first is not None and second is not None
        self.assertEqual(first.intent_id, intent_id)
        self.assertEqual(second, first)

    def test_last_launch_wins(self) -> None:
        _record(draft_id=5)
        newer = _record(draft_id=6, kind="team")
        intent = peek_intent("777")
        assert intent is not None
        self.assertEqual(
            (intent.intent_id, intent.kind, intent.draft_id), (newer, "team", 6)
        )

    def test_consume_with_stale_id_keeps_newer_intent(self) -> None:
        old = _record(draft_id=5)
        new = _record(draft_id=6)
        assert old is not None and new is not None
        self.assertFalse(consume_intent("777", old))
        intent = peek_intent("777")
        assert intent is not None
        self.assertEqual(intent.intent_id, new)
        self.assertTrue(consume_intent("777", new))
        self.assertIsNone(peek_intent("777"))
        self.assertFalse(consume_intent("777", new))

    def test_malformed_payload_peeks_as_none(self) -> None:
        redis_client.set(intent_key("777"), "not json", ex=60)
        self.assertIsNone(peek_intent("777"))
        redis_client.set(intent_key("777"), json.dumps({"intent_id": "x"}), ex=60)
        self.assertIsNone(peek_intent("777"))
        self.assertFalse(consume_intent("777", "x"))

    def test_redis_errors_fail_open_and_log(self) -> None:
        broken = mock.Mock()
        broken.set.side_effect = redis.ConnectionError("down")
        broken.get.side_effect = redis.ConnectionError("down")
        broken.evalsha.side_effect = redis.ConnectionError("down")
        script = mock.Mock(side_effect=redis.ConnectionError("down"))
        with (
            mock.patch.object(activity_intent, "redis_client", broken),
            mock.patch.object(activity_intent, "_CONSUME", script),
            capture_logs() as logs,
        ):
            self.assertIsNone(_record())
            self.assertIsNone(peek_intent("777"))
            self.assertFalse(consume_intent("777", "x"))
        failures = [e for e in logs if e["event"] == "activity_intent_redis_failed"]
        self.assertEqual([e["op"] for e in failures], ["record", "peek", "consume"])
        for event in failures:
            self.assertEqual(event["system"], "discord")
            self.assertEqual(event["subsystem"], "activity")
            self.assertEqual(event["error_type"], "ConnectionError")

    def test_intent_is_frozen(self) -> None:
        intent = LaunchIntent(
            intent_id="a",
            kind="hero",
            draft_id=1,
            tournament_id=None,
            guild_id="1",
            channel_id="2",
            created_at="2026-11-16T00:00:00+00:00",
        )
        with self.assertRaises(AttributeError):
            intent.draft_id = 2  # type: ignore[misc]

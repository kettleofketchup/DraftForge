"""Unit tests for discord_log_context CM and InteractionContext."""

from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import MagicMock

import structlog
from structlog.contextvars import clear_contextvars, get_contextvars
from structlog.testing import capture_logs


class InteractionContextTests(TestCase):
    def test_starts_empty(self):
        from discordbot.log_context import InteractionContext

        ctx = InteractionContext()
        self.assertIsNone(ctx.outcome)
        self.assertEqual(ctx.extra, {})

    def test_set_outcome_overwrites(self):
        from discordbot.log_context import InteractionContext

        ctx = InteractionContext()
        ctx.set_outcome("signed_up")
        ctx.set_outcome("error")
        self.assertEqual(ctx.outcome, "error")

    def test_add_merges_kwargs(self):
        from discordbot.log_context import InteractionContext

        ctx = InteractionContext()
        ctx.add(signup_id=42)
        ctx.add(signup_status="confirmed")
        self.assertEqual(ctx.extra, {"signup_id": 42, "signup_status": "confirmed"})


class TagsAndIdsTests(TestCase):
    def test_resolve_tags_known_prefixes(self):
        from discordbot.log_context import resolve_tags

        signup_prefixes = [
            "event_signup:42", "event_notify:42", "event_tentative:42", "event_decline:42",
            "signup_friend_id:42", "signup_rank_status:42",
            "pos_select_1:42", "pos_confirm:42",
            "rank_medal:42", "rank_star:7:Herald",
            "bcup_tier:42", "screenshot_upload:42:rank", "screenshot_file:42:rank",
        ]
        for cid in signup_prefixes:
            self.assertEqual(resolve_tags(cid), ["events", "signup"], cid)

    def test_resolve_tags_unknown_returns_empty(self):
        from discordbot.log_context import resolve_tags

        self.assertEqual(resolve_tags("unknown_prefix:99"), [])
        self.assertEqual(resolve_tags(None), [])
        self.assertEqual(resolve_tags(""), [])

    def test_tags_csv_helper(self):
        from discordbot.log_context import tags_csv

        self.assertEqual(tags_csv(["events", "signup"]), "events,signup")
        self.assertEqual(tags_csv([]), "")
        self.assertEqual(tags_csv(["one"]), "one")

    def test_parse_event_id(self):
        from discordbot.log_context import parse_event_id

        self.assertEqual(parse_event_id("event_signup:42"), 42)
        self.assertEqual(parse_event_id("rank_star:7:Herald"), 7)
        self.assertEqual(parse_event_id("screenshot_upload:99:rank"), 99)
        self.assertIsNone(parse_event_id("no_colon"))
        self.assertIsNone(parse_event_id("bad:notanumber"))
        self.assertIsNone(parse_event_id(None))

    def test_span_name(self):
        from discordbot.log_context import span_name

        self.assertEqual(span_name("event_signup:42"), "discord.interaction.event_signup")
        self.assertEqual(span_name("rank_star:7:Herald"), "discord.interaction.rank_star")
        self.assertEqual(span_name(None), "discord.interaction.unknown")
        self.assertEqual(span_name(""), "discord.interaction.unknown")

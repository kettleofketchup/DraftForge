"""Unit tests for discord_log_context CM and InteractionContext."""

from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import MagicMock

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


def _mock_interaction(*, interaction_id=12345, user_id=67890, username="testuser",
                     channel_id=111, guild_id=222, interaction_type="component",
                     custom_id="event_signup:42"):
    """Build a discord.Interaction-like mock."""
    interaction = MagicMock()
    interaction.id = interaction_id
    interaction.user.id = user_id
    interaction.user.name = username
    interaction.channel_id = channel_id
    interaction.guild_id = guild_id
    # Fresh MagicMock for .type so .name assignment isn't shadowed by Mock's name arg
    interaction.type = MagicMock()
    interaction.type.name = interaction_type
    interaction.data = {"custom_id": custom_id}
    return interaction


class DiscordLogContextTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        clear_contextvars()

    async def asyncTearDown(self):
        clear_contextvars()

    async def test_binds_all_contextvars_on_entry(self):
        from discordbot.log_context import discord_log_context

        interaction = _mock_interaction()
        captured: dict | None = None

        async with discord_log_context(interaction, custom_id="event_signup:42"):
            captured = dict(get_contextvars())

        self.assertEqual(captured["interaction_id"], "12345")
        self.assertEqual(captured["discord_user_id"], "67890")
        self.assertEqual(captured["discord_username"], "testuser")
        self.assertEqual(captured["channel_id"], "111")
        self.assertEqual(captured["guild_id"], "222")
        self.assertEqual(captured["custom_id"], "event_signup:42")
        self.assertEqual(captured["event_id"], 42)
        self.assertEqual(captured["tags"], ["events", "signup"])
        self.assertEqual(captured["tags_csv"], "events,signup")
        self.assertEqual(captured["system"], "discord")
        self.assertEqual(captured["subsystem"], "interaction")
        self.assertEqual(captured["interaction_type"], "component")

    async def test_clears_contextvars_on_exit(self):
        from discordbot.log_context import discord_log_context

        async with discord_log_context(_mock_interaction(), custom_id="event_signup:42"):
            pass
        self.assertEqual(get_contextvars(), {})

    async def test_bookend_logs_carry_identity_explicitly(self):
        """Bookend logs MUST pass identity as kwargs so capture_logs sees them."""
        from discordbot.log_context import discord_log_context

        with capture_logs() as logs:
            async with discord_log_context(_mock_interaction(), custom_id="event_signup:42") as ctx:
                ctx.set_outcome("signed_up")
                ctx.add(signup_id=99)

        started = next(log for log in logs if log["event"] == "interaction_started")
        self.assertEqual(started["interaction_id"], "12345")
        self.assertEqual(started["discord_user_id"], "67890")
        self.assertEqual(started["event_id"], 42)
        self.assertEqual(started["tags_csv"], "events,signup")

        finished = next(log for log in logs if log["event"] == "interaction_finished")
        self.assertEqual(finished["interaction_id"], "12345")
        self.assertEqual(finished["outcome"], "signed_up")
        self.assertEqual(finished["signup_id"], 99)
        self.assertEqual(finished["tags_csv"], "events,signup")

    async def test_outcome_defaults_to_ok(self):
        from discordbot.log_context import discord_log_context

        with capture_logs() as logs:
            async with discord_log_context(_mock_interaction(), custom_id="event_signup:42"):
                pass

        finished = [log for log in logs if log["event"] == "interaction_finished"]
        self.assertEqual(len(finished), 1)
        self.assertEqual(finished[0]["outcome"], "ok")

    async def test_explicit_event_id_and_tags_override_derivation(self):
        from discordbot.log_context import discord_log_context

        async with discord_log_context(
            _mock_interaction(),
            custom_id="unknown_prefix:1",
            event_id=999,
            tags=["custom", "override"],
        ):
            ctx_vars = dict(get_contextvars())

        self.assertEqual(ctx_vars["event_id"], 999)
        self.assertEqual(ctx_vars["tags"], ["custom", "override"])
        self.assertEqual(ctx_vars["tags_csv"], "custom,override")

    async def test_interaction_id_none_dropped_not_bound_as_null(self):
        """If interaction.id resolves to None (shouldn't happen but defensively),
        contextvar should not be set to a null string."""
        from discordbot.log_context import discord_log_context

        interaction = _mock_interaction()
        # interaction_id always resolves from interaction.id which is always present,
        # but guild_id can legitimately be None (DM context) — assert None stays None
        interaction.guild_id = None
        interaction.channel_id = None

        async with discord_log_context(interaction, custom_id="event_signup:42"):
            ctx_vars = dict(get_contextvars())

        self.assertIsNone(ctx_vars["guild_id"])
        self.assertIsNone(ctx_vars["channel_id"])
        # And the bookend log lines should still emit without crashing

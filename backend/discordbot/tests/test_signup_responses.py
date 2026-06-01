"""Tests for backend.discordbot.signup_responses (#191, #192)."""

from unittest.mock import AsyncMock, MagicMock, patch
import discord

from django.test import SimpleTestCase

from discordbot.signup_responses import (
    ResponseChannel,
    respond_to_signup_user,
)


def _make_interaction(user_id=12345, response_done=False):
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock()
    interaction.user.id = user_id
    interaction.user.create_dm = AsyncMock()
    interaction.response = MagicMock()
    interaction.response.is_done = MagicMock(return_value=response_done)
    interaction.response.defer = AsyncMock()
    interaction.delete_original_response = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


def _make_forbidden(code):
    response = MagicMock()
    response.status = 403
    err = discord.Forbidden(response, f"code={code}")
    err.code = code
    return err


class RespondToSignupUserDMSuccessTest(SimpleTestCase):
    async def test_dm_path_defers_with_thinking_then_sends_then_deletes_placeholder(self):
        """Regression guard for the signup-post-deletion bug.

        For component (button) interactions, `defer(ephemeral=True)` WITHOUT
        `thinking=True` issues DEFERRED_MESSAGE_UPDATE (type 6), making
        `@original` resolve to the SOURCE message (the public signup post).
        `delete_original_response()` then deletes the signup post.

        `thinking=True` switches to DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE
        (type 5), creating an ephemeral placeholder. `@original` is the
        placeholder, and the subsequent delete only clears that.
        """
        interaction = _make_interaction()
        dm_channel = AsyncMock()
        dm_channel.send = AsyncMock()
        interaction.user.create_dm.return_value = dm_channel

        result = await respond_to_signup_user(interaction, content="hi")

        interaction.response.defer.assert_awaited_once_with(
            ephemeral=True, thinking=True
        )
        interaction.user.create_dm.assert_awaited_once()
        dm_channel.send.assert_awaited_once_with(content="hi", embed=None, view=None)
        interaction.delete_original_response.assert_awaited_once()
        interaction.followup.send.assert_not_called()
        self.assertEqual(result, ResponseChannel.DM)

    async def test_skips_defer_when_response_already_done(self):
        interaction = _make_interaction(response_done=True)
        dm_channel = AsyncMock()
        interaction.user.create_dm.return_value = dm_channel

        await respond_to_signup_user(interaction, content="hi")
        interaction.response.defer.assert_not_called()

    async def test_delete_original_not_found_does_not_break_dm_success(self):
        """delete_original_response can raise NotFound if the placeholder is
        already gone; cleanup is best-effort and the DM has already landed."""
        interaction = _make_interaction()
        dm_channel = AsyncMock()
        interaction.user.create_dm.return_value = dm_channel
        interaction.delete_original_response.side_effect = discord.NotFound(
            MagicMock(status=404), "not found"
        )
        result = await respond_to_signup_user(interaction, content="hi")
        self.assertEqual(result, ResponseChannel.DM)

    async def test_other_http_errors_on_delete_propagate(self):
        """We narrowed the except to NotFound only — a 403/5xx on delete should
        surface, not be silently swallowed (it would have masked the signup-
        post-deletion bug otherwise)."""
        interaction = _make_interaction()
        dm_channel = AsyncMock()
        interaction.user.create_dm.return_value = dm_channel
        interaction.delete_original_response.side_effect = discord.HTTPException(
            MagicMock(status=500), "server error"
        )
        with self.assertRaises(discord.HTTPException):
            await respond_to_signup_user(interaction, content="hi")


class RespondToSignupUserDMDisabledTest(SimpleTestCase):
    async def test_50007_falls_back_to_ephemeral_with_user_mention(self):
        interaction = _make_interaction()
        dm_channel = AsyncMock()
        dm_channel.send = AsyncMock(side_effect=_make_forbidden(50007))
        interaction.user.create_dm.return_value = dm_channel

        result = await respond_to_signup_user(interaction, content="please reply")

        interaction.followup.send.assert_awaited_once()
        kwargs = interaction.followup.send.await_args.kwargs
        self.assertIn("<@12345>", kwargs["content"])
        self.assertIn("please reply", kwargs["content"])
        self.assertTrue(kwargs["ephemeral"])
        self.assertEqual(result, ResponseChannel.EPHEMERAL)


class RespondToSignupUserNoViewFallbackTest(SimpleTestCase):
    async def test_forbidden_fallback_with_no_view_does_not_raise_typeerror(self):
        """#268 bug 1: DM-disabled + no view/embed must fall back cleanly.

        discord.py's Webhook.send (the followup.send path) rejects a literal
        None view (None is not MISSING and lacks __discord_ui_view__). The
        fallback must pass MISSING, not None. The DM path (Messageable.send)
        tolerates None, so only the followup is affected.
        """
        interaction = _make_interaction(user_id=999)
        dm_channel = AsyncMock()
        dm_channel.send = AsyncMock(side_effect=_make_forbidden(50007))
        interaction.user.create_dm.return_value = dm_channel

        # Mirror Webhook.send: reject a literal None view/embed.
        def _send(*args, **kwargs):
            if kwargs.get("view", discord.utils.MISSING) is None:
                raise TypeError(
                    "expected view parameter to be of type View not NoneType"
                )
            if kwargs.get("embed", discord.utils.MISSING) is None:
                raise TypeError(
                    "expected embed parameter to be of type Embed not NoneType"
                )
        interaction.followup.send = AsyncMock(side_effect=_send)

        channel = await respond_to_signup_user(interaction, content="✅ You're signed up!")

        self.assertEqual(channel, ResponseChannel.EPHEMERAL)
        interaction.followup.send.assert_awaited_once()
        kwargs = interaction.followup.send.await_args.kwargs
        self.assertTrue(kwargs["ephemeral"])
        self.assertTrue(kwargs["content"].startswith("<@999>"))


class RespondToSignupUserOtherForbiddenTest(SimpleTestCase):
    async def test_non_50007_forbidden_reraises(self):
        interaction = _make_interaction()
        dm_channel = AsyncMock()
        dm_channel.send = AsyncMock(side_effect=_make_forbidden(50001))
        interaction.user.create_dm.return_value = dm_channel

        with self.assertRaises(discord.Forbidden):
            await respond_to_signup_user(interaction, content="x")

        interaction.followup.send.assert_not_called()


class RespondToSignupUserLoggingTest(SimpleTestCase):
    async def test_dm_success_logs_signup_response_sent(self):
        interaction = _make_interaction()
        dm_channel = AsyncMock()
        interaction.user.create_dm.return_value = dm_channel

        with patch("discordbot.signup_responses.log") as mock_log:
            await respond_to_signup_user(interaction, content="hi")

        events = [call.args[0] for call in mock_log.info.call_args_list]
        self.assertIn("signup_interaction_deferred", events)
        self.assertIn("signup_interaction_placeholder_deleted", events)
        self.assertIn("signup_response_sent", events)

        sent_call = next(
            c for c in mock_log.info.call_args_list
            if c.args[0] == "signup_response_sent"
        )
        kwargs = sent_call.kwargs
        self.assertEqual(kwargs["system"], "discord")
        self.assertEqual(kwargs["subsystem"], "interaction")
        self.assertEqual(kwargs["tags"], ["events", "signup"])
        self.assertEqual(kwargs["tags_csv"], "events,signup")
        self.assertEqual(kwargs["channel"], "dm")
        self.assertFalse(kwargs["fallback_to_ephemeral"])
        self.assertEqual(kwargs["user_id"], 12345)

    async def test_other_forbidden_logs_signup_response_failed(self):
        interaction = _make_interaction()
        dm_channel = AsyncMock()
        dm_channel.send = AsyncMock(side_effect=_make_forbidden(50001))
        interaction.user.create_dm.return_value = dm_channel

        with patch("discordbot.signup_responses.log") as mock_log:
            with self.assertRaises(discord.Forbidden):
                await respond_to_signup_user(interaction, content="x")

        mock_log.error.assert_called_once()
        kwargs = mock_log.error.call_args.kwargs
        self.assertEqual(kwargs["system"], "discord")
        self.assertEqual(kwargs["subsystem"], "interaction")
        self.assertEqual(kwargs["tags"], ["events", "signup"])
        self.assertEqual(kwargs["tags_csv"], "events,signup")
        self.assertIn("error", kwargs)

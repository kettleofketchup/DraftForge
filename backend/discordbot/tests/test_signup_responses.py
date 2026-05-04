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
    async def test_dm_path_defers_then_sends_then_deletes_original(self):
        interaction = _make_interaction()
        dm_channel = AsyncMock()
        dm_channel.send = AsyncMock()
        interaction.user.create_dm.return_value = dm_channel

        result = await respond_to_signup_user(interaction, content="hi")

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
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

    async def test_delete_original_failure_does_not_break_dm_success(self):
        """delete_original_response can raise NotFound/HTTPException; cleanup is best-effort."""
        interaction = _make_interaction()
        dm_channel = AsyncMock()
        interaction.user.create_dm.return_value = dm_channel
        interaction.delete_original_response.side_effect = discord.NotFound(
            MagicMock(status=404), "not found"
        )
        # Should not raise — DM already succeeded.
        result = await respond_to_signup_user(interaction, content="hi")
        self.assertEqual(result, ResponseChannel.DM)


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

        mock_log.info.assert_called_once()
        kwargs = mock_log.info.call_args.kwargs
        self.assertEqual(kwargs["system"], "events")
        self.assertEqual(kwargs["subsystem"], "discord")
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
        self.assertEqual(kwargs["system"], "events")
        self.assertEqual(kwargs["subsystem"], "discord")
        self.assertIn("error", kwargs)

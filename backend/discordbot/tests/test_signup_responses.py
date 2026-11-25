"""Tests for backend.discordbot.signup_responses (#191, #192)."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from django.test import SimpleTestCase

from discordbot.dm_ledger import ClaimResult
from discordbot.models import DMStatus
from discordbot.signup_responses import (
    ResponseChannel,
    respond_to_signup_user,
)

INTERACTION_ID = 4242
EVENT_ID = 31
GRANTED = ClaimResult(
    id=7, granted=True, status=DMStatus.PENDING, attempts=1, created=True
)


def _make_interaction(user_id=12345, response_done=False):
    interaction = MagicMock(spec=discord.Interaction)
    interaction.id = INTERACTION_ID
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


class _LedgerMixin(SimpleTestCase):
    claim_result: ClaimResult | None = GRANTED

    def setUp(self) -> None:
        super().setUp()
        self.claim = self._patch("claim_dm", return_value=self.claim_result)
        self.mark = self._patch("mark_dm_sending", return_value=True)
        self.finalize = self._patch("finalize_dm", return_value=True)

    def _patch(self, name: str, **kwargs: Any) -> MagicMock:
        patcher = patch(f"discordbot.gateway_dm.{name}", **kwargs)
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock


async def _respond(interaction: MagicMock, **kwargs: Any) -> ResponseChannel:
    kwargs.setdefault("event_id", EVENT_ID)
    kwargs.setdefault("result", "signed_up")
    return await respond_to_signup_user(interaction, **kwargs)


def _dm_channel() -> AsyncMock:
    channel = AsyncMock()
    channel.id = 555
    channel.send = AsyncMock(return_value=MagicMock(id=777))
    return channel


def _make_forbidden(code):
    response = MagicMock()
    response.status = 403
    err = discord.Forbidden(response, f"code={code}")
    err.code = code
    return err


class RespondToSignupUserDMSuccessTest(_LedgerMixin):
    async def test_dm_path_defers_with_thinking_then_sends_then_deletes_placeholder(
        self,
    ):
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
        dm_channel = _dm_channel()
        interaction.user.create_dm.return_value = dm_channel

        result = await _respond(interaction, content="hi")

        interaction.response.defer.assert_awaited_once_with(
            ephemeral=True, thinking=True
        )
        interaction.user.create_dm.assert_awaited_once()
        dm_channel.send.assert_awaited_once()
        sent = dm_channel.send.await_args.kwargs
        self.assertEqual(
            (sent["content"], sent["embed"], sent["view"]), ("hi", None, None)
        )
        interaction.delete_original_response.assert_awaited_once()
        interaction.followup.send.assert_not_called()
        self.assertEqual(result, ResponseChannel.DM)

    async def test_skips_defer_when_response_already_done(self):
        interaction = _make_interaction(response_done=True)
        dm_channel = _dm_channel()
        interaction.user.create_dm.return_value = dm_channel

        await _respond(interaction, content="hi")
        interaction.response.defer.assert_not_called()

    async def test_delete_original_not_found_does_not_break_dm_success(self):
        """delete_original_response can raise NotFound if the placeholder is
        already gone; cleanup is best-effort and the DM has already landed."""
        interaction = _make_interaction()
        dm_channel = _dm_channel()
        interaction.user.create_dm.return_value = dm_channel
        interaction.delete_original_response.side_effect = discord.NotFound(
            MagicMock(status=404), "not found"
        )
        result = await _respond(interaction, content="hi")
        self.assertEqual(result, ResponseChannel.DM)

    async def test_other_http_errors_on_delete_propagate(self):
        """We narrowed the except to NotFound only — a 403/5xx on delete should
        surface, not be silently swallowed (it would have masked the signup-
        post-deletion bug otherwise)."""
        interaction = _make_interaction()
        dm_channel = _dm_channel()
        interaction.user.create_dm.return_value = dm_channel
        interaction.delete_original_response.side_effect = discord.HTTPException(
            MagicMock(status=500), "server error"
        )
        with self.assertRaises(discord.HTTPException):
            await _respond(interaction, content="hi")


class RespondToSignupUserDMDisabledTest(_LedgerMixin):
    async def test_50007_falls_back_to_ephemeral_with_user_mention(self):
        interaction = _make_interaction()
        dm_channel = _dm_channel()
        dm_channel.send = AsyncMock(side_effect=_make_forbidden(50007))
        interaction.user.create_dm.return_value = dm_channel

        result = await _respond(interaction, content="please reply")

        interaction.followup.send.assert_awaited_once()
        kwargs = interaction.followup.send.await_args.kwargs
        self.assertIn("<@12345>", kwargs["content"])
        self.assertIn("please reply", kwargs["content"])
        self.assertTrue(kwargs["ephemeral"])
        self.assertEqual(result, ResponseChannel.EPHEMERAL)


class RespondToSignupUserNoViewFallbackTest(_LedgerMixin):
    async def test_forbidden_fallback_with_no_view_does_not_raise_typeerror(self):
        """DM-disabled + no view/embed must fall back cleanly (#268).

        discord.py's Webhook.send (the followup.send path) rejects a literal
        None view (None is not MISSING and lacks __discord_ui_view__). The
        fallback must pass MISSING, not None. The DM path (Messageable.send)
        tolerates None, so only the followup is affected.
        """
        interaction = _make_interaction(user_id=999)
        dm_channel = _dm_channel()
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

        channel = await _respond(interaction, content="✅ You're signed up!")

        self.assertEqual(channel, ResponseChannel.EPHEMERAL)
        interaction.followup.send.assert_awaited_once()
        kwargs = interaction.followup.send.await_args.kwargs
        self.assertTrue(kwargs["ephemeral"])
        self.assertTrue(kwargs["content"].startswith("<@999>"))


class RespondToSignupUserOtherForbiddenTest(_LedgerMixin):
    async def test_non_50007_forbidden_falls_back_to_ephemeral(self):
        interaction = _make_interaction()
        dm_channel = _dm_channel()
        dm_channel.send = AsyncMock(side_effect=_make_forbidden(50001))
        interaction.user.create_dm.return_value = dm_channel

        channel = await _respond(interaction, content="x")

        self.assertEqual(channel, ResponseChannel.EPHEMERAL)
        kwargs = interaction.followup.send.await_args.kwargs
        self.assertEqual(kwargs["content"], "<@12345> x")
        self.assertTrue(kwargs["ephemeral"])
        self.assertEqual(self.finalize.call_args.args[1].status, "failed")


class RespondToSignupUserLedgerTest(_LedgerMixin):
    claim_result = None

    async def test_ledger_unavailable_falls_back_to_ephemeral_mention(self):
        interaction = _make_interaction()

        channel = await _respond(interaction, content="saved")

        self.assertEqual(channel, ResponseChannel.EPHEMERAL)
        interaction.user.create_dm.assert_not_awaited()
        kwargs = interaction.followup.send.await_args.kwargs
        self.assertEqual(kwargs["content"], "<@12345> saved")
        self.assertTrue(kwargs["ephemeral"])
        interaction.delete_original_response.assert_not_awaited()


class RespondToSignupUserKeyTest(_LedgerMixin):
    async def test_dm_uses_signup_confirmation_key(self):
        interaction = _make_interaction()
        interaction.user.create_dm.return_value = _dm_channel()
        view = MagicMock(spec=discord.ui.View)

        await _respond(
            interaction, content="hi", view=view, event_id=88, result="tentative"
        )

        body = self.claim.call_args.args[0]
        self.assertEqual(body.kind, "signup_confirmation")
        self.assertEqual(
            body.idempotency_key, f"signup_confirmation:interaction:{INTERACTION_ID}"
        )
        self.assertEqual((body.subject_type, body.subject_id), ("event", 88))
        self.assertEqual(
            body.context, {"result": "tentative", "interaction_id": INTERACTION_ID}
        )
        self.assertTrue(body.has_components)
        self.assertEqual(body.claim_token, str(INTERACTION_ID))

    async def test_duplicate_sends_nothing(self):
        self.claim.return_value = ClaimResult(
            id=7, granted=False, status=DMStatus.SENT, attempts=0, created=False
        )
        interaction = _make_interaction()

        channel = await _respond(interaction, content="hi")

        self.assertEqual(channel, ResponseChannel.DM)
        interaction.user.create_dm.assert_not_awaited()
        interaction.followup.send.assert_not_called()


class RespondToSignupUserLoggingTest(_LedgerMixin):
    async def test_dm_success_logs_signup_response_sent(self):
        interaction = _make_interaction()
        dm_channel = _dm_channel()
        interaction.user.create_dm.return_value = dm_channel

        with patch("discordbot.signup_responses.log") as mock_log:
            await _respond(interaction, content="hi")

        events = [call.args[0] for call in mock_log.info.call_args_list]
        self.assertIn("signup_interaction_deferred", events)
        self.assertIn("signup_interaction_placeholder_deleted", events)
        self.assertIn("signup_response_sent", events)

        sent_call = next(
            c
            for c in mock_log.info.call_args_list
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
        dm_channel = _dm_channel()
        dm_channel.send = AsyncMock(side_effect=_make_forbidden(50001))
        interaction.user.create_dm.return_value = dm_channel

        with patch("discordbot.signup_responses.log") as mock_log:
            await _respond(interaction, content="x")

        mock_log.error.assert_called_once()
        kwargs = mock_log.error.call_args.kwargs
        self.assertEqual(kwargs["system"], "discord")
        self.assertEqual(kwargs["subsystem"], "interaction")
        self.assertEqual(kwargs["tags"], ["events", "signup"])
        self.assertEqual(kwargs["tags_csv"], "events,signup")
        self.assertEqual(kwargs["dm_outcome"], "failed")

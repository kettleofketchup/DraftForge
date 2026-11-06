"""Component interaction routing in discordbot.interaction_router."""

from collections.abc import AsyncIterator
from contextlib import ExitStack, asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from structlog.testing import capture_logs

from discordbot import interaction_router
from discordbot.custom_ids import PosSelectId

MOD = "discordbot.interaction_router"
BUTTONS = ("SignupButton", "TentativeButton", "DeclineButton", "NotifyButton")
STALE_MSG = "❌ This menu is out of date."

MALFORMED: list[tuple[str, str]] = [
    ("event_signup:abc", "SignupId"),
    ("event_tentative:abc", "TentativeId"),
    ("event_decline:abc", "DeclineId"),
    ("event_notify:abc", "NotifyId"),
    ("pos_select_x:5", "PosSelectId"),
    ("pos_select_1", "PosSelectId"),
]


class _Harness:
    def __init__(self, stack: ExitStack, *, is_done: bool = False) -> None:
        self.ctx = MagicMock()
        ctx = self.ctx

        @asynccontextmanager
        async def fake_log_context(*_a: Any, **_kw: Any) -> AsyncIterator[MagicMock]:
            yield ctx

        stack.enter_context(patch(f"{MOD}.discord_log_context", fake_log_context))
        self.buttons: dict[str, MagicMock] = {
            name: stack.enter_context(patch(f"{MOD}.{name}", autospec=True))
            for name in BUTTONS
        }
        self.provider = SimpleNamespace(
            bare_select_ids=(PosSelectId,), dispatch_bare_select=AsyncMock()
        )
        stack.enter_context(
            patch(f"{MOD}.iter_component_providers", return_value=[self.provider])
        )
        self.interaction = MagicMock()
        self.interaction.response.is_done = MagicMock(return_value=is_done)
        self.interaction.response.send_message = AsyncMock()


class RouteComponentInteractionTests(IsolatedAsyncioTestCase):
    async def test_malformed_ids_are_logged_and_rejected(self) -> None:
        for custom_id, codec_name in MALFORMED:
            with self.subTest(custom_id=custom_id), ExitStack() as stack:
                h = _Harness(stack)
                with capture_logs() as logs:
                    await interaction_router.route_component_interaction(
                        h.interaction, custom_id
                    )
                failures = [e for e in logs if e["event"] == "custom_id_decode_failed"]
                self.assertEqual(len(failures), 1)
                self.assertEqual(failures[0]["codec"], codec_name)
                self.assertEqual(failures[0]["system"], "discord")
                self.assertEqual(failures[0]["subsystem"], "interaction")
                self.assertTrue(failures[0]["error"])
                h.ctx.set_outcome.assert_called_with("rejected_bad_custom_id")
                h.interaction.response.send_message.assert_awaited_once_with(
                    STALE_MSG, ephemeral=True
                )
                for button in h.buttons.values():
                    button.assert_not_called()
                h.provider.dispatch_bare_select.assert_not_awaited()

    async def test_valid_pos_select_dispatches_to_provider(self) -> None:
        with ExitStack() as stack:
            h = _Harness(stack)
            await interaction_router.route_component_interaction(
                h.interaction, "pos_select_2:7"
            )
            h.provider.dispatch_bare_select.assert_awaited_once_with(
                h.interaction, PosSelectId(event_id=7, slot=2)
            )
            h.interaction.response.send_message.assert_not_awaited()

    async def test_valid_signup_invokes_button_callback(self) -> None:
        with ExitStack() as stack:
            h = _Harness(stack)
            await interaction_router.route_component_interaction(
                h.interaction, "event_signup:3"
            )
            signup = h.buttons["SignupButton"]
            signup.assert_called_once_with(3)
            signup.return_value.callback.assert_awaited_once_with(h.interaction)
            h.interaction.response.send_message.assert_not_awaited()

    async def test_already_acknowledged_interaction_is_not_replied(self) -> None:
        with ExitStack() as stack:
            h = _Harness(stack, is_done=True)
            with capture_logs() as logs:
                await interaction_router.route_component_interaction(
                    h.interaction, "event_signup:abc"
                )
            self.assertIn("custom_id_decode_failed", [e["event"] for e in logs])
            h.interaction.response.send_message.assert_not_awaited()

    async def test_reply_failure_propagates_after_logging(self) -> None:
        with ExitStack() as stack:
            h = _Harness(stack)
            h.interaction.response.send_message.side_effect = discord.HTTPException(
                MagicMock(status=404), "expired"
            )
            with capture_logs() as logs:
                with self.assertRaises(discord.HTTPException):
                    await interaction_router.route_component_interaction(
                        h.interaction, "event_decline:abc"
                    )
            self.assertIn("custom_id_decode_failed", [e["event"] for e in logs])

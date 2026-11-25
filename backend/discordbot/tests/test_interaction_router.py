"""Component interaction routing in discordbot.interaction_router."""

import asyncio
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


class DMClickHookTests(IsolatedAsyncioTestCase):
    def _interaction(self, *, guild_id: int | None) -> MagicMock:
        interaction = MagicMock()
        interaction.guild_id = guild_id
        interaction.message.id = 111
        interaction.user.id = 222
        interaction.response.is_done = MagicMock(return_value=True)
        interaction.response.send_message = AsyncMock()
        return interaction

    async def _route(self, interaction: MagicMock, custom_id: str) -> MagicMock:
        with ExitStack() as stack:
            _Harness(stack)
            record = stack.enter_context(patch(f"{MOD}.record_dm_click"))
            await interaction_router.route_component_interaction(interaction, custom_id)
            await asyncio.gather(*list(interaction_router._click_tasks))
        return record

    async def test_dm_click_schedules_record(self) -> None:
        record = await self._route(self._interaction(guild_id=None), "event_signup:5")
        record.assert_called_once_with("111", "222")

    async def test_guild_click_does_not_record(self) -> None:
        record = await self._route(self._interaction(guild_id=9), "event_signup:5")
        record.assert_not_called()

    async def test_lr_click_not_recorded_by_hook(self) -> None:
        record = await self._route(self._interaction(guild_id=None), "lr:1:2:3")
        record.assert_not_called()

    async def test_click_without_message_not_recorded(self) -> None:
        interaction = self._interaction(guild_id=None)
        interaction.message = None
        record = await self._route(interaction, "event_signup:5")
        record.assert_not_called()

    async def test_record_failure_is_logged_not_raised(self) -> None:
        with ExitStack() as stack:
            _Harness(stack)
            stack.enter_context(
                patch(f"{MOD}.record_dm_click", side_effect=RuntimeError("down"))
            )
            with capture_logs() as logs:
                await interaction_router.route_component_interaction(
                    self._interaction(guild_id=None), "event_signup:5"
                )
                await asyncio.gather(*list(interaction_router._click_tasks))
        failed = [e for e in logs if e["event"] == "dm_click_record_failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["subsystem"], "dm")

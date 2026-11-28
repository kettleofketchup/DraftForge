"""Gateway handling of leadership review DM button clicks."""

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import ExitStack, asynccontextmanager
from typing import Any
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from discordbot import leadership_gateway
from discordbot.custom_ids import LeadershipScoreId
from discordbot.internal_client.leadership_actions import SAVE_FAILED
from discordbot.schemas import ClickResult, ReviewClickBody

MOD = "discordbot.leadership_gateway"
PAYLOAD: dict[str, Any] = {"flags": 1 << 15, "components": [{"type": 10}]}


def _interaction(message_id: int = 111) -> MagicMock:
    interaction = MagicMock()
    interaction.id = 444
    interaction.application_id = 555
    interaction.token = "tok"
    interaction.channel_id = 222
    interaction.user.id = 333
    interaction.message.id = message_id
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.client.http.request = AsyncMock()
    return interaction


class LeadershipGatewayTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)

        @asynccontextmanager
        async def fake_log_context(*_a: Any, **_kw: Any) -> AsyncIterator[MagicMock]:
            yield MagicMock()

        self.stack.enter_context(patch(f"{MOD}.discord_log_context", fake_log_context))
        self.review_click = self.stack.enter_context(patch(f"{MOD}.review_click"))
        self.cid = LeadershipScoreId(snapshot_id=7, trait_id=8, score=4)

    async def test_click_defers_then_patches_original(self) -> None:
        interaction = _interaction()
        calls: list[str] = []
        interaction.response.defer.side_effect = lambda *a, **k: calls.append("defer")
        interaction.client.http.request.side_effect = lambda *a, **k: calls.append(
            "patch"
        )
        self.review_click.return_value = ClickResult(message=PAYLOAD)
        await leadership_gateway.handle_review_click(interaction, self.cid)
        self.assertEqual(calls, ["defer", "patch"])
        interaction.response.defer.assert_awaited_once_with()
        route = interaction.client.http.request.call_args.args[0]
        self.assertEqual(route.method, "PATCH")
        self.assertTrue(route.url.endswith("/webhooks/555/tok/messages/@original"))
        self.assertEqual(
            interaction.client.http.request.call_args.kwargs["json"],
            {**PAYLOAD, "allowed_mentions": {"parse": []}},
        )
        body: ReviewClickBody = self.review_click.call_args.args[0]
        self.assertEqual(
            body.model_dump(),
            {
                "discord_user_id": "333",
                "discord_message_id": "111",
                "discord_channel_id": "222",
                "interaction_id": "444",
                "snapshot_id": 7,
                "trait_id": 8,
                "score": 4,
            },
        )
        interaction.followup.send.assert_not_awaited()

    async def test_click_ephemeral_refusal(self) -> None:
        interaction = _interaction()
        self.review_click.return_value = ClickResult(ephemeral="Nope.")
        await leadership_gateway.handle_review_click(interaction, self.cid)
        interaction.followup.send.assert_awaited_once_with("Nope.", ephemeral=True)
        interaction.client.http.request.assert_not_awaited()

    async def test_click_rerender_and_ephemeral(self) -> None:
        interaction = _interaction()
        self.review_click.return_value = ClickResult(
            message=PAYLOAD, ephemeral="Closed."
        )
        await leadership_gateway.handle_review_click(interaction, self.cid)
        interaction.client.http.request.assert_awaited_once()
        interaction.followup.send.assert_awaited_once_with("Closed.", ephemeral=True)

    async def test_click_backend_unreachable_ephemeral(self) -> None:
        interaction = _interaction()
        self.review_click.return_value = None
        await leadership_gateway.handle_review_click(interaction, self.cid)
        interaction.response.defer.assert_awaited_once()
        interaction.followup.send.assert_awaited_once_with(SAVE_FAILED, ephemeral=True)
        interaction.client.http.request.assert_not_awaited()

    async def test_patch_failure_is_logged_not_raised(self) -> None:
        interaction = _interaction()
        interaction.client.http.request.side_effect = discord.HTTPException(
            MagicMock(status=404), "unknown webhook"
        )
        self.review_click.return_value = ClickResult(message=PAYLOAD)
        await leadership_gateway.handle_review_click(interaction, self.cid)
        interaction.followup.send.assert_not_awaited()

    async def test_two_concurrent_clicks_patch_in_order(self) -> None:
        def slow_first(body: ReviewClickBody) -> ClickResult:
            if body.score == 1:
                time.sleep(0.3)
            return ClickResult(message={"flags": 1 << 15, "components": [body.score]})

        self.review_click.side_effect = slow_first
        interaction = _interaction()
        patched: list[int] = []
        interaction.client.http.request.side_effect = lambda *a, **k: patched.append(
            k["json"]["components"][0]
        )
        first = asyncio.create_task(
            leadership_gateway.handle_review_click(
                interaction, LeadershipScoreId(snapshot_id=7, trait_id=8, score=1)
            )
        )
        for _ in range(5):
            await asyncio.sleep(0)
        second = asyncio.create_task(
            leadership_gateway.handle_review_click(
                interaction, LeadershipScoreId(snapshot_id=7, trait_id=9, score=2)
            )
        )
        await asyncio.gather(first, second)
        self.assertEqual(patched, [1, 2])
        self.assertEqual(
            [c.args[0].score for c in self.review_click.call_args_list], [1, 2]
        )

    async def test_lock_entries_released(self) -> None:
        self.review_click.return_value = ClickResult(message=PAYLOAD)
        await asyncio.gather(
            leadership_gateway.handle_review_click(_interaction(111), self.cid),
            leadership_gateway.handle_review_click(_interaction(111), self.cid),
            leadership_gateway.handle_review_click(_interaction(112), self.cid),
        )
        self.assertEqual(leadership_gateway._message_locks, {})
        self.assertEqual(leadership_gateway._lock_holders, {})

    async def test_lock_released_when_backend_raises(self) -> None:
        self.review_click.side_effect = RuntimeError("boom")
        with self.assertRaises(RuntimeError):
            await leadership_gateway.handle_review_click(_interaction(), self.cid)
        self.assertEqual(leadership_gateway._message_locks, {})

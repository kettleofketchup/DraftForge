"""Gateway handler for leadership review DM buttons (``lr:`` custom ids).

No ORM: the click is applied by the backend over the internal API, then the
clicked message is re-rendered with a raw PATCH of ``@original``.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import discord
from asgiref.sync import sync_to_async
from discord.http import Route
from pydantic import ValidationError

from discordbot.custom_ids import LeadershipScoreId
from discordbot.internal_client.leadership_actions import SAVE_FAILED, review_click
from discordbot.log_context import discord_log_context
from discordbot.schemas import ReviewClickBody
from telemetry.logging import get_logger

log = get_logger(__name__)

_LOG = {"system": "discord", "subsystem": "leadership"}
_message_locks: dict[int, asyncio.Lock] = {}
_lock_holders: dict[int, int] = {}


@asynccontextmanager
async def _message_lock(message_id: int) -> AsyncIterator[None]:
    lock = _message_locks.setdefault(message_id, asyncio.Lock())
    _lock_holders[message_id] = _lock_holders.get(message_id, 0) + 1
    try:
        async with lock:
            yield
    finally:
        _lock_holders[message_id] -= 1
        if not _lock_holders[message_id]:
            del _lock_holders[message_id]
            _message_locks.pop(message_id, None)


async def edit_original_v2(
    interaction: discord.Interaction, payload: dict[str, Any]
) -> None:
    route = Route(
        "PATCH",
        "/webhooks/{webhook_id}/{webhook_token}/messages/@original",
        webhook_id=interaction.application_id,
        webhook_token=interaction.token,
    )
    await interaction.client.http.request(
        route,
        json={
            "flags": payload["flags"],
            "components": payload["components"],
            "allowed_mentions": {"parse": []},
        },
    )


def _body(
    interaction: discord.Interaction, message: discord.Message, cid: LeadershipScoreId
) -> ReviewClickBody | None:
    try:
        return ReviewClickBody(
            discord_user_id=str(interaction.user.id),
            discord_message_id=str(message.id),
            discord_channel_id=str(interaction.channel_id or message.channel.id),
            interaction_id=str(interaction.id),
            snapshot_id=cid.snapshot_id,
            trait_id=cid.trait_id,
            score=cid.score,
        )
    except ValidationError:
        return None


async def handle_review_click(
    interaction: discord.Interaction, cid: LeadershipScoreId
) -> None:
    async with discord_log_context(interaction) as ctx:
        await interaction.response.defer()
        message = interaction.message
        body = _body(interaction, message, cid) if message is not None else None
        if message is None or body is None:
            ctx.set_outcome("bad_interaction")
            await interaction.followup.send(SAVE_FAILED, ephemeral=True)
            return
        async with _message_lock(message.id):
            result = await sync_to_async(review_click, thread_sensitive=False)(body)
            if result is None:
                ctx.set_outcome("backend_unavailable")
                await interaction.followup.send(SAVE_FAILED, ephemeral=True)
                return
            if result.message is not None:
                try:
                    await edit_original_v2(interaction, result.message)
                except discord.HTTPException as exc:
                    log.warning(
                        "leadership_review_rerender_failed",
                        **_LOG,
                        http_status_code=exc.status,
                        error_code=exc.code,
                    )
            if result.ephemeral:
                ctx.set_outcome("refused")
                await interaction.followup.send(result.ephemeral, ephemeral=True)

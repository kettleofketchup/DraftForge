"""Route component interactions that discord.py's view store does not own."""

from __future__ import annotations

import asyncio

import discord
from asgiref.sync import sync_to_async
from django.conf import settings

from discordbot.activity_ids import decode_draft_launch
from discordbot.activity_launch_gateway import handle_draft_launch
from discordbot.components import (
    DeclineButton,
    NotifyButton,
    SignupButton,
    TentativeButton,
)
from discordbot.components.registry import iter_component_providers
from discordbot.custom_ids import (
    LEADERSHIP_REVIEW_PREFIX,
    CustomId,
    DeclineId,
    LeadershipScoreId,
    NotifyId,
    SignupId,
    TentativeId,
)
from discordbot.internal_client.dm_ledger import record_dm_click
from discordbot.leadership_gateway import handle_review_click
from discordbot.log_context import discord_log_context
from telemetry.logging import get_logger

log = get_logger(__name__)

STALE_COMPONENT_MESSAGE = "❌ This menu is out of date."
_click_tasks: set[asyncio.Task[None]] = set()


async def _record_click(discord_message_id: str, discord_user_id: str) -> None:
    try:
        await sync_to_async(record_dm_click, thread_sensitive=False)(
            discord_message_id, discord_user_id
        )
    except Exception:
        log.warning(
            "dm_click_record_failed", system="discord", subsystem="dm", exc_info=True
        )


def _schedule_dm_click(interaction: discord.Interaction, custom_id: str) -> None:
    message = interaction.message
    if (
        interaction.guild_id is not None
        or message is None
        or custom_id.startswith(LEADERSHIP_REVIEW_PREFIX)
    ):
        return
    task = asyncio.create_task(_record_click(str(message.id), str(interaction.user.id)))
    _click_tasks.add(task)
    task.add_done_callback(_click_tasks.discard)


async def _reject_bad_custom_id(
    interaction: discord.Interaction,
    custom_id: str,
    codec: type[CustomId] | type[LeadershipScoreId],
    exc: ValueError,
) -> None:
    async with discord_log_context(interaction, custom_id=custom_id) as ctx:
        ctx.set_outcome("rejected_bad_custom_id")
        log.warning(
            "custom_id_decode_failed",
            system="discord",
            subsystem="interaction",
            codec=codec.__name__,
            error=str(exc),
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(
                STALE_COMPONENT_MESSAGE, ephemeral=True
            )


async def route_component_interaction(
    interaction: discord.Interaction, custom_id: str
) -> None:
    _schedule_dm_click(interaction, custom_id)

    if LeadershipScoreId.matches(custom_id):
        try:
            score = LeadershipScoreId.decode(custom_id)
        except ValueError as exc:
            await _reject_bad_custom_id(interaction, custom_id, LeadershipScoreId, exc)
            return
        await handle_review_click(interaction, score)
        return

    if custom_id.startswith("draft_activity:") and custom_id != "draft_activity:launch":
        draft = decode_draft_launch(custom_id)
        if draft is None:
            await interaction.response.send_message(
                "This draft notification is out of date.", ephemeral=True
            )
        else:
            await handle_draft_launch(interaction, *draft)
        return

    if custom_id == "draft_activity:launch":
        # The gateway process has no ORM. Channel resolution happens in Django
        # after the SDK exchanges an OAuth code and verifies the instance.

        if (
            getattr(settings, "DISCORD_ACTIVITY_ENABLED", False)
            and interaction.guild is not None
            and getattr(interaction.channel, "type", None) == discord.ChannelType.voice
        ):
            await interaction.response.launch_activity()
        else:
            await interaction.response.send_message(
                "Launch this button from a configured server voice channel, or use the draft notification to launch in your current voice channel.",
                ephemeral=True,
            )
        return

    # RSVP buttons are posted as raw dicts (discordbot/utils.py), never
    # handed to discord.py as a ui.View, so they are reconstructed here
    # from the typed custom-id on every interaction.
    if SignupId.matches(custom_id):
        try:
            signup = SignupId.decode(custom_id)
        except ValueError as exc:
            await _reject_bad_custom_id(interaction, custom_id, SignupId, exc)
            return
        await SignupButton(signup.event_id).callback(interaction)
    elif TentativeId.matches(custom_id):
        try:
            tentative = TentativeId.decode(custom_id)
        except ValueError as exc:
            await _reject_bad_custom_id(interaction, custom_id, TentativeId, exc)
            return
        await TentativeButton(tentative.event_id).callback(interaction)
    elif DeclineId.matches(custom_id):
        try:
            decline = DeclineId.decode(custom_id)
        except ValueError as exc:
            await _reject_bad_custom_id(interaction, custom_id, DeclineId, exc)
            return
        await DeclineButton(decline.event_id).callback(interaction)
    elif NotifyId.matches(custom_id):
        try:
            notify = NotifyId.decode(custom_id)
        except ValueError as exc:
            await _reject_bad_custom_id(interaction, custom_id, NotifyId, exc)
            return
        await NotifyButton(notify.event_id).callback(interaction)
    else:
        # Game-specific bare ui.Selects (no overridden callback) are the
        # ONLY components routed here — e.g. pos_select_. Every other
        # game component has an overridden callback and self-dispatches
        # via discord.py's in-memory view store; routing those here too
        # caused a 40060 ACK race (the ~200ms internal-client HTTP round
        # trip lets the view dispatch ACK first). Do NOT add a codec
        # whose component has an overridden callback to bare_select_ids.
        for provider in iter_component_providers():
            for id_type in provider.bare_select_ids:
                if id_type.matches(custom_id):
                    try:
                        cid = id_type.decode(custom_id)
                    except ValueError as exc:
                        await _reject_bad_custom_id(
                            interaction, custom_id, id_type, exc
                        )
                        return
                    await provider.dispatch_bare_select(interaction, cid)
                    return

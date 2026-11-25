"""DM-with-ephemeral-fallback helper for signup-flow Discord interactions.

Issues #191, #192: signup messages should land as DMs (persistent, notification-
generating) rather than ephemerals that auto-dismiss after 60 seconds. The DM
goes through the ledger (``discordbot.gateway_dm``). When it is not delivered
(DMs disabled, ledger unreachable, Discord error), fall back to ephemeral and
prefix with <@user_id> so they get a notification badge.

CRITICAL — `thinking=True` on defer for component interactions:

    For a *component* (button) interaction, discord.py's `defer(ephemeral=...)`
    without `thinking=True` issues a `DEFERRED_MESSAGE_UPDATE` (type 6). That
    type does NOT create a new response message — it silently defers an
    *update to the source message* (the message the button lives on), and
    the `ephemeral` flag is ignored. After that, `@original` IS the source
    message, so `delete_original_response()` deletes the public signup post.

    Passing `thinking=True` switches discord.py to
    `DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE` (type 5), creating a fresh
    ephemeral placeholder. Then `@original` is that placeholder and
    `delete_original_response()` cleans up only the placeholder.

    Removing `thinking=True` here will start deleting users' signup posts
    on every button click again. Do not change without re-reading this.
"""

from enum import Enum
from typing import Literal

import discord
from discord.utils import MISSING

from discordbot.dm_keys import signup_confirmation_key
from discordbot.gateway_dm import send_interaction_dm
from discordbot.models import DMKind, DMSubject
from telemetry.logging import get_logger

log = get_logger(__name__)

SignupResult = Literal["signed_up", "tentative", "declined", "screenshot_saved"]


class ResponseChannel(Enum):
    DM = "dm"
    EPHEMERAL = "ephemeral"


def _message_id(interaction: discord.Interaction) -> str | None:
    msg = getattr(interaction, "message", None)
    return str(msg.id) if msg is not None and getattr(msg, "id", None) else None


async def respond_to_signup_user(
    interaction: discord.Interaction,
    *,
    event_id: int,
    result: SignupResult,
    content: str | None = None,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
) -> ResponseChannel:
    """DM the user through the ledger; fall back to an ephemeral <@user> reply."""
    user_id = interaction.user.id
    source_message_id = _message_id(interaction)
    channel_id = (
        str(interaction.channel_id)
        if getattr(interaction, "channel_id", None)
        else None
    )

    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True, thinking=True)
        log.info(
            "signup_interaction_deferred",
            system="discord",
            subsystem="interaction",
            tags=["events", "signup"],
            tags_csv="events,signup",
            user_id=user_id,
            event_id=event_id,
            channel_id=channel_id,
            source_message_id=source_message_id,
        )

    outcome = await send_interaction_dm(
        interaction,
        kind=DMKind.SIGNUP_CONFIRMATION,
        idempotency_key=signup_confirmation_key(interaction_id=interaction.id),
        subject=(DMSubject.EVENT, event_id),
        context={"result": result, "interaction_id": interaction.id},
        content=content,
        embed=embed,
        view=view,
    )

    if outcome in ("sent", "duplicate"):
        try:
            await interaction.delete_original_response()
            log.info(
                "signup_interaction_placeholder_deleted",
                system="discord",
                subsystem="interaction",
                tags=["events", "signup"],
                tags_csv="events,signup",
                user_id=user_id,
                event_id=event_id,
            )
        except discord.NotFound:
            pass
        channel = ResponseChannel.DM
    else:
        if outcome in ("failed", "unknown"):
            log.error(
                "signup_response_failed",
                system="discord",
                subsystem="interaction",
                tags=["events", "signup"],
                tags_csv="events,signup",
                user_id=user_id,
                event_id=event_id,
                channel_id=channel_id,
                source_message_id=source_message_id,
                dm_outcome=outcome,
            )
        mention = f"<@{user_id}>"
        text = f"{mention} {content}".strip() if content else mention
        # Webhook.send (followup) rejects a literal None view/embed: pass MISSING.
        await interaction.followup.send(
            content=text,
            embed=embed if embed is not None else MISSING,
            view=view if view is not None else MISSING,
            ephemeral=True,
        )
        channel = ResponseChannel.EPHEMERAL

    log.info(
        "signup_response_sent",
        system="discord",
        subsystem="interaction",
        tags=["events", "signup"],
        tags_csv="events,signup",
        channel=channel.value,
        fallback_to_ephemeral=(channel == ResponseChannel.EPHEMERAL),
        dm_outcome=outcome,
        user_id=user_id,
        event_id=event_id,
        channel_id=channel_id,
        source_message_id=source_message_id,
    )
    return channel

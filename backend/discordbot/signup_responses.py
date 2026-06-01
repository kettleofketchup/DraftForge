"""DM-with-ephemeral-fallback helper for signup-flow Discord interactions.

Issues #191, #192: signup messages should land as DMs (persistent, notification-
generating) rather than ephemerals that auto-dismiss after 60 seconds. When a
user has DMs disabled (Discord 50007), fall back to ephemeral and prefix with
<@user_id> so they get a notification badge.

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

import discord
from discord.utils import MISSING

from telemetry.logging import get_logger

log = get_logger(__name__)


class ResponseChannel(Enum):
    DM = "dm"
    EPHEMERAL = "ephemeral"


def _message_id(interaction: discord.Interaction) -> str | None:
    msg = getattr(interaction, "message", None)
    return str(msg.id) if msg is not None and getattr(msg, "id", None) else None


async def respond_to_signup_user(
    interaction: discord.Interaction,
    *,
    content: str | None = None,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
    event=None,
) -> ResponseChannel:
    """Try DM → fall back to ephemeral with <@user_id> prefix on Forbidden(50007)."""
    user_id = interaction.user.id
    event_id = getattr(event, "pk", None)
    source_message_id = _message_id(interaction)
    channel_id = (
        str(interaction.channel_id) if getattr(interaction, "channel_id", None) else None
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

    try:
        dm_channel = await interaction.user.create_dm()
        await dm_channel.send(content=content, embed=embed, view=view)
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
    except discord.Forbidden as e:
        if getattr(e, "code", None) == 50007:
            mention = f"<@{user_id}>"
            text = f"{mention} {content}".strip() if content else mention
            # Webhook.send (followup) rejects a literal None view/embed — it is
            # not MISSING and lacks __discord_ui_view__. Pass MISSING instead.
            # (The DM path above is Messageable.send, which tolerates None.)
            await interaction.followup.send(
                content=text,
                embed=embed if embed is not None else MISSING,
                view=view if view is not None else MISSING,
                ephemeral=True,
            )
            channel = ResponseChannel.EPHEMERAL
        else:
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
                error=str(e),
            )
            raise

    log.info(
        "signup_response_sent",
        system="discord",
        subsystem="interaction",
        tags=["events", "signup"],
        tags_csv="events,signup",
        channel=channel.value,
        fallback_to_ephemeral=(channel == ResponseChannel.EPHEMERAL),
        user_id=user_id,
        event_id=event_id,
        channel_id=channel_id,
        source_message_id=source_message_id,
    )
    return channel

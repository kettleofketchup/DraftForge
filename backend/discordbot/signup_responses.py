"""DM-with-ephemeral-fallback helper for signup-flow Discord interactions.

Issues #191, #192: signup messages should land as DMs (persistent, notification-
generating) rather than ephemerals that auto-dismiss after 60 seconds. When a
user has DMs disabled (Discord 50007), fall back to ephemeral and prefix with
<@user_id> so they get a notification badge.

Discord interactions must be acknowledged within 3 seconds — defer first to
extend the window to 15 minutes, then attempt the DM. On DM success, delete
the deferred placeholder so the originating button doesn't appear hung.
delete_original_response is best-effort: NotFound/HTTPException are swallowed
since the DM already landed.
"""

from enum import Enum

import discord

from telemetry.logging import get_logger

log = get_logger(__name__)


class ResponseChannel(Enum):
    DM = "dm"
    EPHEMERAL = "ephemeral"


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

    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)

    try:
        dm_channel = await interaction.user.create_dm()
        await dm_channel.send(content=content, embed=embed, view=view)
        try:
            await interaction.delete_original_response()
        except (discord.NotFound, discord.HTTPException):
            # Cleanup is best-effort; the DM already landed.
            pass
        channel = ResponseChannel.DM
    except discord.Forbidden as e:
        if getattr(e, "code", None) == 50007:
            mention = f"<@{user_id}>"
            text = f"{mention} {content}".strip() if content else mention
            await interaction.followup.send(
                content=text, embed=embed, view=view, ephemeral=True
            )
            channel = ResponseChannel.EPHEMERAL
        else:
            log.error(
                "signup_response_failed",
                system="events",
                subsystem="discord",
                user_id=user_id,
                event_id=event_id,
                error=str(e),
            )
            raise

    log.info(
        "signup_response_sent",
        system="events",
        subsystem="discord",
        channel=channel.value,
        fallback_to_ephemeral=(channel == ResponseChannel.EPHEMERAL),
        user_id=user_id,
        event_id=event_id,
    )
    return channel

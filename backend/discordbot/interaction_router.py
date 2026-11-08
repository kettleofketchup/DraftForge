"""Route component interactions that discord.py's view store does not own."""

from __future__ import annotations

import discord

from discordbot.components import (
    DeclineButton,
    NotifyButton,
    SignupButton,
    TentativeButton,
)
from discordbot.components.registry import iter_component_providers
from discordbot.custom_ids import CustomId, DeclineId, NotifyId, SignupId, TentativeId
from discordbot.log_context import discord_log_context
from telemetry.logging import get_logger

log = get_logger(__name__)

STALE_COMPONENT_MESSAGE = "❌ This menu is out of date."


async def _reject_bad_custom_id(
    interaction: discord.Interaction,
    custom_id: str,
    codec: type[CustomId],
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

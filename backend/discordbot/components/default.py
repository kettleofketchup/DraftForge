"""Default (game-agnostic) signup components: ``DefaultComponents``.

Fallback provider for any game type without a dedicated module. Renders a
minimal modal (friend-id only, or no fields if ``require_steam_id`` is False).

Counterpart logic layer: ``events.discord.providers.base.DefaultHandler``.
"""

from __future__ import annotations

import discord
from asgiref.sync import sync_to_async
from discord import ui

from discordbot.components.base import (
    GameComponentProvider,
    build_friend_id_input,
    respond_to_signup_user,
)
from discordbot.internal_client.signup_actions import signup_modal_submit
from discordbot.log_context import discord_log_context
from telemetry.logging import get_logger

log = get_logger(__name__)


class DefaultComponents(GameComponentProvider):
    """Stateless singleton fallback provider. Minimal modal, no follow-up views."""

    bare_select_ids: tuple = ()

    def build_signup_modal(
        self, event_id: int, prefill: dict, config: dict
    ) -> ui.Modal:
        return DefaultSignupModal(event_id, prefill, config)

    async def dispatch_bare_select(
        self, interaction: discord.Interaction, cid
    ) -> None:  # pragma: no cover - no bare selects
        return None


class DefaultSignupModal(ui.Modal):
    """Minimal modal: friend-id only (or no fields if not required)."""

    def __init__(self, event_id, prefill=None, config=None):
        self.event_id = event_id
        self.event_config = config or {}
        prefill = prefill or {}

        super().__init__(title="Event Sign Up")

        require_friend_id = (self.event_config or {}).get("require_steam_id", True)
        self.friend_id_input = build_friend_id_input(event_id, prefill, require_friend_id)
        if self.friend_id_input is not None:
            self.add_item(self.friend_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        async with discord_log_context(
            interaction,
            custom_id=f"signup_modal:{self.event_id}",
            event_id=self.event_id,
            tags=["events", "signup"],
        ) as ctx:
            values = {}
            if self.friend_id_input:
                values["unverified_friend_id"] = self.friend_id_input.value

            result = await sync_to_async(signup_modal_submit, thread_sensitive=False)(
                event_id=self.event_id,
                discord_user_id=str(interaction.user.id),
                game_type=0,
                values=values,
            )
            ctx.set_outcome(result["action"])

            if result["action"] == "signed_up":
                await respond_to_signup_user(
                    interaction,
                    content=f"✅ You're signed up! Status: **{result['status']}**",
                )
            elif result["action"] == "error":
                await interaction.response.send_message(
                    f"❌ {result['message']}",
                    ephemeral=True,
                )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        async with discord_log_context(
            interaction,
            custom_id=f"signup_modal:{self.event_id}",
            event_id=self.event_id,
            tags=["events", "signup"],
        ):
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ Something went wrong. Please try again.",
                        ephemeral=True,
                    )
                else:
                    await interaction.followup.send(
                        "❌ Something went wrong. Please try again.",
                        ephemeral=True,
                    )
            finally:
                raise error

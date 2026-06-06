"""Deadlock signup components: ``DeadlockComponents`` + ``DeadlockSignupModal``.

Friend-id + rank/date text inputs; direct signup, no follow-up views.

Counterpart logic layer: ``events.discord.providers.deadlock.DeadlockHandler``.
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
from discordbot.custom_ids import SignupDeadlockDateId, SignupDeadlockRankId
from discordbot.internal_client.signup_actions import signup_modal_submit
from discordbot.log_context import discord_log_context
from telemetry.logging import get_logger

log = get_logger(__name__)


class DeadlockComponents(GameComponentProvider):
    """Stateless singleton. Owns Deadlock's modal. No ORM, no follow-up views."""

    bare_select_ids: tuple = ()

    def build_signup_modal(
        self, event_id: int, prefill: dict, config: dict
    ) -> ui.Modal:
        return DeadlockSignupModal(event_id, prefill, config)

    async def dispatch_bare_select(
        self, interaction: discord.Interaction, cid
    ) -> None:  # pragma: no cover - no bare selects
        return None


class DeadlockSignupModal(ui.Modal):
    """Modal that collects Deadlock player profile data: friend-id + rank/date."""

    def __init__(self, event_id, prefill=None, config=None):
        self.event_id = event_id
        self.event_config = config or {}
        prefill = prefill or {}

        super().__init__(title="Event Sign Up")

        require_friend_id = (self.event_config or {}).get("require_steam_id", True)
        self.friend_id_input = build_friend_id_input(event_id, prefill, require_friend_id)
        if self.friend_id_input is not None:
            self.add_item(self.friend_id_input)

        self.rank_input = ui.TextInput(
            label="Your Deadlock Rank",
            placeholder="e.g., Phantom IV, Ascendant II, or 'unranked'",
            custom_id=SignupDeadlockRankId(event_id=event_id).encode(),
            required=True,
            max_length=100,
            style=discord.TextStyle.short,
            default=prefill.get("deadlock_rank", ""),
        )
        self.add_item(self.rank_input)

        self.rank_date_input = ui.TextInput(
            label="When did you last play ranked?",
            placeholder="e.g., March 2026, last week, never",
            custom_id=SignupDeadlockDateId(event_id=event_id).encode(),
            required=False,
            max_length=50,
            style=discord.TextStyle.short,
        )
        self.add_item(self.rank_date_input)

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
            values["deadlock_rank"] = self.rank_input.value
            values["deadlock_date"] = self.rank_date_input.value

            result = await sync_to_async(signup_modal_submit, thread_sensitive=False)(
                event_id=self.event_id,
                discord_user_id=str(interaction.user.id),
                game_type=2,
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

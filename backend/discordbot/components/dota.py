"""Dota 2 signup components: ``DotaComponents`` provider + ephemeral views.

``DotaComponents`` is a stateless singleton owning Dota's interaction
operations as methods. Each ephemeral-view callback decodes its typed
``CustomId`` and delegates to a bound method, forwarding the View's transient
state as explicit kwargs. discord.py dispatches the overridden callbacks
directly from its in-memory view store, so they self-dispatch (no central
routing) — except the bare ``pos_select_`` select, which ``bot.py`` routes via
``bare_select_ids`` / ``dispatch_bare_select``.

Counterpart logic layer: ``events.discord.providers.dota.DotaHandler``.
"""

from __future__ import annotations

import discord
from asgiref.sync import sync_to_async
from discord import ui

from discordbot.components.base import (
    GameComponentProvider,
    ScreenshotUploadPromptView,
    build_friend_id_input,
    respond_to_signup_user,
)
from discordbot.custom_ids import (
    BattleCupTierId,
    PosConfirmId,
    PosSelectId,
    RankMedalId,
    RankStarId,
    RankStatusId,
    SignupRankStatusId,
)
from discordbot.internal_client.signup_actions import (
    battle_cup_submit,
    rank_medal_select,
    rank_status_select,
    save_positions,
    set_position,
    signup_modal_submit,
)
from discordbot.log_context import discord_log_context
from telemetry.logging import get_logger

log = get_logger(__name__)


DOTA_POSITIONS = [
    discord.SelectOption(label="1: Hard Carry", value="1", emoji="⚔️"),
    discord.SelectOption(label="2: Midlane", value="2", emoji="\U0001f3af"),
    discord.SelectOption(label="3: Offlane", value="3", emoji="\U0001f6e1️"),
    discord.SelectOption(label="4: Soft Support", value="4", emoji="\U0001f49a"),
    discord.SelectOption(label="5: Hard Support", value="5", emoji="\U0001f49b"),
]

DOTA_MEDALS = [
    "Herald",
    "Guardian",
    "Crusader",
    "Archon",
    "Legend",
    "Ancient",
    "Divine",
    "Immortal",
]
DOTA_STARS = ["1", "2", "3", "4", "5"]


def _medal_options() -> list[discord.SelectOption]:
    """Build SelectOption list for Dota 2 medals."""
    return [discord.SelectOption(label=m, value=m) for m in DOTA_MEDALS]


def _star_options() -> list[discord.SelectOption]:
    """Build SelectOption list for medal stars 1-5."""
    return [discord.SelectOption(label=f"Star {s}", value=s) for s in DOTA_STARS]


class DotaComponents(GameComponentProvider):
    """Stateless singleton. Owns Dota's interaction operations as methods. No ORM.

    Transient flow-state (rank_status, require_screenshot, min_mmr,
    selected_medal) is passed per call — it lives on the View, not here.
    """

    bare_select_ids = (PosSelectId,)

    def build_signup_modal(
        self, event_id: int, prefill: dict, config: dict
    ) -> ui.Modal:
        return DotaSignupModal(event_id, prefill, config, provider=self)

    async def position_select(
        self, interaction: discord.Interaction, cid: PosSelectId
    ) -> None:
        """Bare select (routed by bot.py): persist a single position pick."""
        if interaction.response.is_done():
            return
        selected = interaction.data.get("values", []) if interaction.data else []
        if selected:
            try:
                pos_int = int(selected[0])
            except (TypeError, ValueError):
                pos_int = 0
            if pos_int in (1, 2, 3, 4, 5):
                await sync_to_async(set_position, thread_sensitive=False)(
                    event_id=cid.event_id,
                    discord_user_id=str(interaction.user.id),
                    position=pos_int,
                )
        await interaction.response.defer()

    async def dispatch_bare_select(
        self, interaction: discord.Interaction, cid: PosSelectId
    ) -> None:
        await self.position_select(interaction, cid)

    async def rank_status_select(
        self, interaction: discord.Interaction, cid: RankStatusId, *, values: list[str]
    ) -> None:
        async with discord_log_context(
            interaction, custom_id=cid.encode(), event_id=cid.event_id
        ) as ctx:
            rank_status = values[0] if values else "never"
            await sync_to_async(rank_status_select, thread_sensitive=False)(
                event_id=cid.event_id,
                discord_user_id=str(interaction.user.id),
                rank_status=rank_status,
            )
            ctx.set_outcome("rank_status_selected")
            ctx.add(rank_status=rank_status)

            new_view = RankDetailsView(cid.event_id, rank_status, provider=self)
            labels = {
                "active": "\U0001f3c5 **Select your current medal and star:**",
                "previous": "\U0001f3c5 **Select your previous medal and star:**",
                "never": "\U0001f4dd **Select your Battle Cup tier:**",
            }
            await interaction.response.edit_message(
                content=labels.get(rank_status, labels["never"]),
                view=new_view,
            )

    async def position_confirm(
        self,
        interaction: discord.Interaction,
        cid: PosConfirmId,
        *,
        view: ui.View,
        rank_status: str,
        require_screenshot: bool,
        min_mmr: int | None,
    ) -> None:
        async with discord_log_context(
            interaction, custom_id=cid.encode(), event_id=cid.event_id
        ) as ctx:
            positions = []
            for item in view.children:
                if isinstance(item, ui.Select) and item.values:
                    positions.extend(item.values)

            # Disable selects + confirm on first activation (double-click guard).
            for item in view.children:
                item.disabled = True

            await interaction.response.defer()  # bug-2: ACK before slow ORM

            try:
                positions_int = [int(v) for v in positions]
            except (TypeError, ValueError):
                ctx.set_outcome("error")
                ctx.add(reason="invalid_positions")
                await interaction.edit_original_response(
                    content="❌ Invalid positions.", view=None
                )
                return

            result = await sync_to_async(save_positions, thread_sensitive=False)(
                event_id=cid.event_id,
                discord_user_id=str(interaction.user.id),
                positions=positions_int,
            )
            if result.get("action") == "error":
                msg = result.get("message", "Could not save positions.")
                ctx.set_outcome("error")
                ctx.add(reason=msg)
                await interaction.edit_original_response(content=f"❌ {msg}", view=None)
                return

            ctx.set_outcome("positions_saved")
            ctx.add(positions=positions)

            new_view = RankDetailsView(
                cid.event_id,
                rank_status,
                require_screenshot=require_screenshot,
                min_mmr=min_mmr,
                provider=self,
            )
            labels = {
                "active": "\U0001f3c5 **Now select your rank:**\nChoose your medal and star",
                "previous": "\U0001f3c5 **Now select your previous rank:**\nChoose your medal and star",
                "never": "\U0001f3c6 **Select your Battle Cup tier:**",
            }
            await interaction.edit_original_response(
                content=labels.get(rank_status, labels["never"]),
                view=new_view,
            )

    async def rank_medal_select(
        self,
        interaction: discord.Interaction,
        cid: RankMedalId,
        *,
        values: list[str],
        rank_status: str,
        require_screenshot: bool,
    ) -> None:
        """Rebuild RankDetailsView so StarSelect.custom_id encodes the picked medal.

        Doing the rebuild here (rather than in a central handler) removes the
        40060 race against discord.py's view dispatch.
        """
        async with discord_log_context(
            interaction, custom_id=cid.encode(), event_id=cid.event_id
        ) as ctx:
            medal = values[0] if values else "Herald"
            ctx.set_outcome("medal_selected")
            ctx.add(medal=medal)

            new_view = RankDetailsView(
                cid.event_id,
                rank_status=rank_status,
                require_screenshot=require_screenshot,
                selected_medal=medal,
                provider=self,
            )
            label = "Rank" if rank_status == "active" else "Previous rank"
            await interaction.response.edit_message(
                content=f"\U0001f3c5 {label}: **{medal}** — now pick your star:",
                view=new_view,
            )

    async def rank_star_select(
        self,
        interaction: discord.Interaction,
        cid: RankStarId,
        *,
        values: list[str],
        view: ui.View,
        rank_status: str,
    ) -> None:
        async with discord_log_context(
            interaction, custom_id=cid.encode(), event_id=cid.event_id
        ) as ctx:
            medal = cid.medal if cid.medal != "Herald" else None

            if not medal:
                for item in view.children:
                    if isinstance(item, MedalSelect) and item.values:
                        medal = item.values[0]
                        break
            medal = medal or "Herald"

            star = values[0] if values else "1"
            medal_with_star = f"{medal} {star}" if medal != "Immortal" else "Immortal"

            # Disable selects (double-click guard) before the slow ORM call.
            for item in view.children:
                item.disabled = True

            await interaction.response.defer()  # bug-2: ACK before slow ORM

            result = await sync_to_async(rank_medal_select, thread_sensitive=False)(
                event_id=cid.event_id,
                discord_user_id=str(interaction.user.id),
                medal=medal_with_star,
            )
            ctx.set_outcome(result.get("action", "unknown"))
            ctx.add(medal=medal_with_star)

            label = "Rank" if rank_status == "active" else "Previous rank"

            if result.get("action") == "needs_screenshot":
                new_view = ScreenshotUploadPromptView(
                    cid.event_id, result["screenshot_type"]
                )
                await interaction.edit_original_response(
                    content=(
                        f"\U0001f3c5 {label} set to **{medal_with_star}**\n\n"
                        "\U0001f4f7 **Upload your screenshot to complete your signup.**\n"
                        "Press the button below to upload →"
                    ),
                    view=new_view,
                )
            elif result.get("action") == "error":
                await interaction.edit_original_response(
                    content=f"❌ {result['message']}",
                    view=None,
                )
            else:
                await interaction.edit_original_response(
                    content=f"✅ {label} set to **{medal_with_star}**. You're signed up! Status: **{result['status']}**",
                    view=None,
                )

    async def battle_cup_select(
        self,
        interaction: discord.Interaction,
        cid: BattleCupTierId,
        *,
        values: list[str],
        view: ui.View,
    ) -> None:
        async with discord_log_context(
            interaction, custom_id=cid.encode(), event_id=cid.event_id
        ) as ctx:
            tier = values[0] if values else "1"

            # Disable selects (double-click guard) before the slow ORM call.
            for item in view.children:
                item.disabled = True

            await interaction.response.defer()  # bug-2: ACK before slow ORM

            result = await sync_to_async(battle_cup_submit, thread_sensitive=False)(
                event_id=cid.event_id,
                discord_user_id=str(interaction.user.id),
                tier=tier,
            )
            ctx.set_outcome(result.get("action", "unknown"))
            ctx.add(tier=tier)

            if result.get("action") == "needs_screenshot":
                new_view = ScreenshotUploadPromptView(
                    cid.event_id, result["screenshot_type"]
                )
                await interaction.edit_original_response(
                    content=(
                        f"\U0001f3c6 Battle Cup tier {tier} saved\n\n"
                        "\U0001f4f7 **Upload your ticket screenshot to complete your signup.**\n"
                        "Press the button below to upload →"
                    ),
                    view=new_view,
                )
            elif result.get("action") == "error":
                await interaction.edit_original_response(
                    content=f"❌ {result['message']}",
                    view=None,
                )
            else:
                await interaction.edit_original_response(
                    content=f"✅ Battle Cup tier {tier} saved. You're signed up! Status: **{result['status']}**",
                    view=None,
                )


_PROVIDER = DotaComponents()


class DotaSignupModal(ui.Modal):
    """Modal that collects Dota player profile data for event signup.

    Friend ID (when missing) + Rank Status. Positions are collected in a
    follow-up ephemeral message (3 selects). The full config dict is stashed on
    ``self`` and read at the follow-up step.
    """

    def __init__(
        self,
        event_id: int,
        prefill: dict | None = None,
        config: dict | None = None,
        provider: DotaComponents | None = None,
    ) -> None:
        self.event_id = event_id
        self.event_config = config or {}
        self._provider = provider or _PROVIDER
        prefill = prefill or {}

        super().__init__(title="Event Sign Up")

        require_friend_id = (self.event_config or {}).get("require_steam_id", True)
        self.friend_id_input = build_friend_id_input(
            event_id, prefill, require_friend_id
        )
        if self.friend_id_input is not None:
            self.add_item(self.friend_id_input)

        self._add_dota_fields(event_id, prefill)

    def _add_dota_fields(self, event_id: int, prefill: dict) -> None:
        # Modal only has Steam ID + Rank Status.
        # Positions are collected in a follow-up ephemeral message (3 selects).
        self.pos_1_select = None
        self.pos_2_select = None
        self.pos_3_select = None

        # Build rank options based on event config flags
        all_rank_options = [
            (
                "allow_active_mmr",
                discord.SelectOption(
                    label="I have an active MMR",
                    value="active",
                    description="Currently ranked in Dota 2",
                    emoji="\U0001f3af",
                ),
            ),
            (
                "allow_previous_rank",
                discord.SelectOption(
                    label="I had an MMR",
                    value="previous",
                    description="Previously ranked but not currently",
                    emoji="⏰",
                ),
            ),
            (
                "allow_battlecup_rating",
                discord.SelectOption(
                    label="I've never had an MMR",
                    value="never",
                    description="Never played ranked Dota 2",
                    emoji="\U0001f195",
                ),
            ),
        ]

        rank_options = [
            opt for key, opt in all_rank_options if self.event_config.get(key, True)
        ]

        # Fallback: show all if none allowed (shouldn't happen)
        if not rank_options:
            rank_options = [opt for _, opt in all_rank_options]

        # String Select in modals requires Label wrapper + IS_COMPONENTS_V2 flag
        self.rank_status_input = ui.Select(
            placeholder="Select your ranked status",
            custom_id=SignupRankStatusId(event_id=event_id).encode(),
            min_values=1,
            max_values=1,
            options=rank_options,
        )
        self.add_item(
            ui.Label(
                text="Rank Status",
                description="What's your Dota 2 ranked status?",
                component=self.rank_status_input,
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        async with discord_log_context(
            interaction,
            custom_id=f"signup_modal:{self.event_id}",
            event_id=self.event_id,
            tags=["events", "signup"],
        ) as ctx:
            values = {}
            if self.friend_id_input:
                values["unverified_friend_id"] = self.friend_id_input.value

            values["positions"] = []
            values["rank_status"] = (
                self.rank_status_input.values[0]
                if self.rank_status_input and self.rank_status_input.values
                else None
            )

            result = await sync_to_async(signup_modal_submit, thread_sensitive=False)(
                event_id=self.event_id,
                discord_user_id=str(interaction.user.id),
                game_type=1,
                values=values,
            )
            ctx.set_outcome(result["action"])

            if result["action"] == "needs_rank_details":
                from events.schemas import DotaModalConfig, dota_require_screenshot

                rank_status = values.get("rank_status", "never")
                cfg = DotaModalConfig(
                    **{
                        k: v
                        for k, v in self.event_config.items()
                        if k in DotaModalConfig.model_fields
                    }
                )
                require_screenshot = dota_require_screenshot(rank_status, cfg)
                view = PositionSelectView(
                    self.event_id,
                    rank_status,
                    require_screenshot=require_screenshot,
                    min_mmr=self.event_config.get("min_mmr"),
                    provider=self._provider,
                )
                await interaction.response.send_message(
                    "\U0001f3ae **Select your preferred positions:**\n"
                    "Choose your 1st, 2nd, and 3rd choice, then press Confirm",
                    view=view,
                    ephemeral=True,
                )
            elif result["action"] == "needs_rank_status":
                view = RankStatusSelectView(
                    event_id=self.event_id, provider=self._provider
                )
                await interaction.response.send_message(
                    "\U0001f3ae **What's your Dota 2 ranked status?**",
                    view=view,
                    ephemeral=True,
                )
            elif result["action"] == "signed_up":
                await respond_to_signup_user(
                    interaction,
                    content=f"✅ You're signed up! Status: **{result['status']}**",
                )
            elif result["action"] == "error":
                await interaction.response.send_message(
                    f"❌ {result['message']}",
                    ephemeral=True,
                )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
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


class RankStatusSelectView(ui.View):
    """Ephemeral select for MMR status after modal submit."""

    def __init__(self, event_id: int, provider: DotaComponents | None = None) -> None:
        super().__init__(timeout=300)
        self.event_id = event_id
        self._provider = provider or _PROVIDER
        self.add_item(RankStatusSelect(event_id, provider=self._provider))


class RankStatusSelect(ui.Select):
    """Select menu for rank status choice."""

    def __init__(self, event_id: int, provider: DotaComponents | None = None) -> None:
        super().__init__(
            placeholder="Select your ranked status",
            custom_id=RankStatusId(event_id=event_id).encode(),
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="I have an active MMR",
                    value="active",
                    description="Currently ranked in Dota 2",
                    emoji="\U0001f3af",
                ),
                discord.SelectOption(
                    label="I had an MMR",
                    value="previous",
                    description="Previously ranked but not currently",
                    emoji="⏰",
                ),
                discord.SelectOption(
                    label="I've never had an MMR",
                    value="never",
                    description="Never played ranked Dota 2",
                    emoji="\U0001f195",
                ),
            ],
        )
        self.event_id = event_id
        self._provider = provider or _PROVIDER

    async def callback(self, interaction: discord.Interaction) -> None:
        await self._provider.rank_status_select(
            interaction, RankStatusId.decode(self.custom_id), values=list(self.values)
        )


class PositionSelectView(ui.View):
    """Ephemeral view with 3 position selects. Confirm saves positions and shows rank details."""

    def __init__(
        self,
        event_id: int,
        rank_status: str,
        require_screenshot: bool = False,
        min_mmr: int | None = None,
        provider: DotaComponents | None = None,
    ) -> None:
        super().__init__(timeout=300)
        self.event_id = event_id
        self.rank_status = rank_status
        self.require_screenshot = require_screenshot
        self.min_mmr = min_mmr
        self._provider = provider or _PROVIDER

        self.pos_1 = ui.Select(
            placeholder="1st Choice Position",
            custom_id=PosSelectId(event_id=event_id, slot=1).encode(),
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=o.label, value=o.value, emoji=o.emoji)
                for o in DOTA_POSITIONS
            ],
        )
        self.add_item(self.pos_1)

        self.pos_2 = ui.Select(
            placeholder="2nd Choice Position",
            custom_id=PosSelectId(event_id=event_id, slot=2).encode(),
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=o.label, value=o.value, emoji=o.emoji)
                for o in DOTA_POSITIONS
            ],
        )
        self.add_item(self.pos_2)

        self.pos_3 = ui.Select(
            placeholder="3rd Choice Position (optional)",
            custom_id=PosSelectId(event_id=event_id, slot=3).encode(),
            min_values=0,
            max_values=1,
            options=[
                discord.SelectOption(label=o.label, value=o.value, emoji=o.emoji)
                for o in DOTA_POSITIONS
            ],
        )
        self.add_item(self.pos_3)

        self.add_item(
            PositionConfirmButton(
                event_id,
                rank_status,
                require_screenshot,
                min_mmr,
                provider=self._provider,
            )
        )


class PositionConfirmButton(ui.Button):
    """Confirm button that saves positions and transitions to rank details."""

    def __init__(
        self,
        event_id: int,
        rank_status: str,
        require_screenshot: bool = False,
        min_mmr: int | None = None,
        provider: DotaComponents | None = None,
    ) -> None:
        super().__init__(
            label="Confirm Positions",
            style=discord.ButtonStyle.success,
            custom_id=PosConfirmId(event_id=event_id).encode(),
            emoji="✅",
        )
        self.event_id = event_id
        self.rank_status = rank_status
        self.require_screenshot = require_screenshot
        self.min_mmr = min_mmr
        self._provider = provider or _PROVIDER

    async def callback(self, interaction: discord.Interaction) -> None:
        await self._provider.position_confirm(
            interaction,
            PosConfirmId.decode(self.custom_id),
            view=self.view,
            rank_status=self.rank_status,
            require_screenshot=self.require_screenshot,
            min_mmr=self.min_mmr,
        )


class RankDetailsView(ui.View):
    """Ephemeral follow-up for collecting rank details. All selects, no modals.

    - active: Medal + Star selects → signs up
    - previous: Medal + Star selects → signs up (date not required)
    - never: Battle Cup Tier select → signs up
    """

    def __init__(
        self,
        event_id: int,
        rank_status: str,
        require_screenshot: bool = False,
        min_mmr: int | None = None,
        selected_medal: str | None = None,
        provider: DotaComponents | None = None,
    ) -> None:
        super().__init__(timeout=300)
        self.event_id = event_id
        self.rank_status = rank_status
        self.require_screenshot = require_screenshot
        self.min_mmr = min_mmr
        self._provider = provider or _PROVIDER

        if rank_status in ("active", "previous"):
            self.add_item(
                MedalSelect(
                    event_id,
                    rank_status=rank_status,
                    require_screenshot=require_screenshot,
                    provider=self._provider,
                )
            )
            self.add_item(
                StarSelect(
                    event_id,
                    rank_status,
                    require_screenshot=require_screenshot,
                    selected_medal=selected_medal,
                    provider=self._provider,
                )
            )
        elif rank_status == "never":
            self.add_item(
                BattleCupTierSelect(
                    event_id,
                    require_screenshot=require_screenshot,
                    provider=self._provider,
                )
            )


class MedalSelect(ui.Select):
    """Select menu for rank medal."""

    def __init__(
        self,
        event_id: int,
        rank_status: str = "active",
        require_screenshot: bool = False,
        provider: DotaComponents | None = None,
    ) -> None:
        super().__init__(
            placeholder="Select your medal",
            custom_id=RankMedalId(event_id=event_id).encode(),
            min_values=1,
            max_values=1,
            options=_medal_options(),
        )
        self.event_id = event_id
        self.rank_status = rank_status
        self.require_screenshot = require_screenshot
        self._provider = provider or _PROVIDER

    async def callback(self, interaction: discord.Interaction) -> None:
        await self._provider.rank_medal_select(
            interaction,
            RankMedalId.decode(self.custom_id),
            values=list(self.values),
            rank_status=self.rank_status,
            require_screenshot=self.require_screenshot,
        )


class StarSelect(ui.Select):
    """Select menu for medal star 1-5. Triggers signup on selection.

    The selected medal is encoded in custom_id as rank_star:{event_id}:{medal}.
    The "Herald" sentinel (unset) and "Immortal" suppression logic live in the
    provider callback, not the codec.
    """

    def __init__(
        self,
        event_id: int,
        rank_status: str = "active",
        require_screenshot: bool = False,
        selected_medal: str | None = None,
        provider: DotaComponents | None = None,
    ) -> None:
        medal_part = selected_medal or "Herald"
        super().__init__(
            placeholder="Select your star (1-5)",
            custom_id=RankStarId(event_id=event_id, medal=medal_part).encode(),
            min_values=1,
            max_values=1,
            options=_star_options(),
        )
        self.event_id = event_id
        self.rank_status = rank_status
        self.require_screenshot = require_screenshot
        self._provider = provider or _PROVIDER

    async def callback(self, interaction: discord.Interaction) -> None:
        await self._provider.rank_star_select(
            interaction,
            RankStarId.decode(self.custom_id),
            values=list(self.values),
            view=self.view,
            rank_status=self.rank_status,
        )


class BattleCupTierSelect(ui.Select):
    """Select menu for Battle Cup tier. Triggers signup on selection."""

    def __init__(
        self,
        event_id: int,
        require_screenshot: bool = False,
        provider: DotaComponents | None = None,
    ) -> None:
        super().__init__(
            placeholder="Select your max Battle Cup tier",
            custom_id=BattleCupTierId(event_id=event_id).encode(),
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=f"Tier {t}", value=str(t))
                for t in range(1, 9)
            ],
        )
        self.event_id = event_id
        self.require_screenshot = require_screenshot
        self._provider = provider or _PROVIDER

    async def callback(self, interaction: discord.Interaction) -> None:
        await self._provider.battle_cup_select(
            interaction,
            BattleCupTierId.decode(self.custom_id),
            values=list(self.values),
            view=self.view,
        )

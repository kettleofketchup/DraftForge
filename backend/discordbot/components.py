"""discord.py persistent Views, Buttons, and Modals for event interactions.

These classes handle the Discord UI plumbing. Business logic lives in
events/discord.py (handle_signup_button, handle_modal_submit, etc.).
"""

import logging

import discord
from discord import ui
from django.conf import settings

log = logging.getLogger(__name__)

SITE_URL = getattr(settings, "SITE_URL", "")


class EventSignupView(ui.View):
    """Persistent view attached to event announcement messages.

    Components:
    - Sign Up button (green)
    - Notify Me button (grey, only if event has a repeater)
    - View Event button (link to site)
    """

    def __init__(self, event_id, has_repeater=False, site_url=None):
        super().__init__(timeout=None)  # Persistent

        # Sign Up button
        self.add_item(SignupButton(event_id))

        # Notify Me — only for repeater events
        if has_repeater:
            self.add_item(NotifyButton(event_id))

        # View Event — link button (no custom_id, opens URL)
        url = site_url or SITE_URL
        if url:
            self.add_item(
                ui.Button(
                    label="View Event",
                    style=discord.ButtonStyle.link,
                    url=f"{url}/events/{event_id}/",
                    emoji="\U0001f517",
                )
            )


class SignupButton(ui.Button):
    """Green 'Sign Up' button. custom_id='event_signup:{event_id}'"""

    def __init__(self, event_id):
        super().__init__(
            label="Sign Up",
            style=discord.ButtonStyle.success,
            custom_id=f"event_signup:{event_id}",
            emoji="\u2705",
        )
        self.event_id = event_id

    async def callback(self, interaction: discord.Interaction):
        from asgiref.sync import sync_to_async

        from events.discord import handle_signup_button

        result = await sync_to_async(handle_signup_button)(
            event_id=self.event_id,
            discord_user_id=str(interaction.user.id),
        )

        if result["action"] == "signed_up":
            await interaction.response.send_message(
                f"\u2705 You're signed up! Status: **{result['status']}**",
                ephemeral=True,
            )
        elif result["action"] == "needs_modal":
            modal = EventSignupModal(
                event_id=self.event_id,
                game_type=result["game_type"],
                prefill=result.get("prefill", {}),
            )
            await interaction.response.send_modal(modal)
        elif result["action"] == "error":
            await interaction.response.send_message(
                f"\u274c {result['message']}",
                ephemeral=True,
            )


class NotifyButton(ui.Button):
    """Grey 'Notify Me' button. custom_id='event_notify:{event_id}'"""

    def __init__(self, event_id):
        super().__init__(
            label="Notify Me",
            style=discord.ButtonStyle.secondary,
            custom_id=f"event_notify:{event_id}",
            emoji="\U0001f514",
        )
        self.event_id = event_id

    async def callback(self, interaction: discord.Interaction):
        from asgiref.sync import sync_to_async

        from events.discord import handle_notify_button

        result = await sync_to_async(handle_notify_button)(
            event_id=self.event_id,
            discord_user_id=str(interaction.user.id),
        )

        if result["subscribed"]:
            await interaction.response.send_message(
                "\U0001f514 You'll be notified about future events in this series!",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "\U0001f515 Notifications turned off for this series.",
                ephemeral=True,
            )


class EventSignupModal(ui.Modal):
    """Modal that collects player profile data for event signup.

    Fields vary based on game_type:
    - Dota 2: Steam ID, positions (select 1-3), rank status
    - Deadlock: Steam ID, rank (text), rank date
    """

    def __init__(self, event_id, game_type, prefill=None):
        self.event_id = event_id
        self.game_type = game_type
        prefill = prefill or {}

        super().__init__(title="Event Sign Up")

        # Steam Friend ID — always shown if missing
        if "unverified_steam_id" not in prefill or not prefill["unverified_steam_id"]:
            self.steam_id_input = ui.TextInput(
                label="Steam Friend ID",
                placeholder="Your Steam Friend ID (number from Dotabuff URL)",
                custom_id=f"signup_steam:{event_id}",
                required=True,
                max_length=20,
                style=discord.TextStyle.short,
                default=str(prefill.get("unverified_steam_id", "")),
            )
            self.add_item(self.steam_id_input)
        else:
            self.steam_id_input = None

        if game_type == 1:  # Dota 2
            self._add_dota_fields(event_id, prefill)
        elif game_type == 2:  # Deadlock
            self._add_deadlock_fields(event_id, prefill)

    def _add_dota_fields(self, event_id, prefill):
        # NOTE: discord.py Modals only support TextInput, NOT Select menus.
        # Positions and rank status are collected as text, parsed on submit.
        self.positions_input = ui.TextInput(
            label="Preferred Positions (pick 1-3)",
            placeholder="e.g., 1,2,5 (1=Carry, 2=Mid, 3=Off, 4=Soft Sup, 5=Hard Sup)",
            custom_id=f"signup_positions:{event_id}",
            required=True,
            max_length=20,
            style=discord.TextStyle.short,
        )
        self.add_item(self.positions_input)

        self.rank_status_input = ui.TextInput(
            label="Rank Status",
            placeholder="active, previous, or never",
            custom_id=f"signup_rank_status:{event_id}",
            required=True,
            max_length=20,
            style=discord.TextStyle.short,
        )
        self.add_item(self.rank_status_input)

    def _add_deadlock_fields(self, event_id, prefill):
        self.rank_input = ui.TextInput(
            label="Your Deadlock Rank",
            placeholder="e.g., Phantom IV, Ascendant II, or 'unranked'",
            custom_id=f"signup_deadlock_rank:{event_id}",
            required=True,
            max_length=100,
            style=discord.TextStyle.short,
            default=prefill.get("deadlock_rank", ""),
        )
        self.add_item(self.rank_input)

        self.rank_date_input = ui.TextInput(
            label="When did you last play ranked?",
            placeholder="e.g., March 2026, last week, never",
            custom_id=f"signup_deadlock_date:{event_id}",
            required=False,
            max_length=50,
            style=discord.TextStyle.short,
        )
        self.add_item(self.rank_date_input)

    async def on_submit(self, interaction: discord.Interaction):
        from asgiref.sync import sync_to_async

        from events.discord import handle_signup_modal_submit

        # Collect values from fields
        values = {}
        if self.steam_id_input:
            values["unverified_steam_id"] = self.steam_id_input.value

        if self.game_type == 1:  # Dota 2
            # Parse comma-separated position numbers from TextInput
            values["positions"] = [
                p.strip() for p in self.positions_input.value.split(",") if p.strip()
            ]
            values["rank_status"] = self.rank_status_input.value.strip().lower()
        elif self.game_type == 2:  # Deadlock
            values["deadlock_rank"] = self.rank_input.value
            values["deadlock_date"] = self.rank_date_input.value

        result = await sync_to_async(handle_signup_modal_submit)(
            event_id=self.event_id,
            discord_user_id=str(interaction.user.id),
            game_type=self.game_type,
            values=values,
        )

        if result["action"] == "needs_rank_details":
            # Step 2: send ephemeral follow-up for rank details
            view = RankDetailsView(
                event_id=self.event_id,
                rank_status=values["rank_status"],
            )
            await interaction.response.send_message(
                result["message"],
                view=view,
                ephemeral=True,
            )
        elif result["action"] == "signed_up":
            await interaction.response.send_message(
                f"\u2705 You're signed up! Status: **{result['status']}**",
                ephemeral=True,
            )
        elif result["action"] == "error":
            await interaction.response.send_message(
                f"\u274c {result['message']}",
                ephemeral=True,
            )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.exception("EventSignupModal error: %s", error)
        await interaction.response.send_message(
            "\u274c Something went wrong. Please try again.",
            ephemeral=True,
        )


class RankDetailsView(ui.View):
    """Ephemeral follow-up view for collecting rank details after modal submit.

    Shown when rank_status is 'active', 'previous', or 'never' for Dota 2 events.
    """

    def __init__(self, event_id, rank_status):
        super().__init__(timeout=300)  # 5 min timeout for follow-up
        self.event_id = event_id
        self.rank_status = rank_status

        if rank_status == "active":
            self.add_item(MedalSelect(event_id))
        elif rank_status in ("previous", "never"):
            self.add_item(RankDetailsButton(event_id, rank_status))


class MedalSelect(ui.Select):
    """Select menu for active rank medal."""

    def __init__(self, event_id):
        super().__init__(
            placeholder="Select your current medal",
            custom_id=f"rank_medal:{event_id}",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="Herald", value="Herald"),
                discord.SelectOption(label="Guardian", value="Guardian"),
                discord.SelectOption(label="Crusader", value="Crusader"),
                discord.SelectOption(label="Archon", value="Archon"),
                discord.SelectOption(label="Legend", value="Legend"),
                discord.SelectOption(label="Ancient", value="Ancient"),
                discord.SelectOption(label="Divine", value="Divine"),
                discord.SelectOption(label="Immortal", value="Immortal"),
            ],
        )
        self.event_id = event_id

    async def callback(self, interaction: discord.Interaction):
        from asgiref.sync import sync_to_async

        from events.discord import handle_rank_medal_select

        result = await sync_to_async(handle_rank_medal_select)(
            event_id=self.event_id,
            discord_user_id=str(interaction.user.id),
            medal=self.values[0],
        )

        await interaction.response.edit_message(
            content=f"\u2705 Rank set to **{self.values[0]}**. You're signed up! Status: **{result['status']}**",
            view=None,
        )


class RankDetailsButton(ui.Button):
    """Button that opens a mini-modal for previous rank / battle cup details."""

    def __init__(self, event_id, rank_status):
        label = (
            "Enter Rank Details"
            if rank_status == "previous"
            else "Enter Battle Cup Info"
        )
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id=f"rank_details:{event_id}:{rank_status}",
        )
        self.event_id = event_id
        self.rank_status = rank_status

    async def callback(self, interaction: discord.Interaction):
        if self.rank_status == "previous":
            modal = PreviousRankModal(self.event_id)
        else:
            modal = BattleCupModal(self.event_id)
        await interaction.response.send_modal(modal)


class PreviousRankModal(ui.Modal, title="Previous Rank"):
    """Modal for previously ranked players."""

    def __init__(self, event_id):
        super().__init__()
        self.event_id = event_id

        self.medal_input = ui.TextInput(
            label="What was your highest medal?",
            placeholder="e.g., Legend, Ancient, Divine",
            custom_id=f"prev_medal:{event_id}",
            required=True,
            max_length=50,
            style=discord.TextStyle.short,
        )
        self.add_item(self.medal_input)

        self.date_input = ui.TextInput(
            label="When were you last ranked?",
            placeholder="e.g., January 2026, 6 months ago",
            custom_id=f"prev_date:{event_id}",
            required=True,
            max_length=50,
            style=discord.TextStyle.short,
        )
        self.add_item(self.date_input)

    async def on_submit(self, interaction: discord.Interaction):
        from asgiref.sync import sync_to_async

        from events.discord import handle_previous_rank_submit

        result = await sync_to_async(handle_previous_rank_submit)(
            event_id=self.event_id,
            discord_user_id=str(interaction.user.id),
            medal=self.medal_input.value,
            date_text=self.date_input.value,
        )

        await interaction.response.send_message(
            f"\u2705 Rank info saved. You're signed up! Status: **{result['status']}**",
            ephemeral=True,
        )


class BattleCupModal(ui.Modal, title="Battle Cup Info"):
    """Modal for never-ranked players."""

    def __init__(self, event_id):
        super().__init__()
        self.event_id = event_id

        self.tier_input = ui.TextInput(
            label="Max Battle Cup ticket tier you can buy",
            placeholder="Enter the number (e.g., 3, 5, 8)",
            custom_id=f"bcup_tier:{event_id}",
            required=True,
            max_length=5,
            style=discord.TextStyle.short,
        )
        self.add_item(self.tier_input)

    async def on_submit(self, interaction: discord.Interaction):
        from asgiref.sync import sync_to_async

        from events.discord import handle_battle_cup_submit

        result = await sync_to_async(handle_battle_cup_submit)(
            event_id=self.event_id,
            discord_user_id=str(interaction.user.id),
            tier=self.tier_input.value,
        )

        await interaction.response.send_message(
            f"\u2705 Battle Cup tier saved. You're signed up! Status: **{result['status']}**",
            ephemeral=True,
        )

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
IS_COMPONENTS_V2 = 1 << 15  # 32768


async def send_modal_v2(interaction: discord.Interaction, modal: ui.Modal):
    """Send a modal with IS_COMPONENTS_V2 flag for Label + Select support.

    discord.py's send_modal doesn't set the V2 flag, so Label-wrapped
    String Selects in modals get rejected. This helper sends the modal
    response manually with the flag included.
    """
    from discord.webhook.async_ import async_context

    adapter = async_context.get()
    http = interaction._state.http

    payload = modal.to_dict()
    payload["flags"] = IS_COMPONENTS_V2

    data = {
        "type": discord.InteractionResponseType.modal.value,
        "data": payload,
    }

    from discord.http import MultipartParameters

    params = MultipartParameters(payload=data, multipart=None, files=None)

    await adapter.create_interaction_response(
        interaction.id,
        interaction.token,
        session=interaction._session,
        proxy=http.proxy,
        proxy_auth=http.proxy_auth,
        params=params,
    )

    if not modal.is_finished():
        interaction._state.store_view(modal)
    interaction.response._response_type = discord.InteractionResponseType.modal


DOTA_POSITIONS = [
    discord.SelectOption(label="1: Hard Carry", value="1", emoji="\u2694\ufe0f"),
    discord.SelectOption(label="2: Midlane", value="2", emoji="\U0001f3af"),
    discord.SelectOption(label="3: Offlane", value="3", emoji="\U0001f6e1\ufe0f"),
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


def _medal_options():
    """Build SelectOption list for Dota 2 medals."""
    return [discord.SelectOption(label=m, value=m) for m in DOTA_MEDALS]


def _star_options():
    """Build SelectOption list for medal stars 1-5."""
    return [discord.SelectOption(label=f"Star {s}", value=s) for s in DOTA_STARS]


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
            discord_username=interaction.user.name,
        )

        if result["action"] == "signed_up":
            await interaction.response.defer()
            await interaction.followup.send(
                f"\u2705 You're signed up! Status: **{result['status']}**",
                delete_after=60,
            )
        elif result["action"] == "needs_modal":
            modal = EventSignupModal(
                event_id=self.event_id,
                game_type=result["game_type"],
                prefill=result.get("prefill", {}),
                event_config={
                    "require_steam_id": result.get("require_steam_id", True),
                    "require_rank_screenshot": result.get(
                        "require_rank_screenshot", False
                    ),
                    "require_battlecup_screenshot": result.get(
                        "require_battlecup_screenshot", False
                    ),
                    "min_mmr": result.get("min_mmr"),
                    "allow_active_mmr": result.get("allow_active_mmr", True),
                    "allow_previous_rank": result.get("allow_previous_rank", True),
                    "allow_battlecup_rating": result.get(
                        "allow_battlecup_rating", True
                    ),
                },
            )
            await send_modal_v2(interaction, modal)
        elif result["action"] == "error":
            await interaction.response.send_message(
                f"\u274c {result['message']}",
                ephemeral=True,
            )


class NotifyButton(ui.Button):
    """Grey 'Notify Me' button. custom_id='event_notify:{event_id}'"""

    def __init__(self, event_id):
        super().__init__(
            label="Notify Me for Future Events",
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


class TentativeButton(ui.Button):
    """Grey 'Tentative' button. custom_id='event_tentative:{event_id}'"""

    def __init__(self, event_id):
        super().__init__(
            label="Tentative",
            style=discord.ButtonStyle.secondary,
            custom_id=f"event_tentative:{event_id}",
            emoji="\u2753",
        )
        self.event_id = event_id

    async def callback(self, interaction: discord.Interaction):
        from asgiref.sync import sync_to_async

        from events.discord import handle_tentative_button

        result = await sync_to_async(handle_tentative_button)(
            event_id=self.event_id,
            discord_user_id=str(interaction.user.id),
        )

        if result["action"] == "tentative":
            await interaction.response.defer()
            await interaction.followup.send(
                "\u2753 Marked as tentative. We'll count you as interested!",
                delete_after=60,
            )
        elif result["action"] == "error":
            await interaction.response.send_message(
                result.get("message", "Something went wrong."),
                ephemeral=True,
            )


class DeclineButton(ui.Button):
    """Grey 'Decline' button. custom_id='event_decline:{event_id}'"""

    def __init__(self, event_id):
        super().__init__(
            label="Decline",
            style=discord.ButtonStyle.secondary,
            custom_id=f"event_decline:{event_id}",
        )
        self.event_id = event_id

    async def callback(self, interaction: discord.Interaction):
        from asgiref.sync import sync_to_async

        from events.discord import handle_decline_button

        result = await sync_to_async(handle_decline_button)(
            event_id=self.event_id,
            discord_user_id=str(interaction.user.id),
        )

        if result["action"] == "declined":
            await interaction.response.defer()
            await interaction.followup.send(
                "You've declined the event.",
                delete_after=60,
            )
        elif result["action"] == "not_signed_up":
            await interaction.response.send_message(
                "You weren't signed up for this event.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                result.get("message", "Something went wrong."),
                ephemeral=True,
            )


class EventSignupModal(ui.Modal):
    """Modal that collects player profile data for event signup.

    Fields vary based on game_type:
    - Dota 2: Steam ID, positions (select 1-3), rank status
    - Deadlock: Steam ID, rank (text), rank date
    """

    def __init__(self, event_id, game_type, prefill=None, event_config=None):
        self.event_id = event_id
        self.game_type = game_type
        self.event_config = event_config or {}
        prefill = prefill or {}

        super().__init__(title="Event Sign Up")

        # Friend ID — shown if missing and required by event
        require_friend_id = (self.event_config or {}).get("require_steam_id", True)
        has_friend_id = prefill.get("unverified_friend_id")
        if require_friend_id and not has_friend_id:
            self.friend_id_input = ui.TextInput(
                label="Dota 2 Friend ID",
                placeholder="Your Friend ID (number from your Dotabuff URL)",
                custom_id=f"signup_friend_id:{event_id}",
                required=True,
                max_length=20,
                style=discord.TextStyle.short,
                default=str(prefill.get("unverified_friend_id", "")),
            )
            self.add_item(self.friend_id_input)
        else:
            self.friend_id_input = None

        if game_type == 1:  # Dota 2
            self._add_dota_fields(event_id, prefill)
        elif game_type == 2:  # Deadlock
            self._add_deadlock_fields(event_id, prefill)

    def _add_dota_fields(self, event_id, prefill):
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
                    emoji="\u23f0",
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
            custom_id=f"signup_rank_status:{event_id}",
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
        if self.friend_id_input:
            values["unverified_friend_id"] = self.friend_id_input.value

        if self.game_type == 1:  # Dota 2
            # Positions collected in follow-up ephemeral, not in modal
            values["positions"] = []
            values["rank_status"] = (
                self.rank_status_input.values[0]
                if self.rank_status_input and self.rank_status_input.values
                else None
            )
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
            # Show position selection first, then rank details after
            rank_status = values.get("rank_status", "never")
            require_screenshot = (
                self.event_config.get("require_rank_screenshot", False)
                if rank_status == "active"
                else (
                    self.event_config.get("require_battlecup_screenshot", False)
                    if rank_status == "never"
                    else False
                )
            )
            view = PositionSelectView(
                self.event_id,
                rank_status,
                require_screenshot=require_screenshot,
                min_mmr=self.event_config.get("min_mmr"),
            )
            await interaction.response.send_message(
                "\U0001f3ae **Select your preferred positions:**\n"
                "Choose your 1st, 2nd, and 3rd choice, then press Confirm",
                view=view,
                ephemeral=True,
            )
        elif result["action"] == "needs_rank_status":
            # Fallback if rank_status wasn't captured
            view = RankStatusSelectView(event_id=self.event_id)
            await interaction.response.send_message(
                "\U0001f3ae **What's your Dota 2 ranked status?**",
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


class RankStatusSelectView(ui.View):
    """Ephemeral select for MMR status after modal submit.

    Options:
    - I have an active MMR → shows MedalSelect
    - I had an MMR → shows PreviousRankModal via button
    - I've never had an MMR → shows BattleCupModal via button
    """

    def __init__(self, event_id):
        super().__init__(timeout=300)
        self.event_id = event_id
        self.add_item(RankStatusSelect(event_id))


class RankStatusSelect(ui.Select):
    """Select menu for rank status choice."""

    def __init__(self, event_id):
        super().__init__(
            placeholder="Select your ranked status",
            custom_id=f"rank_status:{event_id}",
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
                    emoji="\u23f0",
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

    async def callback(self, interaction: discord.Interaction):
        from asgiref.sync import sync_to_async

        from events.discord import handle_rank_status_select

        rank_status = self.values[0]

        # Save rank_status to profile
        await sync_to_async(handle_rank_status_select)(
            event_id=self.event_id,
            discord_user_id=str(interaction.user.id),
            rank_status=rank_status,
        )

        view = RankDetailsView(self.event_id, rank_status)
        labels = {
            "active": "\U0001f3c5 **Select your current medal and star:**",
            "previous": "\U0001f3c5 **Select your previous medal and star:**",
            "never": "\U0001f4dd **Select your Battle Cup tier:**",
        }
        await interaction.response.edit_message(
            content=labels.get(rank_status, labels["never"]),
            view=view,
        )


class PositionSelectView(ui.View):
    """Ephemeral view with 3 position selects. Confirm saves positions and shows rank details."""

    def __init__(self, event_id, rank_status, require_screenshot=False, min_mmr=None):
        super().__init__(timeout=300)
        self.event_id = event_id
        self.rank_status = rank_status
        self.require_screenshot = require_screenshot
        self.min_mmr = min_mmr

        self.pos_1 = ui.Select(
            placeholder="1st Choice Position",
            custom_id=f"pos_select_1:{event_id}",
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
            custom_id=f"pos_select_2:{event_id}",
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
            custom_id=f"pos_select_3:{event_id}",
            min_values=0,
            max_values=1,
            options=[
                discord.SelectOption(label=o.label, value=o.value, emoji=o.emoji)
                for o in DOTA_POSITIONS
            ],
        )
        self.add_item(self.pos_3)

        self.add_item(
            PositionConfirmButton(event_id, rank_status, require_screenshot, min_mmr)
        )


class PositionConfirmButton(ui.Button):
    """Confirm button that saves positions and transitions to rank details."""

    def __init__(self, event_id, rank_status, require_screenshot=False, min_mmr=None):
        super().__init__(
            label="Confirm Positions",
            style=discord.ButtonStyle.success,
            custom_id=f"pos_confirm:{event_id}",
            emoji="\u2705",
        )
        self.event_id = event_id
        self.rank_status = rank_status
        self.require_screenshot = require_screenshot
        self.min_mmr = min_mmr

    async def callback(self, interaction: discord.Interaction):
        from asgiref.sync import sync_to_async

        from events.discord import _get_org_user
        from events.models import Event

        # Collect positions from sibling selects
        positions = []
        for item in self.view.children:
            if isinstance(item, ui.Select) and item.values:
                positions.extend(item.values)

        # Save positions to profile
        event = await sync_to_async(Event.objects.select_related("organization").get)(
            pk=self.event_id
        )
        org_user, _ = await sync_to_async(_get_org_user)(
            event, str(interaction.user.id)
        )

        if org_user:
            from cacheops import invalidate_obj

            from org.models_profiles import PlayerDotaProfile

            profile = await sync_to_async(
                lambda: PlayerDotaProfile.objects.get_or_create(org_user=org_user)[0]
            )()
            profile.pos_1 = "1" in positions
            profile.pos_2 = "2" in positions
            profile.pos_3 = "3" in positions
            profile.pos_4 = "4" in positions
            profile.pos_5 = "5" in positions
            await sync_to_async(profile.save)()
            await sync_to_async(invalidate_obj)(profile)

        # Now show rank details
        view = RankDetailsView(
            self.event_id,
            self.rank_status,
            require_screenshot=self.require_screenshot,
            min_mmr=self.min_mmr,
        )
        labels = {
            "active": "\U0001f3c5 **Now select your rank:**\nChoose your medal and star",
            "previous": "\U0001f3c5 **Now select your previous rank:**\nChoose your medal and star",
            "never": "\U0001f3c6 **Select your Battle Cup tier:**",
        }
        await interaction.response.edit_message(
            content=labels.get(self.rank_status, labels["never"]),
            view=view,
        )


class RankDetailsView(ui.View):
    """Ephemeral follow-up for collecting rank details. All selects, no modals.

    - active: Medal + Star selects → signs up
    - previous: Medal + Star selects → signs up (date not required)
    - never: Battle Cup Tier select → signs up
    """

    def __init__(
        self,
        event_id,
        rank_status,
        require_screenshot=False,
        min_mmr=None,
        selected_medal=None,
    ):
        super().__init__(timeout=300)
        self.event_id = event_id
        self.rank_status = rank_status
        self.require_screenshot = require_screenshot
        self.min_mmr = min_mmr

        if rank_status in ("active", "previous"):
            self.add_item(MedalSelect(event_id))
            self.add_item(
                StarSelect(
                    event_id,
                    rank_status,
                    require_screenshot=require_screenshot,
                    selected_medal=selected_medal,
                )
            )
        elif rank_status == "never":
            self.add_item(
                BattleCupTierSelect(event_id, require_screenshot=require_screenshot)
            )


class MedalSelect(ui.Select):
    """Select menu for rank medal."""

    def __init__(self, event_id):
        super().__init__(
            placeholder="Select your medal",
            custom_id=f"rank_medal:{event_id}",
            min_values=1,
            max_values=1,
            options=_medal_options(),
        )
        self.event_id = event_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()


class StarSelect(ui.Select):
    """Select menu for medal star 1-5. Triggers signup on selection.

    The selected medal is encoded in custom_id as rank_star:{event_id}:{medal}
    so the bot gateway handler can read it reliably.
    """

    def __init__(
        self,
        event_id,
        rank_status="active",
        require_screenshot=False,
        selected_medal=None,
    ):
        medal_part = selected_medal or "Herald"
        super().__init__(
            placeholder="Select your star (1-5)",
            custom_id=f"rank_star:{event_id}:{medal_part}",
            min_values=1,
            max_values=1,
            options=_star_options(),
        )
        self.event_id = event_id
        self.rank_status = rank_status
        self.require_screenshot = require_screenshot

    async def callback(self, interaction: discord.Interaction):
        from asgiref.sync import sync_to_async

        from events.discord import handle_rank_medal_select

        # Read medal from custom_id (rank_star:{event_id}:{medal})
        parts = self.custom_id.split(":")
        medal = parts[2] if len(parts) > 2 and parts[2] != "Herald" else None

        # Fallback: try reading from MedalSelect values
        if not medal:
            for item in self.view.children:
                if isinstance(item, MedalSelect) and item.values:
                    medal = item.values[0]
                    break
        medal = medal or "Herald"

        star = self.values[0]
        medal_with_star = f"{medal} {star}" if medal != "Immortal" else "Immortal"

        result = await sync_to_async(handle_rank_medal_select)(
            event_id=self.event_id,
            discord_user_id=str(interaction.user.id),
            medal=medal_with_star,
        )

        label = "Rank" if self.rank_status == "active" else "Previous rank"

        if result.get("action") == "needs_screenshot":
            view = ScreenshotUploadPromptView(self.event_id, result["screenshot_type"])
            await interaction.response.edit_message(
                content=(
                    f"\U0001f3c5 {label} set to **{medal_with_star}**\n\n"
                    "\U0001f4f7 **Upload your screenshot to complete your signup.**\n"
                    "Press the button below to upload \u2192"
                ),
                view=view,
            )
        elif result.get("action") == "error":
            await interaction.response.edit_message(
                content=f"\u274c {result['message']}",
                view=None,
            )
        else:
            await interaction.response.edit_message(
                content=f"\u2705 {label} set to **{medal_with_star}**. You're signed up! Status: **{result['status']}**",
                view=None,
            )


class BattleCupTierSelect(ui.Select):
    """Select menu for Battle Cup tier. Triggers signup on selection."""

    def __init__(self, event_id, require_screenshot=False):
        super().__init__(
            placeholder="Select your max Battle Cup tier",
            custom_id=f"bcup_tier:{event_id}",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=f"Tier {t}", value=str(t))
                for t in range(1, 9)
            ],
        )
        self.event_id = event_id
        self.require_screenshot = require_screenshot

    async def callback(self, interaction: discord.Interaction):
        from asgiref.sync import sync_to_async

        from events.discord import handle_battle_cup_submit

        tier = self.values[0]

        result = await sync_to_async(handle_battle_cup_submit)(
            event_id=self.event_id,
            discord_user_id=str(interaction.user.id),
            tier=tier,
        )

        if result.get("action") == "needs_screenshot":
            view = ScreenshotUploadPromptView(self.event_id, result["screenshot_type"])
            await interaction.response.edit_message(
                content=(
                    f"\U0001f3c6 Battle Cup tier {tier} saved\n\n"
                    "\U0001f4f7 **Upload your ticket screenshot to complete your signup.**\n"
                    "Press the button below to upload \u2192"
                ),
                view=view,
            )
        elif result.get("action") == "error":
            await interaction.response.edit_message(
                content=f"\u274c {result['message']}",
                view=None,
            )
        else:
            await interaction.response.edit_message(
                content=f"\u2705 Battle Cup tier {tier} saved. You're signed up! Status: **{result['status']}**",
                view=None,
            )


# ---------------------------------------------------------------------------
# Screenshot upload flow (V2 modals)
# ---------------------------------------------------------------------------

SCREENSHOT_EXAMPLE_URLS = {
    "rank": "https://assets.kettle.sh/draftforge/discord/rank/dota2/dota2_rank.png",
    "battlecup": "https://assets.kettle.sh/draftforge/discord/rank/dota2/battlecup_ticket.png",
}


class ScreenshotUploadPromptView(ui.View):
    """Ephemeral prompt with Upload Screenshot button."""

    def __init__(self, event_id, screenshot_type):
        super().__init__(timeout=300)
        self.event_id = event_id
        self.screenshot_type = screenshot_type
        self.example_url = SCREENSHOT_EXAMPLE_URLS.get(screenshot_type, "")
        self.add_item(ScreenshotUploadButton(event_id, screenshot_type))


class ScreenshotUploadButton(ui.Button):
    """Button that opens the screenshot upload modal."""

    def __init__(self, event_id, screenshot_type):
        label = (
            "Upload MMR Screenshot"
            if screenshot_type == "rank"
            else "Upload Battle Cup Screenshot"
        )
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id=f"screenshot_upload:{event_id}:{screenshot_type}",
            emoji="\U0001f4f8",
        )
        self.event_id = event_id
        self.screenshot_type = screenshot_type

    async def callback(self, interaction: discord.Interaction):
        if interaction.response.is_done():
            log.warning("Screenshot upload interaction already acknowledged")
            return
        modal = ScreenshotUploadModal(self.event_id, self.screenshot_type)
        await send_modal_v2(interaction, modal)


class ScreenshotUploadModal(ui.Modal):
    """V2 modal with TextDisplay (example + tips) and FileUpload or URL fallback."""

    def __init__(self, event_id, screenshot_type):
        self.event_id = event_id
        self.screenshot_type = screenshot_type

        title = (
            "Upload MMR Screenshot"
            if screenshot_type == "rank"
            else "Upload Battle Cup Screenshot"
        )
        super().__init__(title=title)

        from discordbot.screenshot_tips import SCREENSHOT_TIPS

        example_url = SCREENSHOT_EXAMPLE_URLS.get(screenshot_type, "")

        # Show example + tips (only TextDisplay type 10 is allowed in modals, not MediaGallery)
        if hasattr(ui, "TextDisplay"):
            label = "MMR" if screenshot_type == "rank" else "Battle Cup ticket"
            self.add_item(
                ui.TextDisplay(
                    content=f"**Example {label} screenshot:**\n{example_url}\n\n{SCREENSHOT_TIPS}"
                )
            )

        # Add FileUpload if available, otherwise fall back to TextInput for URL
        if hasattr(ui, "FileUpload"):
            self.file_upload = ui.FileUpload(
                custom_id=f"screenshot_file:{event_id}:{screenshot_type}",
            )
            self.add_item(ui.Label(text="Screenshot", component=self.file_upload))
            self.url_input = None
        else:
            self.file_upload = None
            self.url_input = ui.TextInput(
                label="Imgur Link",
                placeholder="Paste your imgur.com link here",
                custom_id=f"screenshot_url:{event_id}:{screenshot_type}",
                required=True,
                style=discord.TextStyle.short,
            )
            self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        from asgiref.sync import sync_to_async

        from events.discord import handle_screenshot_upload

        # Get URL from file upload or text input
        if self.file_upload and interaction.data.get("resolved", {}).get("files"):
            files = interaction.data["resolved"]["files"]
            attachment_url = list(files.values())[0].get("url", "") if files else ""
        elif self.url_input:
            attachment_url = self.url_input.value
        else:
            attachment_url = ""

        result = await sync_to_async(handle_screenshot_upload)(
            event_id=self.event_id,
            discord_user_id=str(interaction.user.id),
            screenshot_type=self.screenshot_type,
            attachment_url=attachment_url,
        )

        if result.get("success"):
            if result.get("signed_up"):
                await interaction.response.send_message(
                    f"\u2705 {result.get('message', 'Screenshot uploaded! You are signed up.')}",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"\u2705 {result.get('message', 'Screenshot saved.')}",
                    ephemeral=True,
                )
        else:
            await interaction.response.send_message(
                f"\u274c {result.get('message', 'Upload failed.')}",
                ephemeral=True,
            )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.exception("ScreenshotUploadModal error: %s", error)
        await interaction.response.send_message(
            "\u274c Something went wrong.",
            ephemeral=True,
        )

"""Discord bot client with slash commands."""

import logging
import sys

import discord
from discord import app_commands
from django.conf import settings

log = logging.getLogger(__name__)


def is_site_admin():
    """Check if user is an admin in the Django database by discordId."""

    async def predicate(interaction: discord.Interaction) -> bool:
        from app.models import CustomUser

        discord_id = str(interaction.user.id)
        try:
            user = CustomUser.objects.get(discordId=discord_id)
            if user.is_staff:
                return True
            raise app_commands.CheckFailure("You are not a site admin.")
        except CustomUser.DoesNotExist:
            raise app_commands.CheckFailure(
                "Your Discord account is not linked to the site."
            )

    return app_commands.check(predicate)


# Emoji mappings for RSVP
RSVP_EMOJIS = {
    "\u2705": "yes",  # checkmark
    "\u2753": "maybe",  # question mark
    "\u274c": "no",  # x mark
}


class KettleBot(discord.Client):
    """Discord bot for DTX gaming organization."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.reactions = True
        intents.members = True
        intents.message_content = True

        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.guild_id = settings.DISCORD_GUILD_ID

    async def setup_hook(self):
        """Called when bot is ready to sync commands."""
        guild = discord.Object(id=self.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        log.info(f"Synced commands to guild {self.guild_id}")

    async def on_ready(self):
        """Called when bot successfully connects."""
        log.info(f"Bot connected as {self.user} (ID: {self.user.id})")
        log.info(f"Connected to {len(self.guilds)} guilds")

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Track RSVP when user reacts."""
        # Ignore bot's own reactions
        if payload.user_id == self.user.id:
            return

        emoji = str(payload.emoji)

        # New events system: ✅ = signup, ❌ = cancel
        if emoji == "\u2705":
            from asgiref.sync import sync_to_async

            from events.discord import handle_reaction_signup

            success, detail = await sync_to_async(handle_reaction_signup)(
                str(payload.message_id), str(payload.user_id)
            )
            if success:
                log.info(
                    f"Event signup via reaction: user={payload.user_id} detail={detail}"
                )
                return
            elif detail != "not_event_message":
                # Was an event message but signup failed (already signed up, event closed, etc.)
                log.info(
                    f"Event signup skipped: user={payload.user_id} detail={detail}"
                )
                return
            # Fall through to old ScheduledEvent RSVP system

        if emoji == "\u274c":
            from asgiref.sync import sync_to_async

            from events.discord import handle_reaction_cancel

            success, detail = await sync_to_async(handle_reaction_cancel)(
                str(payload.message_id), str(payload.user_id)
            )
            if success:
                log.info(f"Event cancel via reaction: user={payload.user_id}")
                return
            elif detail != "not_event_message":
                log.info(
                    f"Event cancel skipped: user={payload.user_id} detail={detail}"
                )
                return

        # Legacy ScheduledEvent RSVP system
        if emoji not in RSVP_EMOJIS:
            return

        await self._handle_rsvp(payload, RSVP_EMOJIS[emoji])

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """Remove RSVP when user removes reaction."""
        emoji = str(payload.emoji)

        # New events system: removing ✅ = cancel signup
        if emoji == "\u2705":
            from asgiref.sync import sync_to_async

            from events.discord import handle_reaction_cancel

            success, detail = await sync_to_async(handle_reaction_cancel)(
                str(payload.message_id), str(payload.user_id)
            )
            if success:
                log.info(f"Event cancel via reaction remove: user={payload.user_id}")
                return
            elif detail != "not_event_message":
                return

        # Legacy ScheduledEvent RSVP system
        if emoji not in RSVP_EMOJIS:
            return

        await self._remove_rsvp(payload)

    async def on_interaction(self, interaction: discord.Interaction):
        """Route component and modal interactions to event signup handlers."""
        custom_id = interaction.data.get("custom_id", "") if interaction.data else ""

        if interaction.type == discord.InteractionType.component:
            if custom_id.startswith("event_signup:"):
                event_id = int(custom_id.split(":")[1])
                from discordbot.components import SignupButton

                button = SignupButton(event_id)
                await button.callback(interaction)
            elif custom_id.startswith("event_tentative:"):
                event_id = int(custom_id.split(":")[1])
                from discordbot.components import TentativeButton

                button = TentativeButton(event_id)
                await button.callback(interaction)
            elif custom_id.startswith("event_decline:"):
                event_id = int(custom_id.split(":")[1])
                from discordbot.components import DeclineButton

                button = DeclineButton(event_id)
                await button.callback(interaction)
            elif custom_id.startswith("event_notify:"):
                event_id = int(custom_id.split(":")[1])
                from discordbot.components import NotifyButton

                button = NotifyButton(event_id)
                await button.callback(interaction)
            elif custom_id.startswith("pos_select_"):
                # Save position immediately on selection (legacy per-click UI).
                event_id = int(custom_id.split(":")[1])
                selected = interaction.data.get("values", [])
                if selected:
                    from asgiref.sync import sync_to_async

                    from app.internal_client.signup_actions import set_position

                    try:
                        pos_int = int(selected[0])
                    except (TypeError, ValueError):
                        pos_int = 0
                    if pos_int in (1, 2, 3, 4, 5):
                        await sync_to_async(set_position, thread_sensitive=False)(
                            event_id=event_id,
                            discord_user_id=str(interaction.user.id),
                            position=pos_int,
                        )
                await interaction.response.defer()
            elif custom_id.startswith("pos_confirm:"):
                event_id = int(custom_id.split(":")[1])
                from asgiref.sync import sync_to_async

                from app.internal_client.signup_actions import get_rank_flow_state

                state = await sync_to_async(
                    get_rank_flow_state, thread_sensitive=False
                )(
                    event_id=event_id,
                    discord_user_id=str(interaction.user.id),
                )
                if state.get("error"):
                    await interaction.response.send_message(
                        f"\u274c {state.get('message', 'Could not load profile.')}",
                        ephemeral=True,
                    )
                    return

                from discordbot.components import RankDetailsView

                view = RankDetailsView(
                    event_id,
                    state["rank_status"],
                    require_screenshot=state["require_screenshot"],
                    min_mmr=state["min_mmr"],
                )
                labels = {
                    "active": "\U0001f3c5 **Now select your rank:**",
                    "previous": "\U0001f4dd **Now select your previous rank:**",
                    "never": "\U0001f4dd **Now select your Battle Cup tier:**",
                }
                await interaction.response.edit_message(
                    content=labels.get(state["rank_status"], labels["never"]),
                    view=view,
                )
            elif custom_id.startswith("rank_star:"):
                # custom_id format: rank_star:{event_id}:{medal}
                parts = custom_id.split(":")
                event_id = int(parts[1])
                medal = parts[2] if len(parts) > 2 else "Herald"

                from asgiref.sync import sync_to_async

                from app.internal_client.signup_actions import rank_medal_select

                star_values = interaction.data.get("values", [])
                star = star_values[0] if star_values else "1"
                medal_with_star = (
                    f"{medal} {star}" if medal != "Immortal" else "Immortal"
                )

                result = await sync_to_async(rank_medal_select)(
                    event_id=event_id,
                    discord_user_id=str(interaction.user.id),
                    medal=medal_with_star,
                )

                if result.get("action") == "needs_screenshot":
                    from discordbot.components import ScreenshotUploadPromptView

                    view = ScreenshotUploadPromptView(
                        event_id, result["screenshot_type"]
                    )
                    await interaction.response.edit_message(
                        content=(
                            f"\U0001f3c5 Rank set to **{medal_with_star}**\n\n"
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
                        content=f"\u2705 Rank set to **{medal_with_star}**. You're signed up! Status: **{result.get('status', 'pending')}**",
                        view=None,
                    )
            elif custom_id.startswith("rank_status:"):
                event_id = int(custom_id.split(":")[1])
                from discordbot.components import RankStatusSelect

                select = RankStatusSelect(event_id)
                select._values = interaction.data.get("values", [])
                await select.callback(interaction)
            elif custom_id.startswith("bcup_tier:"):
                event_id = int(custom_id.split(":")[1])
                from discordbot.components import BattleCupTierSelect

                select = BattleCupTierSelect(event_id)
                select._values = interaction.data.get("values", [])
                await select.callback(interaction)
            elif custom_id.startswith("screenshot_upload:"):
                # Handled by discord.py view system (ScreenshotUploadPromptView)
                # Only handle as fallback if view timed out / bot restarted
                if not interaction.response.is_done():
                    try:
                        parts = custom_id.split(":")
                        event_id = int(parts[1])
                        screenshot_type = parts[2]
                        from discordbot.components import ScreenshotUploadButton

                        button = ScreenshotUploadButton(event_id, screenshot_type)
                        await button.callback(interaction)
                    except discord.errors.HTTPException:
                        pass  # View already handled it
        # Modal submissions are auto-dispatched by discord.py to Modal.on_submit

    async def _handle_rsvp(self, payload, status):
        """Create or update RSVP record."""
        # Import here to avoid circular imports
        from discordbot.models import RSVP, ScheduledEvent

        try:
            event = ScheduledEvent.objects.get(
                discord_message_id=str(payload.message_id)
            )
        except ScheduledEvent.DoesNotExist:
            return  # Not an event message

        # Get user info
        guild = self.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id) if guild else None
        username = member.display_name if member else f"User {payload.user_id}"

        RSVP.objects.update_or_create(
            scheduled_event=event,
            discord_user_id=str(payload.user_id),
            defaults={
                "discord_username": username,
                "status": status,
            },
        )
        log.info(f"RSVP: {username} marked {status} for {event.template.name}")

    async def _remove_rsvp(self, payload):
        """Remove RSVP record."""
        from discordbot.models import RSVP, ScheduledEvent

        try:
            event = ScheduledEvent.objects.get(
                discord_message_id=str(payload.message_id)
            )
            RSVP.objects.filter(
                scheduled_event=event,
                discord_user_id=str(payload.user_id),
            ).delete()
            log.info(f"RSVP removed: user {payload.user_id} for {event.template.name}")
        except ScheduledEvent.DoesNotExist:
            pass


# Create bot instance
bot = KettleBot()


@bot.tree.command(name="roles", description="Set your Dota 2 position preferences")
async def roles_command(interaction: discord.Interaction):
    """Links user to DTX website for role selection."""
    site_url = getattr(settings, "SITE_URL", "https://localhost")
    url = f"{site_url}/profile?discord_id={interaction.user.id}"

    embed = discord.Embed(
        title="Set Your Roles",
        description=f"[Click here to set your position preferences]({url})",
        color=0x5865F2,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="event", description="Create a new event (Admin only)")
@is_site_admin()
async def event_command(
    interaction: discord.Interaction,
    name: str,
    description: str,
):
    """Admin command to create event from Discord."""
    from django.utils import timezone

    from discordbot.models import EventTemplate, ScheduledEvent

    # Create a one-time event template
    template = EventTemplate.objects.create(
        name=name,
        template_type="announcement",
        title=name,
        description=description,
        color="#5865F2",
        channel_id=str(interaction.channel_id),
        include_rsvp=True,
    )

    # Create scheduled event (post immediately)
    event = ScheduledEvent.objects.create(
        template=template,
        next_post_at=timezone.now(),
        is_recurring=False,
    )

    await interaction.response.send_message(
        f"Event '{name}' created! It will be posted shortly.", ephemeral=True
    )


@event_command.error
async def event_error(interaction: discord.Interaction, error):
    """Handle permission errors for event command."""
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(str(error), ephemeral=True)
    elif isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You need administrator permissions to create events.", ephemeral=True
        )


def run_bot():
    """Run the Discord bot."""
    token = settings.DISCORD_BOT_TOKEN
    if not token:
        log.error("DISCORD_BOT_TOKEN not set!")
        sys.exit(1)

    bot.run(token, log_handler=None)

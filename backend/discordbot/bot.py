"""Discord bot client with slash commands."""

import logging
import sys

import discord
from asgiref.sync import sync_to_async
from discord import app_commands
from django.conf import settings

from discordbot.components import (
    DeclineButton,
    NotifyButton,
    SignupButton,
    TentativeButton,
)
from discordbot.internal_client.bot_actions import (
    check_site_admin,
    create_legacy_event,
    reaction_cancel,
    reaction_signup,
    remove_legacy_rsvp,
    set_legacy_rsvp,
)
from discordbot.internal_client.signup_actions import set_position

log = logging.getLogger(__name__)


def is_site_admin():
    """Check if user is an admin via the internal API.

    The bot has no DB mount in production, so this MUST go over HTTP. The
    backend distinguishes "not linked" (no CustomUser row) from "not staff"
    so we can preserve the original CheckFailure messaging.
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        result = await sync_to_async(check_site_admin, thread_sensitive=False)(
            discord_user_id=str(interaction.user.id),
        )
        if result.get("error"):
            raise app_commands.CheckFailure(
                "Admin check unavailable; please try again later."
            )
        if not result.get("is_linked"):
            raise app_commands.CheckFailure(
                "Your Discord account is not linked to the site."
            )
        if not result.get("is_admin"):
            raise app_commands.CheckFailure("You are not a site admin.")
        return True

    return app_commands.check(predicate)


# Emoji mappings for RSVP
RSVP_EMOJIS = {
    "✅": "yes",  # checkmark
    "❓": "maybe",  # question mark
    "❌": "no",  # x mark
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
        if emoji == "✅":
            result = await sync_to_async(reaction_signup, thread_sensitive=False)(
                discord_message_id=str(payload.message_id),
                discord_user_id=str(payload.user_id),
            )
            detail = result.get("detail") or ""
            if result.get("success"):
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

        if emoji == "❌":
            result = await sync_to_async(reaction_cancel, thread_sensitive=False)(
                discord_message_id=str(payload.message_id),
                discord_user_id=str(payload.user_id),
            )
            detail = result.get("detail") or ""
            if result.get("success"):
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
        if emoji == "✅":
            result = await sync_to_async(reaction_cancel, thread_sensitive=False)(
                discord_message_id=str(payload.message_id),
                discord_user_id=str(payload.user_id),
            )
            detail = result.get("detail") or ""
            if result.get("success"):
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
                button = SignupButton(event_id)
                await button.callback(interaction)
            elif custom_id.startswith("event_tentative:"):
                event_id = int(custom_id.split(":")[1])
                button = TentativeButton(event_id)
                await button.callback(interaction)
            elif custom_id.startswith("event_decline:"):
                event_id = int(custom_id.split(":")[1])
                button = DeclineButton(event_id)
                await button.callback(interaction)
            elif custom_id.startswith("event_notify:"):
                event_id = int(custom_id.split(":")[1])
                button = NotifyButton(event_id)
                await button.callback(interaction)
            # Dynamic-view components (pos_confirm, rank_status, rank_star,
            # bcup_tier, screenshot_upload) are dispatched by discord.py's
            # stored-View system — each has an overridden ``callback`` in
            # components.py that runs the canonical handler. Routing them
            # here too caused a 40060 race: HTTP to internal_client takes
            # ~200ms, plenty of time for the View dispatch to ACK first.
            # pos_select_ stays here because the bare ui.Select has no
            # overridden callback (discord.py's default is a no-op).
            elif custom_id.startswith("pos_select_"):
                if interaction.response.is_done():
                    return
                event_id = int(custom_id.split(":")[1])
                selected = interaction.data.get("values", [])
                if selected:
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
        # Modal submissions are auto-dispatched by discord.py to Modal.on_submit

    async def _handle_rsvp(
        self, payload: discord.RawReactionActionEvent, status: str
    ) -> None:
        """Create/update an RSVP record for a legacy ScheduledEvent."""
        guild = self.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id) if guild else None
        username = member.display_name if member else f"User {payload.user_id}"

        result = await sync_to_async(set_legacy_rsvp, thread_sensitive=False)(
            discord_message_id=str(payload.message_id),
            discord_user_id=str(payload.user_id),
            status=status,
            discord_username=username,
        )
        if result.get("success"):
            log.info(
                f"RSVP: {username} marked {status} for {result.get('event_name')}"
            )

    async def _remove_rsvp(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        """Remove a legacy ScheduledEvent RSVP record."""
        result = await sync_to_async(remove_legacy_rsvp, thread_sensitive=False)(
            discord_message_id=str(payload.message_id),
            discord_user_id=str(payload.user_id),
        )
        if result.get("success"):
            log.info(
                f"RSVP removed: user {payload.user_id} for {result.get('event_name')}"
            )


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
    result = await sync_to_async(create_legacy_event, thread_sensitive=False)(
        name=name,
        description=description,
        channel_id=str(interaction.channel_id),
    )
    if not result.get("success"):
        await interaction.response.send_message(
            f"Failed to create event: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return

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

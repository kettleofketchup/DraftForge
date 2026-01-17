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
        if emoji not in RSVP_EMOJIS:
            return

        await self._handle_rsvp(payload, RSVP_EMOJIS[emoji])

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """Remove RSVP when user removes reaction."""
        emoji = str(payload.emoji)
        if emoji not in RSVP_EMOJIS:
            return

        await self._remove_rsvp(payload)

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

    bot.run(token)

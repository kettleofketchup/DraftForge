# Discord Bot Integration Design

## Overview

A Discord bot integrated with the Django backend that provides:
- Slash commands for user interaction
- Admin utility functions for sending templated notifications
- Event creation and RSVP tracking with reactions
- Recurring weekly events with Celery scheduling

## Architecture

### Discord Bot as Standalone Django App

```
backend/discord_bot/        # Created via: python manage.py startapp discord_bot
├── __init__.py
├── admin.py               # Admin interface for templates, events, RSVPs
├── apps.py                # DiscordBotConfig
├── models.py              # EventTemplate, ScheduledEvent, RSVP, etc.
├── migrations/            # Auto-generated migrations
├── bot.py                 # Discord bot client & slash commands
├── tasks.py               # Celery tasks (60-second scheduler check)
├── utils.py               # Admin utility functions for sending embeds
├── embeds.py              # Pre-built embed templates (tournament, draft, etc.)
├── management/
│   └── commands/
│       └── run_discord_bot.py  # Management command to start bot
└── tests.py               # Tests for bot functionality
```

### Registration Points

- `INSTALLED_APPS` in `backend/backend/settings.py`
- `apps = []` in `backend/tasks.py` for Celery autodiscovery
- Migrations via standard `python manage.py makemigrations discord_bot`

### Bot Process

- Runs alongside Django via management command: `python manage.py run_discord_bot`
- Separate Docker service in docker-compose
- Celery beat schedules the 60-second event check task

## Data Models

### EventTemplate

Reusable templates for events and announcements.

```python
class EventTemplate(models.Model):
    TEMPLATE_TYPE_CHOICES = [
        ('event', 'Discord Event'),      # Creates Discord Event + announcement
        ('announcement', 'Announcement'), # Message only
    ]

    name = models.CharField(max_length=100)           # "Weekly Tournament"
    template_type = models.CharField(choices=TEMPLATE_TYPE_CHOICES)
    title = models.CharField(max_length=256)          # Embed title
    description = models.TextField()                  # Embed description (supports placeholders)
    color = models.CharField(max_length=7)            # Hex color for embed
    channel_id = models.CharField(max_length=20)      # Discord channel to post in
    include_rsvp = models.BooleanField(default=True)  # Add reaction buttons
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
```

### ScheduledEvent

Recurring or one-time scheduled posts.

```python
class ScheduledEvent(models.Model):
    template = models.ForeignKey(EventTemplate, on_delete=models.CASCADE)

    # Scheduling
    is_recurring = models.BooleanField(default=False)
    day_of_week = models.IntegerField(null=True)      # 0=Monday, 6=Sunday
    time_of_day = models.TimeField()                  # When to post
    next_post_at = models.DateTimeField()             # Celery checks this

    # Discord references (after posting)
    discord_event_id = models.CharField(max_length=20, null=True)
    discord_message_id = models.CharField(max_length=20, null=True)

    is_active = models.BooleanField(default=True)
```

### RSVP

Tracks user responses via reactions.

```python
class RSVP(models.Model):
    STATUS_CHOICES = [
        ('yes', 'Attending'),
        ('maybe', 'Maybe'),
        ('no', 'Not Attending'),
    ]

    scheduled_event = models.ForeignKey(ScheduledEvent, on_delete=models.CASCADE)
    discord_user_id = models.CharField(max_length=20)
    discord_username = models.CharField(max_length=100)
    status = models.CharField(choices=STATUS_CHOICES)
    responded_at = models.DateTimeField(auto_now=True)
```

## Admin Utility Functions

### Core Utilities in `utils.py`

```python
# Send a pre-built templated embed
async def send_tournament_created(tournament, channel_id=None):
    """Notify Discord when a tournament is created."""

async def send_draft_ready(draft, channel_id=None):
    """Notify Discord when a draft is ready to start."""

async def send_results_posted(tournament, channel_id=None):
    """Notify Discord when tournament results are posted."""

# Generic embed sender (used by templates)
async def send_embed(channel_id, title, description, color, fields=None):
    """Send a rich embed to a Discord channel."""

# Event creation
async def create_discord_event(guild_id, name, description, start_time, end_time=None):
    """Create a native Discord scheduled event."""

async def post_event_announcement(template, scheduled_event):
    """Post announcement message with RSVP reactions."""
```

### Sync Wrappers for Django Views

```python
# Synchronous versions for calling from Django views/signals
def sync_send_tournament_created(tournament, channel_id=None):
    """Sync wrapper - runs async function in event loop."""

def sync_send_embed(channel_id, title, description, color, fields=None):
    """Sync wrapper for generic embed sending."""
```

### Usage Example in Django

```python
# In a view or signal after tournament creation
from discord_bot.utils import sync_send_tournament_created

def create_tournament(request):
    tournament = Tournament.objects.create(...)
    sync_send_tournament_created(tournament)
    return Response(...)
```

## Slash Commands

### Bot Setup in `bot.py`

```python
import discord
from discord import app_commands

class DTXBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.reactions = True
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
```

### Commands

#### `/roles` - Link to Position Selection

```python
@bot.tree.command(name="roles", description="Set your Dota 2 position preferences")
async def roles(interaction: discord.Interaction):
    """Links user to DTX website for role selection."""
    url = f"{settings.SITE_URL}/profile/roles?discord_id={interaction.user.id}"
    embed = discord.Embed(
        title="Set Your Roles",
        description=f"[Click here to set your position preferences]({url})",
        color=0x5865F2
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)
```

#### `/event` - Create Event (Admin Only)

```python
@bot.tree.command(name="event", description="Create a new event")
@app_commands.checks.has_permissions(administrator=True)
async def create_event(interaction: discord.Interaction, name: str, date: str, time: str):
    """Admin command to create event from Discord."""
    # Creates ScheduledEvent, posts announcement with RSVP reactions
```

### Reaction Handling for RSVP

```python
@bot.event
async def on_raw_reaction_add(payload):
    """Track RSVP when user reacts."""
    # Map emoji to status, update or create RSVP record
    # ✅ = yes, ❓ = maybe, ❌ = no

@bot.event
async def on_raw_reaction_remove(payload):
    """Remove RSVP when user removes reaction."""
```

## Celery Tasks

### Scheduler Task in `tasks.py`

```python
from celery import shared_task
from django.utils import timezone
from .models import ScheduledEvent
from .utils import sync_post_event_announcement, sync_create_discord_event

@shared_task
def check_scheduled_events():
    """Runs every 60 seconds - posts events that are due."""
    now = timezone.now()

    due_events = ScheduledEvent.objects.filter(
        is_active=True,
        next_post_at__lte=now,
        discord_message_id__isnull=True  # Not yet posted
    )

    for scheduled_event in due_events:
        template = scheduled_event.template

        # Create Discord Event if template type is 'event'
        if template.template_type == 'event':
            discord_event_id = sync_create_discord_event(
                name=template.title,
                description=template.description,
                start_time=scheduled_event.next_post_at
            )
            scheduled_event.discord_event_id = discord_event_id

        # Post announcement message with RSVP reactions
        message_id = sync_post_event_announcement(template, scheduled_event)
        scheduled_event.discord_message_id = message_id

        # Schedule next occurrence if recurring
        if scheduled_event.is_recurring:
            scheduled_event.next_post_at = calculate_next_post(scheduled_event)
            scheduled_event.discord_message_id = None  # Reset for next week

        scheduled_event.save()


def calculate_next_post(scheduled_event):
    """Calculate next posting time (7 days from now at same time)."""
    from datetime import timedelta
    return scheduled_event.next_post_at + timedelta(days=7)
```

### Celery Beat Schedule

Add to `backend/celery.py`:

```python
app.conf.beat_schedule = {
    'check-scheduled-events': {
        'task': 'discord_bot.tasks.check_scheduled_events',
        'schedule': 60.0,  # Every 60 seconds
    },
}
```

## Configuration

### Environment Variables

```bash
# Discord Bot Credentials
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_GUILD_ID=your_guild_id_here          # Your DTX Discord server
DISCORD_ADMIN_CHANNEL_ID=channel_id_here     # Default channel for admin announcements
```

### Django Settings

Add to `backend/backend/settings.py`:

```python
DISCORD_BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
DISCORD_GUILD_ID = os.environ.get('DISCORD_GUILD_ID')
DISCORD_ADMIN_CHANNEL_ID = os.environ.get('DISCORD_ADMIN_CHANNEL_ID')
```

### Management Command

`backend/discord_bot/management/commands/run_discord_bot.py`:

```python
from django.core.management.base import BaseCommand
from discord_bot.bot import DTXBot
from django.conf import settings

class Command(BaseCommand):
    help = 'Starts the Discord bot'

    def handle(self, *args, **options):
        bot = DTXBot()
        self.stdout.write('Starting Discord bot...')
        bot.run(settings.DISCORD_BOT_TOKEN)
```

### Docker Integration

Add to `docker-compose.debug.yaml`:

```yaml
discord_bot:
  build: ./backend
  command: python manage.py run_discord_bot
  env_file: .env.dev
  depends_on:
    - redis
    - backend
```

## Pre-built Embed Templates

### `embeds.py`

```python
import discord
from django.conf import settings

def tournament_created_embed(tournament):
    """Rich embed for tournament announcements."""
    return discord.Embed(
        title=f"New Tournament: {tournament.name}",
        description=tournament.description or "A new tournament has been created!",
        color=0x00FF00,
        url=f"{settings.SITE_URL}/tournaments/{tournament.id}"
    ).add_field(
        name="Date", value=tournament.date.strftime("%B %d, %Y"), inline=True
    ).add_field(
        name="Format", value=tournament.format, inline=True
    )

def draft_ready_embed(draft):
    """Rich embed when draft is ready to start."""
    return discord.Embed(
        title=f"Draft Ready: {draft.name}",
        description="The draft is ready to begin!",
        color=0x5865F2,
        url=f"{settings.SITE_URL}/drafts/{draft.id}"
    )

def results_posted_embed(tournament):
    """Rich embed for tournament results."""
    return discord.Embed(
        title=f"Results Posted: {tournament.name}",
        description="Check out the final standings!",
        color=0xFFD700,
        url=f"{settings.SITE_URL}/tournaments/{tournament.id}/results"
    )

def event_announcement_embed(template, scheduled_event):
    """Build embed from EventTemplate."""
    return discord.Embed(
        title=template.title,
        description=template.description,
        color=int(template.color.lstrip('#'), 16)
    ).set_footer(text="React: Yes | Maybe | No")
```

## Feature Summary

| Feature | Description |
|---------|-------------|
| `/roles` command | Links users to DTX website for position selection |
| `/event` command | Admins create events from Discord |
| Admin utilities | `sync_send_tournament_created()`, `sync_send_embed()`, etc. |
| Event templates | Configurable templates for Events vs Announcements |
| Recurring events | Weekly auto-posting with admin-configurable schedules |
| RSVP tracking | Yes, Maybe, No reactions stored in database |
| Celery scheduler | 60-second check for due events |

## Dependencies

- `discord.py` (~2.3+)

## Future Phase

- Sync Discord RSVPs to DTX website registrations (requires linked Discord accounts)

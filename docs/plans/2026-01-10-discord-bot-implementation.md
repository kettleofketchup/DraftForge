# Discord Bot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Discord bot functionality for slash commands, event scheduling, RSVP tracking, and admin notifications.

**Architecture:** Extend existing `discordbot` Django app with models for events/RSVPs, a discord.py bot client, Celery tasks for scheduled posting, and utility functions for sending embeds. Bot runs as separate process via management command.

**Tech Stack:** Django, discord.py, Celery, Redis (existing)

---

## Task 1: Add Models

**Files:**
- Modify: `backend/discordbot/models.py`
- Test: `backend/discordbot/tests.py`

**Step 1: Write the failing test**

```python
# backend/discordbot/tests.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from discordbot.models import EventTemplate, ScheduledEvent, RSVP

User = get_user_model()


class EventTemplateModelTest(TestCase):
    def test_create_event_template(self):
        """EventTemplate can be created with required fields."""
        template = EventTemplate.objects.create(
            name="Weekly Tournament",
            template_type="event",
            title="DTX Weekly",
            description="Join us for the weekly tournament!",
            color="#00FF00",
            channel_id="123456789012345678",
            include_rsvp=True,
        )
        self.assertEqual(template.name, "Weekly Tournament")
        self.assertEqual(template.template_type, "event")


class ScheduledEventModelTest(TestCase):
    def setUp(self):
        self.template = EventTemplate.objects.create(
            name="Test Event",
            template_type="announcement",
            title="Test",
            description="Test description",
            color="#FF0000",
            channel_id="123456789012345678",
        )

    def test_create_scheduled_event(self):
        """ScheduledEvent can be created linked to a template."""
        from django.utils import timezone
        from datetime import time

        event = ScheduledEvent.objects.create(
            template=self.template,
            is_recurring=True,
            day_of_week=0,  # Monday
            time_of_day=time(19, 0),  # 7 PM
            next_post_at=timezone.now(),
        )
        self.assertTrue(event.is_recurring)
        self.assertEqual(event.day_of_week, 0)


class RSVPModelTest(TestCase):
    def setUp(self):
        self.template = EventTemplate.objects.create(
            name="Test Event",
            template_type="event",
            title="Test",
            description="Test",
            color="#0000FF",
            channel_id="123456789012345678",
        )
        from django.utils import timezone
        from datetime import time

        self.scheduled_event = ScheduledEvent.objects.create(
            template=self.template,
            next_post_at=timezone.now(),
        )

    def test_create_rsvp(self):
        """RSVP can be created for a scheduled event."""
        rsvp = RSVP.objects.create(
            scheduled_event=self.scheduled_event,
            discord_user_id="987654321098765432",
            discord_username="TestUser",
            status="yes",
        )
        self.assertEqual(rsvp.status, "yes")
        self.assertEqual(rsvp.discord_username, "TestUser")
```

**Step 2: Run test to verify it fails**

Run: `inv test.exec --service backend --cmd 'python backend/manage.py test discordbot.tests -v 2'`
Expected: FAIL with "cannot import name 'EventTemplate' from 'discordbot.models'"

**Step 3: Write the models**

```python
# backend/discordbot/models.py
from django.db import models
from django.conf import settings


class EventTemplate(models.Model):
    """Reusable template for Discord events and announcements."""

    TEMPLATE_TYPE_CHOICES = [
        ("event", "Discord Event"),
        ("announcement", "Announcement"),
    ]

    name = models.CharField(max_length=100)
    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPE_CHOICES)
    title = models.CharField(max_length=256)
    description = models.TextField()
    color = models.CharField(max_length=7)  # Hex color
    channel_id = models.CharField(max_length=20)
    include_rsvp = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.template_type})"


class ScheduledEvent(models.Model):
    """Recurring or one-time scheduled event posts."""

    template = models.ForeignKey(
        EventTemplate,
        on_delete=models.CASCADE,
        related_name="scheduled_events",
    )

    # Scheduling
    is_recurring = models.BooleanField(default=False)
    day_of_week = models.IntegerField(null=True, blank=True)  # 0=Monday, 6=Sunday
    time_of_day = models.TimeField(null=True, blank=True)
    next_post_at = models.DateTimeField()

    # Discord references (after posting)
    discord_event_id = models.CharField(max_length=20, null=True, blank=True)
    discord_message_id = models.CharField(max_length=20, null=True, blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.template.name} - next: {self.next_post_at}"


class RSVP(models.Model):
    """Tracks user RSVP responses via reactions."""

    STATUS_CHOICES = [
        ("yes", "Attending"),
        ("maybe", "Maybe"),
        ("no", "Not Attending"),
    ]

    scheduled_event = models.ForeignKey(
        ScheduledEvent,
        on_delete=models.CASCADE,
        related_name="rsvps",
    )
    discord_user_id = models.CharField(max_length=20)
    discord_username = models.CharField(max_length=100)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    responded_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["scheduled_event", "discord_user_id"]

    def __str__(self):
        return f"{self.discord_username}: {self.status}"
```

**Step 4: Create and run migrations**

Run: `inv test.exec --service backend --cmd 'python backend/manage.py makemigrations discordbot'`
Run: `inv test.exec --service backend --cmd 'python backend/manage.py migrate discordbot'`

**Step 5: Run test to verify it passes**

Run: `inv test.exec --service backend --cmd 'python backend/manage.py test discordbot.tests -v 2'`
Expected: PASS (3 tests)

**Step 6: Commit**

```bash
git add backend/discordbot/models.py backend/discordbot/tests.py backend/discordbot/migrations/
git commit -m "feat(discordbot): add EventTemplate, ScheduledEvent, RSVP models"
```

---

## Task 2: Register Models in Admin

**Files:**
- Modify: `backend/discordbot/admin.py`

**Step 1: Update admin.py**

```python
# backend/discordbot/admin.py
from django.contrib import admin
from .models import EventTemplate, ScheduledEvent, RSVP


@admin.register(EventTemplate)
class EventTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "template_type", "channel_id", "include_rsvp", "created_at"]
    list_filter = ["template_type", "include_rsvp"]
    search_fields = ["name", "title"]


@admin.register(ScheduledEvent)
class ScheduledEventAdmin(admin.ModelAdmin):
    list_display = [
        "template",
        "is_recurring",
        "day_of_week",
        "next_post_at",
        "is_active",
    ]
    list_filter = ["is_recurring", "is_active", "day_of_week"]
    raw_id_fields = ["template"]


@admin.register(RSVP)
class RSVPAdmin(admin.ModelAdmin):
    list_display = [
        "scheduled_event",
        "discord_username",
        "status",
        "responded_at",
    ]
    list_filter = ["status"]
    search_fields = ["discord_username", "discord_user_id"]
    raw_id_fields = ["scheduled_event"]
```

**Step 2: Verify admin loads**

Run: `inv test.exec --service backend --cmd 'python backend/manage.py check'`
Expected: "System check identified no issues"

**Step 3: Commit**

```bash
git add backend/discordbot/admin.py
git commit -m "feat(discordbot): register models in Django admin"
```

---

## Task 3: Add Embed Builders

**Files:**
- Create: `backend/discordbot/embeds.py`
- Test: `backend/discordbot/tests.py` (append)

**Step 1: Write the failing test**

```python
# Append to backend/discordbot/tests.py

class EmbedBuildersTest(TestCase):
    def test_event_announcement_embed(self):
        """event_announcement_embed returns dict with correct structure."""
        from discordbot.embeds import event_announcement_embed

        template = EventTemplate.objects.create(
            name="Test",
            template_type="event",
            title="Weekly Game Night",
            description="Join us for fun!",
            color="#5865F2",
            channel_id="123",
        )
        embed = event_announcement_embed(template)

        self.assertEqual(embed["title"], "Weekly Game Night")
        self.assertEqual(embed["description"], "Join us for fun!")
        self.assertEqual(embed["color"], 0x5865F2)
        self.assertIn("footer", embed)

    def test_tournament_created_embed(self):
        """tournament_created_embed returns dict with tournament info."""
        from discordbot.embeds import tournament_created_embed
        from app.models import Tournament

        tournament = Tournament.objects.create(
            name="Test Tournament",
            description="A test tournament",
        )
        embed = tournament_created_embed(tournament)

        self.assertIn("Test Tournament", embed["title"])
        self.assertIn("color", embed)
```

**Step 2: Run test to verify it fails**

Run: `inv test.exec --service backend --cmd 'python backend/manage.py test discordbot.tests.EmbedBuildersTest -v 2'`
Expected: FAIL with "cannot import name 'event_announcement_embed'"

**Step 3: Write the embeds module**

```python
# backend/discordbot/embeds.py
"""Pre-built Discord embed templates."""

from django.conf import settings


def event_announcement_embed(template):
    """Build embed dict from EventTemplate."""
    return {
        "title": template.title,
        "description": template.description,
        "color": int(template.color.lstrip("#"), 16),
        "footer": {"text": "React: \u2705 Yes | \u2753 Maybe | \u274c No"},
    }


def tournament_created_embed(tournament):
    """Rich embed for tournament announcements."""
    embed = {
        "title": f"\U0001f3c6 New Tournament: {tournament.name}",
        "description": tournament.description or "A new tournament has been created!",
        "color": 0x00FF00,
        "fields": [],
    }

    if hasattr(settings, "SITE_URL"):
        embed["url"] = f"{settings.SITE_URL}/tournament/{tournament.id}"

    return embed


def draft_ready_embed(draft):
    """Rich embed when draft is ready to start."""
    embed = {
        "title": f"\U0001f4cb Draft Ready: {draft.name}",
        "description": "The draft is ready to begin!",
        "color": 0x5865F2,
    }

    if hasattr(settings, "SITE_URL"):
        embed["url"] = f"{settings.SITE_URL}/draft/{draft.id}"

    return embed


def results_posted_embed(tournament):
    """Rich embed for tournament results."""
    embed = {
        "title": f"\U0001f389 Results Posted: {tournament.name}",
        "description": "Check out the final standings!",
        "color": 0xFFD700,
    }

    if hasattr(settings, "SITE_URL"):
        embed["url"] = f"{settings.SITE_URL}/tournament/{tournament.id}/results"

    return embed
```

**Step 4: Run test to verify it passes**

Run: `inv test.exec --service backend --cmd 'python backend/manage.py test discordbot.tests.EmbedBuildersTest -v 2'`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/discordbot/embeds.py backend/discordbot/tests.py
git commit -m "feat(discordbot): add embed builder functions"
```

---

## Task 4: Add Utility Functions for Sending Messages

**Files:**
- Create: `backend/discordbot/utils.py`
- Test: `backend/discordbot/tests.py` (append)

**Step 1: Write the failing test**

```python
# Append to backend/discordbot/tests.py
from unittest.mock import patch, MagicMock


class UtilsTest(TestCase):
    @patch("discordbot.utils.requests.post")
    def test_sync_send_embed(self, mock_post):
        """sync_send_embed sends POST to Discord webhook."""
        from discordbot.utils import sync_send_embed

        mock_post.return_value = MagicMock(status_code=200)

        result = sync_send_embed(
            channel_id="123456789",
            title="Test Title",
            description="Test Description",
            color=0x00FF00,
        )

        self.assertTrue(mock_post.called)

    @patch("discordbot.utils.requests.post")
    def test_sync_send_templated_embed(self, mock_post):
        """sync_send_templated_embed sends embed from EventTemplate."""
        from discordbot.utils import sync_send_templated_embed

        mock_post.return_value = MagicMock(status_code=200)

        template = EventTemplate.objects.create(
            name="Test",
            template_type="announcement",
            title="Test Title",
            description="Test Desc",
            color="#FF0000",
            channel_id="123456789",
        )

        sync_send_templated_embed(template)
        self.assertTrue(mock_post.called)
```

**Step 2: Run test to verify it fails**

Run: `inv test.exec --service backend --cmd 'python backend/manage.py test discordbot.tests.UtilsTest -v 2'`
Expected: FAIL with "cannot import name 'sync_send_embed'"

**Step 3: Write the utils module**

```python
# backend/discordbot/utils.py
"""Admin utility functions for sending Discord messages."""

import logging
import requests
from django.conf import settings
from .embeds import event_announcement_embed

log = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"


def _get_headers():
    """Get authorization headers for Discord API."""
    return {
        "Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }


def sync_send_embed(channel_id, title, description, color, fields=None, footer=None):
    """
    Send a rich embed to a Discord channel.

    Args:
        channel_id: Discord channel ID
        title: Embed title
        description: Embed description
        color: Integer color value (e.g., 0x00FF00)
        fields: Optional list of field dicts with 'name', 'value', 'inline'
        footer: Optional footer dict with 'text'

    Returns:
        dict: API response or None on error
    """
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"

    embed = {
        "title": title,
        "description": description,
        "color": color,
    }

    if fields:
        embed["fields"] = fields

    if footer:
        embed["footer"] = footer

    payload = {"embeds": [embed]}

    try:
        response = requests.post(url, json=payload, headers=_get_headers())
        response.raise_for_status()
        log.info(f"Sent embed to channel {channel_id}: {title}")
        return response.json()
    except requests.RequestException as e:
        log.error(f"Failed to send embed to channel {channel_id}: {e}")
        return None


def sync_send_templated_embed(template):
    """
    Send an embed using an EventTemplate.

    Args:
        template: EventTemplate instance

    Returns:
        dict: API response or None on error
    """
    embed = event_announcement_embed(template)
    return sync_send_embed(
        channel_id=template.channel_id,
        title=embed["title"],
        description=embed["description"],
        color=embed["color"],
        footer=embed.get("footer"),
    )


def sync_send_tournament_created(tournament, channel_id=None):
    """
    Notify Discord when a tournament is created.

    Args:
        tournament: Tournament model instance
        channel_id: Override channel (defaults to DISCORD_ADMIN_CHANNEL_ID)
    """
    from .embeds import tournament_created_embed

    channel = channel_id or getattr(settings, "DISCORD_ADMIN_CHANNEL_ID", None)
    if not channel:
        log.warning("No channel_id provided and DISCORD_ADMIN_CHANNEL_ID not set")
        return None

    embed = tournament_created_embed(tournament)
    return sync_send_embed(
        channel_id=channel,
        title=embed["title"],
        description=embed["description"],
        color=embed["color"],
        fields=embed.get("fields"),
    )


def sync_send_draft_ready(draft, channel_id=None):
    """Notify Discord when a draft is ready to start."""
    from .embeds import draft_ready_embed

    channel = channel_id or getattr(settings, "DISCORD_ADMIN_CHANNEL_ID", None)
    if not channel:
        log.warning("No channel_id provided and DISCORD_ADMIN_CHANNEL_ID not set")
        return None

    embed = draft_ready_embed(draft)
    return sync_send_embed(
        channel_id=channel,
        title=embed["title"],
        description=embed["description"],
        color=embed["color"],
    )


def sync_send_results_posted(tournament, channel_id=None):
    """Notify Discord when tournament results are posted."""
    from .embeds import results_posted_embed

    channel = channel_id or getattr(settings, "DISCORD_ADMIN_CHANNEL_ID", None)
    if not channel:
        log.warning("No channel_id provided and DISCORD_ADMIN_CHANNEL_ID not set")
        return None

    embed = results_posted_embed(tournament)
    return sync_send_embed(
        channel_id=channel,
        title=embed["title"],
        description=embed["description"],
        color=embed["color"],
    )


def sync_add_reactions(channel_id, message_id, emojis=None):
    """
    Add reaction emojis to a message for RSVP.

    Args:
        channel_id: Discord channel ID
        message_id: Discord message ID
        emojis: List of emoji strings (defaults to RSVP emojis)
    """
    if emojis is None:
        emojis = ["\u2705", "\u2753", "\u274c"]  # checkmark, question, x

    for emoji in emojis:
        url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me"
        try:
            response = requests.put(url, headers=_get_headers())
            response.raise_for_status()
        except requests.RequestException as e:
            log.error(f"Failed to add reaction {emoji}: {e}")
```

**Step 4: Run test to verify it passes**

Run: `inv test.exec --service backend --cmd 'python backend/manage.py test discordbot.tests.UtilsTest -v 2'`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/discordbot/utils.py backend/discordbot/tests.py
git commit -m "feat(discordbot): add utility functions for sending embeds"
```

---

## Task 5: Add Celery Task for Scheduled Events

**Files:**
- Create: `backend/discordbot/tasks.py`
- Modify: `backend/config/celery.py`
- Test: `backend/discordbot/tests.py` (append)

**Step 1: Write the failing test**

```python
# Append to backend/discordbot/tests.py
from datetime import timedelta
from django.utils import timezone


class ScheduledEventTaskTest(TestCase):
    def setUp(self):
        self.template = EventTemplate.objects.create(
            name="Test Event",
            template_type="announcement",
            title="Test",
            description="Test description",
            color="#FF0000",
            channel_id="123456789012345678",
        )

    @patch("discordbot.tasks.sync_send_templated_embed")
    @patch("discordbot.tasks.sync_add_reactions")
    def test_check_scheduled_events_posts_due_events(self, mock_reactions, mock_send):
        """check_scheduled_events posts events that are due."""
        from discordbot.tasks import check_scheduled_events

        mock_send.return_value = {"id": "999888777"}

        # Create a due event (next_post_at in the past)
        event = ScheduledEvent.objects.create(
            template=self.template,
            next_post_at=timezone.now() - timedelta(minutes=5),
            is_active=True,
        )

        check_scheduled_events()

        mock_send.assert_called_once()
        event.refresh_from_db()
        self.assertEqual(event.discord_message_id, "999888777")

    @patch("discordbot.tasks.sync_send_templated_embed")
    def test_check_scheduled_events_skips_future_events(self, mock_send):
        """check_scheduled_events skips events not yet due."""
        from discordbot.tasks import check_scheduled_events

        # Create a future event
        ScheduledEvent.objects.create(
            template=self.template,
            next_post_at=timezone.now() + timedelta(hours=1),
            is_active=True,
        )

        check_scheduled_events()

        mock_send.assert_not_called()

    @patch("discordbot.tasks.sync_send_templated_embed")
    @patch("discordbot.tasks.sync_add_reactions")
    def test_recurring_event_reschedules(self, mock_reactions, mock_send):
        """Recurring events get rescheduled after posting."""
        from discordbot.tasks import check_scheduled_events
        from datetime import time

        mock_send.return_value = {"id": "111222333"}

        original_time = timezone.now() - timedelta(minutes=5)
        event = ScheduledEvent.objects.create(
            template=self.template,
            is_recurring=True,
            day_of_week=0,
            time_of_day=time(19, 0),
            next_post_at=original_time,
            is_active=True,
        )

        check_scheduled_events()

        event.refresh_from_db()
        # Should be rescheduled 7 days later
        self.assertGreater(event.next_post_at, original_time)
        # discord_message_id should be cleared for next posting
        self.assertIsNone(event.discord_message_id)
```

**Step 2: Run test to verify it fails**

Run: `inv test.exec --service backend --cmd 'python backend/manage.py test discordbot.tests.ScheduledEventTaskTest -v 2'`
Expected: FAIL with "cannot import name 'check_scheduled_events'"

**Step 3: Write the tasks module**

```python
# backend/discordbot/tasks.py
"""Celery tasks for Discord bot scheduled operations."""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import ScheduledEvent
from .utils import sync_send_templated_embed, sync_add_reactions

log = logging.getLogger(__name__)


@shared_task
def check_scheduled_events():
    """
    Check for and post scheduled events that are due.
    Runs every 60 seconds via Celery beat.
    """
    now = timezone.now()

    due_events = ScheduledEvent.objects.filter(
        is_active=True,
        next_post_at__lte=now,
        discord_message_id__isnull=True,  # Not yet posted
    ).select_related("template")

    for scheduled_event in due_events:
        template = scheduled_event.template

        log.info(f"Posting scheduled event: {template.name}")

        # Send the announcement message
        response = sync_send_templated_embed(template)

        if response and "id" in response:
            message_id = response["id"]
            scheduled_event.discord_message_id = message_id

            # Add RSVP reactions if enabled
            if template.include_rsvp:
                sync_add_reactions(template.channel_id, message_id)

            log.info(f"Posted event {template.name}, message_id={message_id}")
        else:
            log.error(f"Failed to post event {template.name}")
            continue

        # Handle recurring events
        if scheduled_event.is_recurring:
            # Schedule next occurrence (7 days later)
            scheduled_event.next_post_at = scheduled_event.next_post_at + timedelta(
                days=7
            )
            scheduled_event.discord_message_id = None  # Reset for next posting
            log.info(
                f"Rescheduled recurring event {template.name} to {scheduled_event.next_post_at}"
            )

        scheduled_event.save()

    return f"Processed {due_events.count()} scheduled events"
```

**Step 4: Add task to Celery beat schedule**

```python
# Modify backend/config/celery.py - add to beat_schedule dict:

# Add this entry to app.conf.beat_schedule:
    "check-discord-scheduled-events": {
        "task": "discordbot.tasks.check_scheduled_events",
        "schedule": 60.0,  # Every 60 seconds
    },
```

**Step 5: Run test to verify it passes**

Run: `inv test.exec --service backend --cmd 'python backend/manage.py test discordbot.tests.ScheduledEventTaskTest -v 2'`
Expected: PASS (3 tests)

**Step 6: Commit**

```bash
git add backend/discordbot/tasks.py backend/config/celery.py backend/discordbot/tests.py
git commit -m "feat(discordbot): add Celery task for scheduled event posting"
```

---

## Task 6: Add Discord Bot Client with Slash Commands

**Files:**
- Create: `backend/discordbot/bot.py`

**Step 1: Write the bot client**

```python
# backend/discordbot/bot.py
"""Discord bot client with slash commands."""

import logging
import os
import sys

import discord
from discord import app_commands
from django.conf import settings

log = logging.getLogger(__name__)

# Emoji mappings for RSVP
RSVP_EMOJIS = {
    "\u2705": "yes",  # checkmark
    "\u2753": "maybe",  # question mark
    "\u274c": "no",  # x mark
}


class DTXBot(discord.Client):
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
        from discordbot.models import ScheduledEvent, RSVP

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
        from discordbot.models import ScheduledEvent, RSVP

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
bot = DTXBot()


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
@app_commands.checks.has_permissions(administrator=True)
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
    if isinstance(error, app_commands.MissingPermissions):
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
```

**Step 2: Verify syntax**

Run: `inv test.exec --service backend --cmd 'python -c "import discordbot.bot"'`
Expected: No errors

**Step 3: Commit**

```bash
git add backend/discordbot/bot.py
git commit -m "feat(discordbot): add Discord bot client with slash commands"
```

---

## Task 7: Add Management Command to Run Bot

**Files:**
- Create: `backend/discordbot/management/__init__.py`
- Create: `backend/discordbot/management/commands/__init__.py`
- Create: `backend/discordbot/management/commands/run_discord_bot.py`

**Step 1: Create directory structure and management command**

```python
# backend/discordbot/management/__init__.py
# (empty file)
```

```python
# backend/discordbot/management/commands/__init__.py
# (empty file)
```

```python
# backend/discordbot/management/commands/run_discord_bot.py
"""Management command to run the Discord bot."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Starts the Discord bot"

    def handle(self, *args, **options):
        from discordbot.bot import run_bot

        self.stdout.write(self.style.SUCCESS("Starting Discord bot..."))
        run_bot()
```

**Step 2: Verify command is discoverable**

Run: `inv test.exec --service backend --cmd 'python backend/manage.py help run_discord_bot'`
Expected: Shows help for run_discord_bot command

**Step 3: Commit**

```bash
git add backend/discordbot/management/
git commit -m "feat(discordbot): add management command to run bot"
```

---

## Task 8: Add Environment Variables

**Files:**
- Modify: `backend/.env.example`
- Modify: `docker/.env.dev` (if exists)

**Step 1: Update .env.example**

Add these lines to `backend/.env.example`:

```
# Discord Bot
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_ADMIN_CHANNEL_ID=your_channel_id_here
```

**Step 2: Add DISCORD_ADMIN_CHANNEL_ID to settings**

Add to `backend/backend/settings.py` after existing Discord settings:

```python
DISCORD_ADMIN_CHANNEL_ID = os.environ.get("DISCORD_ADMIN_CHANNEL_ID")
```

**Step 3: Commit**

```bash
git add backend/.env.example backend/backend/settings.py
git commit -m "feat(discordbot): add environment variable configuration"
```

---

## Task 9: Add Docker Service for Bot

**Files:**
- Modify: `docker/docker-compose.debug.yaml`

**Step 1: Add discord_bot service**

Add this service to `docker/docker-compose.debug.yaml`:

```yaml
  discord_bot:
    container_name: discord_bot
    image: ghcr.io/kettleofketchup/dota_tournament/backend-dev:latest
    env_file: "./docker/.env.dev"
    volumes:
      - ./backend/:/app/backend
      - ./poetry.lock/:/app/poetry.lock
      - ./pyproject.toml/:/app/pyproject.toml
    command: ["python", "backend/manage.py", "run_discord_bot"]
    depends_on:
      - redis
    networks:
      - dota2-network
    restart: unless-stopped
```

**Step 2: Commit**

```bash
git add docker/docker-compose.debug.yaml
git commit -m "feat(discordbot): add Docker service for Discord bot"
```

---

## Task 10: Run All Tests

**Step 1: Run complete test suite**

Run: `inv test.exec --service backend --cmd 'python backend/manage.py test discordbot.tests -v 2'`
Expected: All tests pass (10+ tests)

**Step 2: Run existing app tests to ensure no regressions**

Run: `inv test.exec --service backend --cmd 'python backend/manage.py test app.tests -v 2'`
Expected: All existing tests still pass

---

## Summary

After completing all tasks, you will have:

1. **Models**: EventTemplate, ScheduledEvent, RSVP with migrations
2. **Admin**: All models registered in Django admin
3. **Embeds**: Pre-built embed templates for tournaments, drafts, results
4. **Utils**: `sync_send_embed()`, `sync_send_tournament_created()`, etc.
5. **Celery Task**: `check_scheduled_events` running every 60 seconds
6. **Bot Client**: discord.py bot with `/roles` and `/event` commands
7. **Management Command**: `python manage.py run_discord_bot`
8. **Docker**: discord_bot service in docker-compose

**To start the bot locally:**
```bash
inv dev.up
inv dev.exec --service discord_bot --cmd 'python backend/manage.py run_discord_bot'
```

**To use admin utilities in Django code:**
```python
from discordbot.utils import sync_send_tournament_created
sync_send_tournament_created(tournament)
```

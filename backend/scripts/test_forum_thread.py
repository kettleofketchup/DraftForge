"""One-off script to test forum thread creation for event announcements.

Run from the backend directory:
    DJANGO_SETTINGS_MODULE=backend.settings DISABLE_CACHE=true \
    ../.venv/bin/python scripts/test_forum_thread.py
"""

import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

import django

django.setup()

from datetime import timedelta

from django.test.runner import DiscoverRunner
from django.utils import timezone

# Set up in-memory test DB
runner = DiscoverRunner(verbosity=0)
old_config = runner.setup_databases()

from app.models import CustomUser, Organization, PositionsModel
from discordbot.models import DiscordMessageLog
from events.models import Event, EventState
from events.tasks import send_event_announcement

# Create test data
org = Organization.objects.create(
    name="Forum Thread Test Org",
    discord_server_id="1467168401805017142",
)
positions = PositionsModel.objects.create()
user = CustomUser.objects.create(
    username="forum_admin", nickname="ForumAdmin", positions=positions
)
event = Event.objects.create(
    organization=org,
    name="Forum Thread Test Event",
    description="This should appear as a forum post with signup buttons!",
    scheduled_at=timezone.now() + timedelta(days=1),
    state=EventState.SIGNUPS_OPEN,
    created_by=user,
    discord_announcement=True,
    discord_announcement_channel_id="1482767177063858216",  # text channel fallback
    discord_post_signups=True,
    discord_post_signups_channel_id="1482767709279096893",  # forum channel
    max_players=10,
)

print(f"Created event pk={event.pk}: {event.name}")
print(f"Announcement channel: {event.discord_announcement_channel_id}")
print(f"Signups channel (forum): {event.discord_post_signups_channel_id}")
print()

result = send_event_announcement(event.pk)
print(f"Result: {result}")
print()

logs = DiscordMessageLog.objects.filter(
    source="event_announcement", source_id=event.pk
).order_by("created_at")

for i, log in enumerate(logs):
    print(f"Log #{i + 1}:")
    print(
        f"  success={log.success}, status={log.status_code}, channel={log.channel_id}"
    )
    print(f"  message_id={log.discord_message_id}")
    if log.response_data:
        thread_id = log.response_data.get("id")
        has_message = bool(log.response_data.get("message"))
        print(f"  thread_id={thread_id}, is_forum_thread={has_message}")
    print()

runner.teardown_databases(old_config)

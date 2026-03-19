"""Test forum thread creation with repeater, signup users, and all buttons.

Run: just py::script scripts/test_forum_thread.py
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

import django

django.setup()

from datetime import time, timedelta

from django.test.runner import DiscoverRunner
from django.utils import timezone

runner = DiscoverRunner(verbosity=0)
old_config = runner.setup_databases()

from app.models import CustomUser, GameType, Organization, PositionsModel
from discordbot.models import DiscordMessageLog
from events.models import (
    Event,
    EventRepeater,
    EventSignup,
    EventState,
    RepeatFrequency,
    SignupStatus,
)
from events.tasks import send_event_announcement

# Create org
org = Organization.objects.create(
    name="Forum Test Org",
    discord_server_id="1467168401805017142",
)

# Create repeater (so Notify Me button shows)
positions_admin = PositionsModel.objects.create()
admin_user = CustomUser.objects.create(
    username="forum_admin", nickname="ForumAdmin", positions=positions_admin
)
repeater = EventRepeater.objects.create(
    organization=org,
    name="Weekly Inhouse",
    frequency=RepeatFrequency.WEEKLY,
    day_of_week=2,
    time_of_day=time(20, 0),
    starts_at=timezone.now().date(),
    is_active=True,
    created_by=admin_user,
    discord_notify_new_events=True,
    discord_announcement=True,
    discord_announcement_channel_id="1482767177063858216",
)

# Create event linked to repeater
event = Event.objects.create(
    organization=org,
    event_repeater=repeater,
    name="Weekly Inhouse — March 19",
    description="Join us for our weekly inhouse! All skill levels welcome.",
    scheduled_at=timezone.now() + timedelta(days=1),
    state=EventState.SIGNUPS_OPEN,
    created_by=admin_user,
    discord_announcement=True,
    discord_announcement_channel_id="1482767177063858216",
    discord_post_signups=True,
    discord_post_signups_channel_id="1482767709279096893",
    max_players=10,
    auto_approve=True,
    game_type=GameType.DOTA2,
)

# Create some test signups so the embed shows users
positions1 = PositionsModel.objects.create()
player1 = CustomUser.objects.create(
    username="player_one", nickname="PlayerOne", positions=positions1
)
positions2 = PositionsModel.objects.create()
player2 = CustomUser.objects.create(
    username="player_two", nickname="PlayerTwo", positions=positions2
)

positions3 = PositionsModel.objects.create()
player3 = CustomUser.objects.create(
    username="player_three", nickname="MaybeMike", positions=positions3
)
positions4 = PositionsModel.objects.create()
player4 = CustomUser.objects.create(
    username="player_four", nickname="DeclinedDave", positions=positions4
)

signup1 = EventSignup.objects.create(
    event=event, user=player1, status=SignupStatus.CONFIRMED
)
signup2 = EventSignup.objects.create(
    event=event, user=player2, status=SignupStatus.APPROVED
)
signup3 = EventSignup.objects.create(
    event=event, user=player3, status=SignupStatus.TENTATIVE
)
signup4 = EventSignup.objects.create(
    event=event, user=player4, status=SignupStatus.CANCELLED
)
print(f"Signup 1: {player1.nickname} - {signup1.status}")
print(f"Signup 2: {player2.nickname} - {signup2.status}")
print(f"Signup 3: {player3.nickname} - {signup3.status}")
print(f"Signup 4: {player4.nickname} - {signup4.status}")
print()

# Send the announcement
print(f"Event: {event.name} (repeater={repeater.name})")
print(f"Forum channel: {event.discord_post_signups_channel_id}")
print()

result = send_event_announcement(event.pk)
print(f"Result: {result}")
print()

# Show logs
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

"""Delete spam reminder messages from Discord and mark as sent for idempotency."""

import os
import sys
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from discordbot.models import DiscordMessageLog
from discordbot.test_utils import delete_discord_message

sources = [
    "signup_reminder",
    "profile_reminder",
    "attendance_reminder",
    "event_announcement",
    "event_notice",
]
logs = DiscordMessageLog.objects.filter(
    source__in=sources,
    success=True,
    discord_message_id__isnull=False,
)

print(f"Found {logs.count()} messages to clean up")

deleted = 0
failed = 0
for log in logs:
    if log.discord_message_id:
        success = delete_discord_message(log.channel_id, log.discord_message_id)
        if success:
            deleted += 1
            print(f"  Deleted: {log.source} msg={log.discord_message_id}")
        else:
            failed += 1
            print(f"  Failed: {log.source} msg={log.discord_message_id}")
        time.sleep(0.5)

print(f"\nDone: {deleted} deleted, {failed} failed")
print("Log entries kept for idempotency")

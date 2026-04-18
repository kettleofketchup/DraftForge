"""Lightweight Celery app that doesn't load the full Django stack.

Uses config.settings_celery instead of backend.settings.
"""

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_celery")

import django

django.setup()

# Initialize telemetry (structlog + optional OTel tracing).
# Solo pool has no fork, so init once in the main process.
from telemetry.config import init_telemetry

init_telemetry()

app = Celery("dtx")
app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()
app.autodiscover_tasks(["events"], related_name="tournament_tasks")

# Beat schedule — copied from config/celery.py
_beat_schedule = {
    "sync-league-matches-every-minute": {
        "task": "steam.tasks.sync_league_matches_task",
        "schedule": 60.0,
    },
    "check-discord-scheduled-events": {
        "task": "discordbot.tasks.check_scheduled_events",
        "schedule": 60.0,
    },
    "refresh-discord-avatars": {
        "task": "app.tasks.avatar_refresh.refresh_discord_avatars",
        "schedule": 300.0,
        "kwargs": {"batch_size": 50},
    },
    "refresh-all-discord-data-daily": {
        "task": "app.tasks.avatar_refresh.refresh_all_discord_data",
        "schedule": crontab(hour=4, minute=0),
    },
}

_event_tasks = {
    "generate-upcoming-events-hourly": {
        "task": "events.tasks.generate_upcoming_events",
        "schedule": 3600.0,
    },
    "open-scheduled-signups-every-minute": {
        "task": "events.tasks.open_scheduled_signups",
        "schedule": 60.0,
    },
    "check-event-reminders": {
        "task": "events.tasks.check_event_reminders",
        "schedule": 30.0,
    },
    "sync-discord-events": {
        "task": "events.tasks.sync_discord_events",
        "schedule": 60.0,
    },
    "cleanup-stale-events-hourly": {
        "task": "events.tasks.cleanup_stale_events",
        "schedule": 3600.0,
    },
}

_beat_schedule.update(_event_tasks)

app.conf.beat_schedule = _beat_schedule


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")

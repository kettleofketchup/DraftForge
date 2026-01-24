import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

app = Celery("dtx")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Beat schedule for periodic tasks
app.conf.beat_schedule = {
    "sync-league-matches-every-minute": {
        "task": "steam.tasks.sync_league_matches_task",
        "schedule": 60.0,  # Every 60 seconds
    },
    "check-discord-scheduled-events": {
        "task": "discordbot.tasks.check_scheduled_events",
        "schedule": 60.0,  # Every 60 seconds
    },
    # Discord avatar refresh - check batch of users every 5 minutes
    "refresh-discord-avatars": {
        "task": "app.tasks.avatar_refresh.refresh_discord_avatars",
        "schedule": 300.0,  # Every 5 minutes
        "kwargs": {"batch_size": 50},
    },
    # Full Discord data refresh - run once daily at 4 AM
    "refresh-all-discord-data-daily": {
        "task": "app.tasks.avatar_refresh.refresh_all_discord_data",
        "schedule": crontab(hour=4, minute=0),
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")

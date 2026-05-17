import os

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

app = Celery("dtx")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
app.autodiscover_tasks(["events"], related_name="tournament_tasks")


@worker_process_init.connect
def init_worker_telemetry(**kwargs):
    """Re-initialize telemetry in each forked celery worker process.

    The main celery process loads Django settings (which calls init_telemetry),
    but forked worker processes don't inherit the OTel providers properly.
    This signal fires after fork, ensuring each worker has its own exporters.
    """
    # Reset guards so init_tracing and init_log_export run again in this process.
    # Both providers from the parent are stale after fork.
    import telemetry.tracing
    from telemetry.config import init_telemetry

    telemetry.tracing._tracing_initialized = False
    telemetry.tracing._log_export_initialized = False

    init_telemetry()


# Beat schedule for periodic tasks
_beat_schedule = {
    "sync-league-matches-every-minute": {
        "task": "steam.tasks.sync_all_steam_leagues_task",
        "schedule": 60.0,
    },
    "check-discord-scheduled-events": {
        "task": "discordbot.tasks.check_scheduled_events",
        "schedule": 60.0,
    },
    "sweep-stale-discord-leases": {
        "task": "discordbot.tasks.sweep_stale_discord_leases",
        "schedule": 60.0,  # 60s cadence: keeps worker-crash recovery <1.5 min
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
    # Daily batched avatar refresh. Pulls one full guild-member fetch per
    # org from the cached `discord_members_<guild_id>` (1 hr TTL — see
    # discordbot/services/users.py), then bulk-updates User.avatar via a
    # single CASE/WHEN UPDATE per 500-row batch. Admin Discord-member
    # searches during the day already repave that cache, so this task
    # picks up users who joined since yesterday without a separate fetch.
    "refresh-avatars-batched-daily": {
        "task": "app.tasks.avatar_refresh.refresh_avatars_batched",
        "schedule": crontab(hour=4, minute=15),  # 15 min after the daily sweep
    },
}

# Event-related tasks that write frequently to the DB.
# Disabled in test environment to prevent SQLite lock contention
# with Playwright E2E tests (celery worker is a separate process).
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

# Event tasks now write via internal HTTP API (no direct DB access),
# so they're safe to run alongside tests. Re-enable in all environments.
_beat_schedule.update(_event_tasks)

app.conf.beat_schedule = _beat_schedule


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")

import os

from celery import Celery

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
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")

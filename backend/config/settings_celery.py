"""Minimal Django settings for Celery workers.

Loads just enough Django to register tasks, connect to Redis, and access
the database (steam tasks use ORM directly). No middleware, no templates.
Event tasks communicate with Django/Daphne over HTTP via internal_client.py.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = "celery-worker-not-serving-http"
DEBUG = False
ALLOWED_HOSTS = []

# Minimal installed apps for task autodiscovery.
# Django contrib apps required because app.models imports AbstractUser.
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "config",
    "app",
    "events",
    "discordbot",
    "steam",
]

# Database — steam tasks (sync_league_matches, update_league_stats) use ORM
BASE_DIR = Path(__file__).resolve().parent.parent

db_name = "prod.db.sqlite3"
match os.environ.get("NODE_ENV", "").lower():
    case "dev":
        db_name = "dev.db.sqlite3"
    case "test":
        db_name = "test.db.sqlite3"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / db_name,
        "OPTIONS": {
            "timeout": 30,
            "transaction_mode": "IMMEDIATE",
        },
    }
}

# Celery configuration
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", f"redis://{REDIS_HOST}:6379/1")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", f"redis://{REDIS_HOST}:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True

INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "")

# Required by app.models at import time
AUTH_USER_MODEL = "app.CustomUser"

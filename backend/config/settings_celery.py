"""Minimal Django settings for Celery workers. No ORM, no DB.

Tasks communicate with Django/Daphne over HTTP via internal_client.py.
"""

import os

from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = "celery-worker-not-serving-http"
DEBUG = False
ALLOWED_HOSTS = []


def _env_bool(key, default=False):
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# Test-mode flag for Discord DM safety in tasks.
# When TEST=true, sync_send_dm only sends DMs to TEST_DISCORD_USER_ID and
# returns fake-success for everyone else (so recipient_count > 0 in tests
# without spamming real users).
TEST = _env_bool("TEST")
RELEASE = _env_bool("RELEASE")
TEST_DISCORD_USER_ID = os.environ.get("TEST_DISCORD_USER_ID", "243497113906970625")

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

# No database — all tasks use internal HTTP API
DATABASES = {}

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

# Discord bot token — required by discordbot.utils.sync_send_dm and friends.
# In TEST mode we still need this for the matching TEST_DISCORD_USER_ID path,
# and in production for real DMs from Celery tasks. Read the same env var
# the Daphne backend uses.
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")

# Public site URL used by Discord embed builders to construct links
# (e.g. /herodraft/<id>, /tournament/<id>/teams/draft). Without this,
# tournament_embeds._site_url() falls back to https://localhost.
SITE_URL = os.environ.get("SITE_URL", "https://localhost")

# Required by app.models at import time
AUTH_USER_MODEL = "app.CustomUser"

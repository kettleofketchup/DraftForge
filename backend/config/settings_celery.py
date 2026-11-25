"""Minimal Django settings for Celery workers. No ORM, no DB.

Tasks communicate with Django/Daphne over HTTP via internal_client.py.
"""

import os

from dotenv import load_dotenv

from config.discord_api import DISCORD_API_BASE_URL  # noqa: F401
from config.dota_lobby import DotaLobbyConfig
from config.installed_apps import MODEL_APPS
from config.redis_host import resolve_redis_host
from config.signup_post import SignupPostConfig

load_dotenv()

SECRET_KEY = "celery-worker-not-serving-http"
DEBUG = False
ALLOWED_HOSTS = []


def _env_bool(key: str, default: bool = False) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# Test-mode flag for Discord DM safety in tasks.
# When TEST=true, discordbot.dm.send_dm only sends DMs to TEST_DISCORD_USER_ID
# and records everyone else as skipped_test_mode in the ledger (callers count
# it as delivered, so recipient_count > 0 in tests without spamming real users).
DISCORD_ACTIVITY_ENABLED = _env_bool("DISCORD_ACTIVITY_ENABLED")
TEST = _env_bool("TEST")
RELEASE = _env_bool("RELEASE")
TEST_DISCORD_USER_ID = os.environ.get("TEST_DISCORD_USER_ID", "243497113906970625")

# Minimal installed apps for task autodiscovery.
# django.contrib.* required because app.models imports AbstractUser.
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "config",
    *MODEL_APPS,
]

# No database — all tasks use internal HTTP API
DATABASES = {}

# Celery configuration
# Same values as backend.settings: Redis host (config/redis_host.py), raw
# Redis key scope and the signup-post debounce and lock (config/signup_post.py).
REDIS_HOST = resolve_redis_host()
REDIS_KEY_SCOPE = os.environ.get("REDIS_KEY_SCOPE", "")
SIGNUP_POST = SignupPostConfig.from_env()
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", f"redis://{REDIS_HOST}:6379/1")
CELERY_RESULT_BACKEND = os.environ.get(
    "CELERY_RESULT_BACKEND", f"redis://{REDIS_HOST}:6379/1"
)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True

INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "")

# dota_lobby integration: the same values as backend.settings (see
# config/dota_lobby.py). Workers call dota_lobby; the webhook secret is only
# used by the backend but is kept here so both settings modules match.
_dota_lobby = DotaLobbyConfig.from_env()
DOTA_LOBBY_ENABLED = _dota_lobby.enabled
DOTA_LOBBY_URL = _dota_lobby.url
DOTA_LOBBY_API_KEY = _dota_lobby.api_key
DOTA_LOBBY_WEBHOOK_SECRETS = _dota_lobby.webhook_secrets
DOTA_LOBBY_TIMEOUT_SECONDS = _dota_lobby.timeout_seconds
DOTA_LOBBY_REF_PREFIX = _dota_lobby.ref_prefix
DOTA_LOBBY_WEBHOOK_TOLERANCE_SECONDS = _dota_lobby.webhook_tolerance_seconds
DOTA_LOBBY_REGION = _dota_lobby.region

# Discord bot token — required by discordbot.dm.send_dm and the discordbot.utils
# REST helpers.
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

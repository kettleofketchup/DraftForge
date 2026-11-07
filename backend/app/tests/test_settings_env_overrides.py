"""Reload backend.settings under controlled env vars and check the overrides.

Assertions read the reloaded module's attributes, never django.conf.settings
(which is configured once and does not reload).
"""

import importlib
import os
import sys
import types
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

import backend.settings

OVERRIDE_KEYS = (
    "DJANGO_SECRET_KEY",
    "SQLITE_PATH",
    "REDIS_HOST",
    "EXTRA_ALLOWED_HOSTS",
    "EXTRA_CSRF_TRUSTED_ORIGINS",
    "TRUST_X_FORWARDED_PROTO",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
)

DEFAULT_SECRET_KEY = "v*kswpdyi3+*-=q4a)7&_!xwb%@udm1vi56r690!!j6e*p3^mn"

DEFAULT_ALLOWED_HOSTS = [
    "dota.kettle.sh",
    "www.dota.kettle.sh",
    "localhost",
    "nginx",
    "backend",
]

DEFAULT_CSRF_TRUSTED_ORIGINS = [
    "https://localhost",
    "https://nginx",
    "https://dota.kettle.sh",
    "http://dota.kettle.sh",
    "https://dota.kettle.sh",
    "http://dota.kettle.sh",
    "https://dtx.kettle.sh",
    "http://dtx.kettle.sh",
    "https://kettle.sh",
    "http://kettle.sh",
]


def _reload(env=None, remove=()):
    """Reload backend.settings with the override keys cleared, then `env` applied.

    load_dotenv is stubbed so a developer's backend/.env cannot re-inject
    REDIS_HOST or CELERY_* during the reload.
    """
    with (
        mock.patch.dict(os.environ),
        mock.patch("dotenv.load_dotenv", lambda *a, **k: False),
    ):
        for key in (*OVERRIDE_KEYS, *remove):
            os.environ.pop(key, None)
        os.environ.update(env or {})
        backend.settings.is_docker.cache_clear()
        return importlib.reload(backend.settings)


def _expected_db_name():
    match os.environ.get("NODE_ENV", "").lower():
        case "dev":
            return "dev.db.sqlite3"
        case "test":
            return "test.db.sqlite3"
    return "prod.db.sqlite3"


def tearDownModule():
    _reload()


class SettingsEnvOverrideTests(SimpleTestCase):
    def test_defaults_unchanged(self):
        mod = _reload()
        self.assertEqual(mod.SECRET_KEY, DEFAULT_SECRET_KEY)
        self.assertEqual(mod.REDIS_HOST, "redis" if mod.IN_DOCKER else "localhost")
        self.assertEqual(mod.CACHEOPS_REDIS["host"], mod.REDIS_HOST)
        self.assertEqual(mod.CELERY_BROKER_URL, f"redis://{mod.REDIS_HOST}:6379/1")
        self.assertEqual(mod.CELERY_RESULT_BACKEND, f"redis://{mod.REDIS_HOST}:6379/1")
        expected_hosts = list(DEFAULT_ALLOWED_HOSTS)
        if mod.TEST or mod.DEBUG:
            expected_hosts += [".ngrok-free.dev", ".ngrok.io"]
        self.assertEqual(mod.ALLOWED_HOSTS, expected_hosts)
        self.assertEqual(mod.CSRF_TRUSTED_ORIGINS, DEFAULT_CSRF_TRUSTED_ORIGINS)
        self.assertFalse(hasattr(mod, "SECURE_PROXY_SSL_HEADER"))
        self.assertEqual(
            mod.DATABASES["default"]["NAME"],
            mod.BASE_DIR_PATH / _expected_db_name(),
        )

    def test_overrides_take_effect(self):
        mod = _reload(
            {
                "DJANGO_SECRET_KEY": "k1",
                "SQLITE_PATH": "/data/db.sqlite3",
                "REDIS_HOST": "redis",
                "EXTRA_ALLOWED_HOSTS": "draftforge-pr-1.home.kettle.sh",
                "EXTRA_CSRF_TRUSTED_ORIGINS": "https://draftforge-pr-1.home.kettle.sh",
                "TRUST_X_FORWARDED_PROTO": "true",
            }
        )
        self.assertEqual(mod.SECRET_KEY, "k1")
        self.assertEqual(mod.DATABASES["default"]["NAME"], Path("/data/db.sqlite3"))
        self.assertEqual(mod.REDIS_HOST, "redis")
        self.assertEqual(mod.CACHEOPS_REDIS["host"], "redis")
        self.assertEqual(mod.CELERY_BROKER_URL, "redis://redis:6379/1")
        self.assertEqual(mod.CELERY_RESULT_BACKEND, "redis://redis:6379/1")
        self.assertEqual(mod.ALLOWED_HOSTS[-1], "draftforge-pr-1.home.kettle.sh")
        self.assertEqual(
            mod.CSRF_TRUSTED_ORIGINS,
            [*DEFAULT_CSRF_TRUSTED_ORIGINS, "https://draftforge-pr-1.home.kettle.sh"],
        )
        self.assertEqual(
            mod.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https")
        )

    def test_local_settings_still_wins(self):
        fake = types.ModuleType("backend.local_settings")
        fake.ALLOWED_HOSTS = ["local-only"]
        sys.modules["backend.local_settings"] = fake
        try:
            mod = _reload({"EXTRA_ALLOWED_HOSTS": "x.example"})
            self.assertEqual(mod.ALLOWED_HOSTS, ["local-only"])
        finally:
            sys.modules.pop("backend.local_settings", None)

    def test_empty_secret_key_env_falls_back(self):
        mod = _reload({"DJANGO_SECRET_KEY": ""})
        self.assertEqual(mod.SECRET_KEY, DEFAULT_SECRET_KEY)

    def test_redis_host_reaches_caches_and_channels(self):
        mod = _reload({"REDIS_HOST": "redis"}, remove=("DISABLE_CACHE",))
        # Exact match: "redis" is a substring of every redis:// URL.
        self.assertEqual(mod.CACHES["default"]["LOCATION"], "redis://redis:6379/1")
        self.assertEqual(
            mod.CHANNEL_LAYERS["default"]["CONFIG"]["hosts"], [("redis", 6379)]
        )

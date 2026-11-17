"""The celery worker and beat boot config.celery_light under config.settings_celery."""

import json
import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[2]


class CelerySettingsBootTest(SimpleTestCase):
    def test_celery_light_imports_under_settings_celery(self) -> None:
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings_celery"}
        result = subprocess.run(
            [sys.executable, "-c", "import config.celery_light"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])

    def test_worker_registers_discord_name_sync_tasks(self) -> None:
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings_celery"}
        code = (
            "import app.tasks.discord_name_sync, discordbot.services.member_names\n"
            "from config.celery_light import app\n"
            "app.loader.import_default_modules()\n"
            "names = [n for n in app.tasks if n.startswith('app.tasks.discord_name_sync.')]\n"
            "print(','.join(sorted(names)))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        names = result.stdout.strip().splitlines()[-1].split(",")
        self.assertIn(
            "app.tasks.discord_name_sync.sync_active_org_discord_names", names
        )
        self.assertIn("app.tasks.discord_name_sync.sync_org_discord_names", names)

    def test_settings_modules_agree_on_discord_api(self) -> None:
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings_celery"}
        code = (
            "import json, config.settings_celery as c; "
            "print(json.dumps([c.DISCORD_API_BASE_URL, hasattr(c, 'DISCORD_GUILD_ID')]))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        base_url, has_guild_id = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(base_url, settings.DISCORD_API_BASE_URL)
        self.assertFalse(has_guild_id)
        self.assertEqual(settings.DISCORD_API_BASE_URL, "https://discord.com/api/v10")


class SharedSettingsParityTest(SimpleTestCase):
    """Web and worker must agree on the signup-post lock config and key scope."""

    ENV: dict[str, str] = {
        "REDIS_KEY_SCOPE": "df-s3:",
        "SIGNUP_POST_DEBOUNCE_SECONDS": "4",
        "SIGNUP_POST_LOCK_SECONDS": "60",
        "DISABLE_CACHE": "false",
    }

    def _read(self, module: str) -> list[str]:
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("SIGNUP_POST_DISABLED", "RUNNING_TESTS")
        }
        env.update(self.ENV, DJANGO_SETTINGS_MODULE=module)
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from django.conf import settings as s; "
                "print(repr(s.SIGNUP_POST)); print(repr(s.REDIS_KEY_SCOPE))",
            ],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        return result.stdout.strip().splitlines()[-2:]

    def test_signup_post_and_scope_parity(self) -> None:
        web = self._read("backend.settings")
        worker = self._read("config.settings_celery")
        self.assertEqual(web, worker)
        self.assertEqual(
            web,
            [
                "SignupPostConfig(debounce_seconds=4, lock_seconds=60, disabled=False)",
                "'df-s3:'",
            ],
        )

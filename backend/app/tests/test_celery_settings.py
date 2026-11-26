"""The celery worker and beat boot config.celery_light under config.settings_celery."""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from config.redis_host import resolve_redis_host

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Entries intentionally scheduled by only one of the two beat schedules.
LIGHT_ONLY_BEAT_ENTRIES: frozenset[str] = frozenset()
FULL_ONLY_BEAT_ENTRIES: frozenset[str] = frozenset()


def beat_task_names(filename: str) -> dict[str, str]:
    """Every beat entry name -> task path in config/<filename>, parsed not imported."""
    tree = ast.parse((BACKEND_DIR / "config" / filename).read_text())
    entries: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and isinstance(value, ast.Dict)):
                continue
            for k, v in zip(value.keys, value.values):
                if (
                    isinstance(k, ast.Constant)
                    and k.value == "task"
                    and isinstance(v, ast.Constant)
                ):
                    entries[key.value] = v.value
    return entries


class BeatScheduleParityTest(SimpleTestCase):
    """Prod beat runs config.celery_light; its schedule must match config.celery."""

    def test_schedules_list_the_same_entries(self) -> None:
        full = beat_task_names("celery.py")
        light = beat_task_names("celery_light.py")
        self.assertIn("sweep-stale-discord-leases", full)
        shared = full.keys() & light.keys()
        self.assertEqual({k: full[k] for k in shared}, {k: light[k] for k in shared})
        self.assertEqual(full.keys() - light.keys(), FULL_ONLY_BEAT_ENTRIES)
        self.assertEqual(light.keys() - full.keys(), LIGHT_ONLY_BEAT_ENTRIES)


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
            "import user.tasks.discord_name_sync, discordbot.services.member_names\n"
            "from config.celery_light import app\n"
            "app.loader.import_default_modules()\n"
            "names = [n for n in app.tasks if n.startswith('user.tasks.discord_name_sync.')]\n"
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
            "user.tasks.discord_name_sync.sync_active_org_discord_names", names
        )
        self.assertIn("user.tasks.discord_name_sync.sync_org_discord_names", names)

    def test_user_tasks_registered(self) -> None:
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings_celery"}
        code = (
            "import json\n"
            "from config.celery_light import app\n"
            "app.loader.import_default_modules()\n"
            "print(json.dumps(sorted(app.tasks)))"
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
        registered = set(json.loads(result.stdout.strip().splitlines()[-1]))
        expected = {
            "user.tasks.avatar_refresh.refresh_discord_avatars",
            "user.tasks.avatar_refresh.refresh_single_user_avatar",
            "user.tasks.avatar_refresh.refresh_avatars_batched",
            "user.tasks.avatar_refresh.refresh_all_discord_data",
            "user.tasks.discord_name_sync.sync_active_org_discord_names",
            "user.tasks.discord_name_sync.sync_org_discord_names",
        }
        self.assertEqual(expected - registered, set())
        retired_prefixes = tuple(
            task.rsplit(".", 1)[0].replace("user.", "app.", 1) for task in expected
        )
        self.assertFalse(any(name.startswith(retired_prefixes) for name in registered))

    def test_worker_registers_every_light_beat_task(self) -> None:
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings_celery"}
        code = (
            "import json\n"
            "from config.celery_light import app\n"
            "app.loader.import_default_modules()\n"
            "print(json.dumps(sorted(app.tasks)))"
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
        registered = set(json.loads(result.stdout.strip().splitlines()[-1]))
        scheduled = set(beat_task_names("celery_light.py").values())
        self.assertIn("discordbot.tasks.sweep_stale_discord_leases", registered)
        self.assertEqual(scheduled - registered, set())

    def test_worker_boot_modules(self) -> None:
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings_celery"}
        code = (
            "import json, sys\n"
            "from config.celery_light import app\n"
            "app.loader.import_default_modules()\n"
            "names = ['user.models', 'bracket.models', 'events.tournament_tasks',"
            " 'tournament.signals', 'social_django.models', 'user.discord_accounts',"
            " 'user.pipelines', 'joke.models']\n"
            "print(json.dumps({n: n in sys.modules for n in names}))"
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
        loaded = json.loads(result.stdout.strip().splitlines()[-1])
        # Auth-pipeline False pins track worker footprint, not crash guards.
        self.assertEqual(
            loaded,
            {
                "user.models": True,
                "bracket.models": False,
                "events.tournament_tasks": True,
                "tournament.signals": True,
                "social_django.models": False,
                "user.discord_accounts": False,
                "user.pipelines": False,
                "joke.models": False,
            },
        )

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
        "SIGNUP_POST_READ_RETRIES": "5",
        "SIGNUP_POST_RETRY_SECONDS": "3",
        "SIGNUP_POST_BUSY_WARN_PASSES": "4",
        "DISABLE_CACHE": "false",
    }

    def _read(
        self, module: str, redis_host: str | None = "redis.internal"
    ) -> list[str]:
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("RUNNING_TESTS", "DF_RUNNING_TESTS", "REDIS_HOST")
            and not k.startswith("SIGNUP_POST_")
        }
        env.update(self.ENV, DJANGO_SETTINGS_MODULE=module)
        if redis_host is not None:
            env["REDIS_HOST"] = redis_host
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from django.conf import settings as s; "
                "print(repr(s.SIGNUP_POST)); print(repr(s.REDIS_KEY_SCOPE)); "
                "print(repr(s.REDIS_HOST))",
            ],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        return result.stdout.strip().splitlines()[-3:]

    def test_signup_post_and_scope_parity(self) -> None:
        web = self._read("backend.settings")
        worker = self._read("config.settings_celery")
        self.assertEqual(web, worker)
        self.assertEqual(
            web,
            [
                "SignupPostConfig(debounce_seconds=4, lock_seconds=60, disabled=False,"
                " read_retries=5, retry_seconds=3, busy_warn_passes=4)",
                "'df-s3:'",
                "'redis.internal'",
            ],
        )

    def test_redis_host_fallback_parity(self) -> None:
        for redis_host in (None, ""):
            with self.subTest(redis_host=redis_host):
                web = self._read("backend.settings", redis_host)
                worker = self._read("config.settings_celery", redis_host)
                self.assertEqual(web[-1], worker[-1])
                self.assertNotEqual(web[-1], "''")


class ResolveRedisHostTest(SimpleTestCase):
    def test_explicit_host_wins(self) -> None:
        env = {"REDIS_HOST": "redis.internal"}
        self.assertEqual(resolve_redis_host(env, in_docker=False), "redis.internal")
        self.assertEqual(resolve_redis_host(env, in_docker=True), "redis.internal")

    def test_unset_or_empty_falls_back_by_runtime(self) -> None:
        for env in ({}, {"REDIS_HOST": ""}, {"REDIS_HOST": "  "}):
            with self.subTest(env=env):
                self.assertEqual(resolve_redis_host(env, in_docker=True), "redis")
                self.assertEqual(resolve_redis_host(env, in_docker=False), "localhost")

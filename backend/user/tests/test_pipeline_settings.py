from types import SimpleNamespace
from typing import Any

from django.conf import settings
from django.test import TestCase
from django.utils.module_loading import import_string
from social_django.models import DjangoStorage
from social_django.strategy import DjangoStrategy

from app.models import CustomUser


class PipelineSettingsTest(TestCase):
    def test_pipeline_paths_import(self) -> None:
        steps = [import_string(path) for path in settings.SOCIAL_AUTH_PIPELINE]
        for name in (
            "associate_by_discord_id",
            "associate_by_discord_username",
            "save_discord",
        ):
            with self.subTest(step=name):
                step = next(step for step in steps if step.__name__ == name)
                self.assertEqual(step.__module__, "user.pipelines")

    def test_user_steps_run_in_settings_order(self) -> None:
        strategy = DjangoStrategy(storage=DjangoStorage())
        backend = SimpleNamespace(
            name="discord",
            strategy=strategy,
            extra_data=lambda user, uid, response, details, kwargs: response,
        )
        paths = list(settings.SOCIAL_AUTH_PIPELINE)
        start = next(
            i
            for i, path in enumerate(paths)
            if path.endswith(".associate_by_discord_id")
        )
        end = next(i for i, path in enumerate(paths) if path.endswith(".save_discord"))
        for match_by in ("uid", "username"):
            with self.subTest(match_by=match_by):
                uid = (
                    "555000111222333444" if match_by == "uid" else "555000111222333445"
                )
                username = f"pipeline_{match_by}"
                user = CustomUser.objects.create(
                    username="old_handle" if match_by == "uid" else username,
                    discordId=uid if match_by == "uid" else None,
                )
                response = {
                    "id": uid,
                    "username": username,
                    "avatar": "avatar_hash",
                    "global_name": "Discord Display",
                }
                context: dict[str, Any] = {
                    "strategy": strategy,
                    "backend": backend,
                    "uid": uid,
                    "response": response,
                    "details": {"username": username},
                    "user": None,
                    "social": None,
                }
                for path in paths[start : end + 1]:
                    result = import_string(path)(**context)
                    if result is not None:
                        self.assertIsInstance(result, dict)
                        context.update(result)
                self.assertEqual(context["user"].pk, user.pk)
                user.refresh_from_db()
                self.assertEqual(user.discordId, uid)
                self.assertEqual(user.discordUsername, username)
                self.assertEqual(user.discordNickname, "Discord Display")
                self.assertEqual(user.avatar, "avatar_hash")
                self.assertTrue(user.positions_id)
                self.assertEqual(user.social_auth.get(provider="discord").uid, uid)

import unittest

from django.core.exceptions import FieldDoesNotExist
from django.db import connection
from django.test import TestCase

from app.models import CustomUser
from user.models import BaseUserProfile

try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error


def _columns(table: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(f'PRAGMA table_info("{table}")')
        return {row[1] for row in cursor.fetchall()}


def _indexes(table: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(f'PRAGMA index_list("{table}")')
        return {row[1] for row in cursor.fetchall()}


class ModelStateTest(TestCase):
    def test_guild_nickname_not_in_model_state(self) -> None:
        with self.assertRaises(FieldDoesNotExist):
            CustomUser._meta.get_field("guildNickname")

    def test_site_nickname_not_in_model_state(self) -> None:
        with self.assertRaises(FieldDoesNotExist):
            BaseUserProfile._meta.get_field("nickname")

    def test_customuser_has_no_nickname_attribute(self) -> None:
        self.assertFalse(hasattr(CustomUser, "nickname"))

    def test_guild_nickname_index_not_in_model_state(self) -> None:
        names = {index.name for index in CustomUser._meta.indexes}
        self.assertNotIn("app_customu_guildNi_602cf5_idx", names)

    def test_columns_and_index_still_exist(self) -> None:
        self.assertIn("guildNickname", _columns("app_customuser"))
        self.assertIn("app_customu_guildNi_602cf5_idx", _indexes("app_customuser"))
        self.assertIn("nickname", _columns("user_baseuserprofile"))

    def test_inserts_leave_retired_columns_null(self) -> None:
        user = CustomUser.objects.create(username="state_only_insert")
        self.assertTrue(BaseUserProfile.objects.filter(user=user).exists())
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT "guildNickname" FROM app_customuser WHERE id = %s', [user.pk]
            )
            self.assertIsNone(cursor.fetchone()[0])
            cursor.execute(
                "SELECT nickname FROM user_baseuserprofile WHERE user_id = %s",
                [user.pk],
            )
            self.assertIsNone(cursor.fetchone()[0])


class StateOnlyMigrationKeepsDataTest(MigratorTestCase):
    migrate_from = [
        ("app", "0106_draftoptions_hero_grace_time_ms_and_more"),
        ("user", "0004_backfill_game_profiles"),
    ]
    migrate_to = [
        ("app", "0107_state_remove_customuser_guildnickname"),
        ("user", "0005_state_remove_baseuserprofile_nickname"),
    ]

    def prepare(self) -> None:
        CustomUser = self.old_state.apps.get_model("app", "CustomUser")
        BaseUserProfile = self.old_state.apps.get_model("user", "BaseUserProfile")
        user = CustomUser.objects.create(
            username="state_only_mig", guildNickname="DragonClaw"
        )
        BaseUserProfile.objects.create(user=user, nickname="Site")
        self.user_pk = user.pk

    def test_raw_values_survive(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT "guildNickname" FROM app_customuser WHERE id = %s',
                [self.user_pk],
            )
            self.assertEqual(cursor.fetchone()[0], "DragonClaw")
            cursor.execute(
                "SELECT nickname FROM user_baseuserprofile WHERE user_id = %s",
                [self.user_pk],
            )
            self.assertEqual(cursor.fetchone()[0], "Site")

    def test_new_state_has_no_fields(self) -> None:
        NewUser = self.new_state.apps.get_model("app", "CustomUser")
        NewProfile = self.new_state.apps.get_model("user", "BaseUserProfile")
        with self.assertRaises(FieldDoesNotExist):
            NewUser._meta.get_field("guildNickname")
        with self.assertRaises(FieldDoesNotExist):
            NewProfile._meta.get_field("nickname")

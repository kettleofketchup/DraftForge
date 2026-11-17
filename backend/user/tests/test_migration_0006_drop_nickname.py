import unittest

from django.db import connection

try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error


STATE_ONLY = ("user", "0005_state_remove_baseuserprofile_nickname")
DROP = ("user", "0006_drop_baseuserprofile_nickname_column")


def _columns() -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA table_info("user_baseuserprofile")')
        return {row[1] for row in cursor.fetchall()}


class DropSiteNicknameColumnTest(MigratorTestCase):
    migrate_from = STATE_ONLY
    migrate_to = DROP

    def prepare(self) -> None:
        CustomUser = self.old_state.apps.get_model("app", "CustomUser")
        BaseUserProfile = self.old_state.apps.get_model("user", "BaseUserProfile")
        user = CustomUser.objects.create(username="drop_sitenick_0006")
        BaseUserProfile.objects.get_or_create(user=user)
        self.user_pk = user.pk

    def test_column_dropped(self) -> None:
        self.assertNotIn("nickname", _columns())

    def test_rows_survive(self) -> None:
        BaseUserProfile = self.new_state.apps.get_model("user", "BaseUserProfile")
        self.assertTrue(BaseUserProfile.objects.filter(user_id=self.user_pk).exists())


class ReverseDropSiteNicknameColumnTest(MigratorTestCase):
    migrate_from = DROP
    migrate_to = STATE_ONLY

    def prepare(self) -> None:
        CustomUser = self.old_state.apps.get_model("app", "CustomUser")
        BaseUserProfile = self.old_state.apps.get_model("user", "BaseUserProfile")
        user = CustomUser.objects.create(username="restore_sitenick_0006")
        BaseUserProfile.objects.get_or_create(user=user)
        self.user_pk = user.pk

    def test_column_restored(self) -> None:
        self.assertIn("nickname", _columns())

    def test_restored_column_is_null(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM user_baseuserprofile WHERE nickname IS NOT NULL"
            )
            self.assertEqual(cursor.fetchone()[0], 0)
            cursor.execute(
                "SELECT nickname FROM user_baseuserprofile WHERE user_id = %s",
                [self.user_pk],
            )
            self.assertIsNone(cursor.fetchone()[0])

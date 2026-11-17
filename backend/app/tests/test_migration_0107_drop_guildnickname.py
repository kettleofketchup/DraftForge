import unittest

from django.db import connection

try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error


STATE_ONLY = ("app", "0106_state_remove_customuser_guildnickname")
DROP = ("app", "0107_drop_customuser_guildnickname_column")
INDEX = "app_customu_guildNi_602cf5_idx"


def _columns() -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA table_info("app_customuser")')
        return {row[1] for row in cursor.fetchall()}


def _indexes() -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA index_list("app_customuser")')
        return {row[1] for row in cursor.fetchall()}


class DropGuildNicknameColumnTest(MigratorTestCase):
    migrate_from = STATE_ONLY
    migrate_to = DROP

    def prepare(self) -> None:
        CustomUser = self.old_state.apps.get_model("app", "CustomUser")
        self.user_pk = CustomUser.objects.create(username="drop_guildnick_0107").pk

    def test_column_dropped(self) -> None:
        self.assertNotIn("guildNickname", _columns())

    def test_index_dropped(self) -> None:
        self.assertNotIn(INDEX, _indexes())

    def test_rows_survive(self) -> None:
        CustomUser = self.new_state.apps.get_model("app", "CustomUser")
        self.assertTrue(CustomUser.objects.filter(pk=self.user_pk).exists())


class ReverseDropGuildNicknameColumnTest(MigratorTestCase):
    migrate_from = DROP
    migrate_to = STATE_ONLY

    def prepare(self) -> None:
        CustomUser = self.old_state.apps.get_model("app", "CustomUser")
        self.user_pk = CustomUser.objects.create(username="restore_guildnick_0107").pk

    def test_column_and_index_restored(self) -> None:
        self.assertIn("guildNickname", _columns())
        self.assertIn(INDEX, _indexes())

    def test_restored_column_is_null(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT COUNT(*) FROM app_customuser WHERE "guildNickname" IS NOT NULL'
            )
            self.assertEqual(cursor.fetchone()[0], 0)
            cursor.execute(
                'SELECT "guildNickname" FROM app_customuser WHERE id = %s',
                [self.user_pk],
            )
            self.assertIsNone(cursor.fetchone()[0])

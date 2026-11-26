import re

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.db.models import Model
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from structlog.testing import capture_logs

from app.models import CustomUser

BEFORE_MOVE: list[tuple[str, str | None]] = [
    ("app", "0117_move_user_models_to_user"),
    ("joke", None),
]
MOVE_MIGRATIONS: list[tuple[str, str]] = [
    ("app", "0118_move_joke_to_joke"),
    ("joke", "0001_move_joke_from_app"),
]
# project_state() takes no (app, None) nodes.
BEFORE_MOVE_STATE: list[tuple[str, str]] = [("app", "0117_move_user_models_to_user")]
MOVED_TABLES = ("app_joke",)
MIGRATED_APPS: tuple[str, ...] = ("app", "joke")
APP = "app"
JOKE = "joke"
# A SQLite table rebuild keeps sqlite_master's sql text but moves rootpage
# and runs CREATE/INSERT INTO "new__..."/DROP/ALTER statements.
DDL_STATEMENT = re.compile(r"^\s*(CREATE|ALTER|DROP)\b|\bnew__", re.IGNORECASE)


def _schema_rows() -> list[tuple[str, str, str, int, str | None]]:
    with connection.cursor() as cursor:
        placeholders = ",".join("%s" for _ in MOVED_TABLES)
        cursor.execute(
            "SELECT type, name, tbl_name, rootpage, sql FROM sqlite_master "
            f"WHERE tbl_name IN ({placeholders}) ORDER BY tbl_name, type, name",
            list(MOVED_TABLES),
        )
        return cursor.fetchall()


class JokeMoveMigrationTest(TransactionTestCase):
    def tearDown(self) -> None:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        ContentType.objects.clear_cache()
        super().tearDown()

    def _back(self) -> None:
        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE_MOVE)
        ContentType.objects.clear_cache()

    def _forward(self) -> None:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(MOVE_MIGRATIONS)
        ContentType.objects.clear_cache()

    def _applied(self) -> set[tuple[str, str]]:
        return set(MigrationLoader(connection).applied_migrations)

    def _historical_joke(self, app_label: str) -> type[Model]:
        state = MOVE_MIGRATIONS if app_label == JOKE else BEFORE_MOVE_STATE
        apps = MigrationExecutor(connection).loader.project_state(state).apps
        return apps.get_model(app_label, "Joke")

    def _label(self, pk: int) -> tuple[str, str]:
        return tuple(
            ContentType.objects.filter(pk=pk).values_list("app_label", "model")[0]
        )

    def test_rows_survive_forward_and_reverse(self) -> None:
        user = CustomUser.objects.create_user(username="joke_move_rows")

        self._back()
        self.assertFalse(self._applied() & set(MOVE_MIGRATIONS))
        old_joke = self._historical_joke(APP)
        row = old_joke.objects.create(user_id=user.pk, tangoes_purchased=5)

        self._forward()
        self.assertTrue(set(MOVE_MIGRATIONS) <= self._applied())
        new_joke = self._historical_joke(JOKE)
        self.assertEqual(
            list(new_joke.objects.values_list("pk", "user_id", "tangoes_purchased")),
            [(row.pk, user.pk, 5)],
        )

        self._back()
        old_joke = self._historical_joke(APP)
        self.assertEqual(
            list(old_joke.objects.values_list("pk", "user_id", "tangoes_purchased")),
            [(row.pk, user.pk, 5)],
        )

    def test_permission_grant_follows_relabel(self) -> None:
        content_type, _ = ContentType.objects.get_or_create(
            app_label=JOKE, model="joke"
        )
        perm, _ = Permission.objects.get_or_create(
            codename="change_joke",
            content_type=content_type,
            defaults={"name": "Can change Joke"},
        )
        group = Group.objects.create(name="joke_move_perm_group")
        group.permissions.add(perm)

        self._back()
        self.assertEqual(self._label(content_type.pk), (APP, "joke"))
        self.assertTrue(
            group.permissions.filter(
                pk=perm.pk, content_type__app_label=APP, codename="change_joke"
            ).exists()
        )

        self._forward()
        self.assertEqual(self._label(content_type.pk), (JOKE, "joke"))
        self.assertTrue(
            group.permissions.filter(
                pk=perm.pk, content_type__app_label=JOKE, codename="change_joke"
            ).exists()
        )

        self._back()
        self.assertEqual(self._label(content_type.pk), (APP, "joke"))
        self.assertFalse(
            ContentType.objects.filter(app_label=JOKE, model="joke").exists()
        )

    def test_duplicate_contenttype_skipped_and_logged(self) -> None:
        original = ContentType.objects.get_or_create(app_label=JOKE, model="joke")[0]

        self._back()
        self.assertEqual(self._label(original.pk), (APP, "joke"))
        duplicate = ContentType.objects.create(app_label=JOKE, model="joke")

        with capture_logs() as logs:
            self._forward()
        self.assertTrue(set(MOVE_MIGRATIONS) <= self._applied())
        self.assertEqual(self._label(original.pk), (APP, "joke"))
        self.assertEqual(self._label(duplicate.pk), (JOKE, "joke"))
        skipped = [
            (entry["model"], entry["direction"], entry["system"], entry["subsystem"])
            for entry in logs
            if entry["event"] == "contenttype_relabel_skipped"
        ]
        self.assertEqual(skipped, [("joke", "app->joke", "migrations", "contenttypes")])

    def test_no_ddl(self) -> None:
        user = CustomUser.objects.create_user(username="joke_move_ddl")
        self._historical_joke(JOKE).objects.create(user_id=user.pk)
        schema_before = _schema_rows()
        self.assertEqual({row[2] for row in schema_before}, set(MOVED_TABLES))

        for _ in range(2):
            with CaptureQueriesContext(connection) as back_queries:
                self._back()
            self.assertEqual(_schema_rows(), schema_before)
            with CaptureQueriesContext(connection) as forward_queries:
                self._forward()
            self.assertEqual(_schema_rows(), schema_before)
            ddl = [
                query["sql"]
                for query in back_queries.captured_queries
                + forward_queries.captured_queries
                if DDL_STATEMENT.search(query["sql"])
            ]
            self.assertEqual(ddl, [])

    def test_one_leaf_per_app(self) -> None:
        leaves = MigrationLoader(None, ignore_no_migrations=True).graph.leaf_nodes()
        for app_label in MIGRATED_APPS:
            self.assertEqual(
                len([node for node in leaves if node[0] == app_label]),
                1,
                app_label,
            )

    def test_move_adds_no_extra_ancestors(self) -> None:
        graph = MigrationLoader(None, ignore_no_migrations=True).graph
        added = (
            set(graph.forwards_plan(("app", "0118_move_joke_to_joke")))
            - set(graph.forwards_plan(("app", "0117_move_user_models_to_user")))
            - set(
                graph.forwards_plan(("contenttypes", "0002_remove_content_type_name"))
            )
        )
        self.assertEqual(added, set(MOVE_MIGRATIONS))

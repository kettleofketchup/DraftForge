import re

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from structlog.testing import capture_logs

from app.models import CustomUser
from org.models import Organization
from user.models import DotaUserProfile, PositionsModel, ProfileClaimRequest

USER_MODELS = ("positionsmodel", "profileclaimrequest")
MOVED_TABLES = ("app_positionsmodel", "app_profileclaimrequest")
REFERRING_TABLES = ("user_dotauserprofile",)
BEFORE_MOVE: list[tuple[str, str]] = [
    ("app", "0115_move_tournament_models_to_tournament"),
    ("user", "0004_backfill_game_profiles"),
]
MOVE_MIGRATIONS: list[tuple[str, str]] = [
    ("app", "0116_move_user_models_to_user"),
    ("user", "0005_move_user_models_from_app"),
]
APP = "app"
USER = "user"
# A SQLite table rebuild keeps sqlite_master's sql text but moves rootpage
# and runs CREATE/INSERT INTO "new__..."/DROP/ALTER statements.
DDL_STATEMENT = re.compile(r"^\s*(CREATE|ALTER|DROP)\b|\bnew__", re.IGNORECASE)


def _schema_rows() -> list[tuple[str, str, str, int, str | None]]:
    tables = MOVED_TABLES + REFERRING_TABLES
    with connection.cursor() as cursor:
        placeholders = ",".join("%s" for _ in tables)
        cursor.execute(
            "SELECT type, name, tbl_name, rootpage, sql FROM sqlite_master "
            f"WHERE tbl_name IN ({placeholders}) ORDER BY tbl_name, type, name",
            list(tables),
        )
        return cursor.fetchall()


def _row_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    with connection.cursor() as cursor:
        for table in MOVED_TABLES:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]
    return counts


class UserMoveMigrationTests(TransactionTestCase):
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

    def _ids(self) -> dict[str, int]:
        return {
            model: ContentType.objects.get_or_create(app_label=USER, model=model)[0].pk
            for model in USER_MODELS
        }

    def _labels(self, ids: dict[str, int]) -> dict[str, tuple[str, str]]:
        return {
            key: tuple(
                ContentType.objects.filter(pk=pk).values_list("app_label", "model")[0]
            )
            for key, pk in ids.items()
        }

    def _grant(self, content_type_id: int, suffix: str) -> tuple[CustomUser, Group]:
        perm, _ = Permission.objects.get_or_create(
            codename="add_positionsmodel",
            content_type_id=content_type_id,
            defaults={"name": "Can add positions model"},
        )
        user = CustomUser.objects.create_user(username=f"user_move_perm_{suffix}")
        group = Group.objects.create(name=f"user_move_perm_group_{suffix}")
        user.user_permissions.add(perm)
        group.permissions.add(perm)
        return user, group

    def _has_perm(self, user: CustomUser, label: str) -> bool:
        return CustomUser.objects.get(pk=user.pk).has_perm(
            f"{label}.add_positionsmodel"
        )

    def _seed(self) -> tuple[DotaUserProfile, ProfileClaimRequest]:
        claimer = CustomUser.objects.create_user(username="user_move_claimer")
        target = CustomUser.objects.create_user(username="user_move_target")
        org = Organization.objects.create(name="User Move Org", owner=claimer)
        profile = DotaUserProfile.objects.get(base_profile__user=claimer)
        positions = PositionsModel.objects.create(carry=5, mid=4, hard_support=1)
        profile.positions = positions
        profile.save(update_fields=["positions"])
        claim = ProfileClaimRequest.objects.create(
            claimer=claimer, target_user=target, organization=org
        )
        return profile, claim

    def test_rows_survive_and_positions_resolve(self) -> None:
        profile, claim = self._seed()
        positions_id = profile.positions_id
        counts = _row_counts()
        self.assertGreaterEqual(counts["app_positionsmodel"], 1)
        self.assertEqual(counts["app_profileclaimrequest"], 1)

        self._back()
        self.assertFalse(self._applied() & set(MOVE_MIGRATIONS))
        self.assertEqual(_row_counts(), counts)
        old_apps = MigrationExecutor(connection).loader.project_state(BEFORE_MOVE).apps
        old_profile = old_apps.get_model(USER, "DotaUserProfile").objects.get(
            pk=profile.pk
        )
        self.assertEqual(old_profile.positions.carry, 5)
        self.assertEqual(old_profile.positions._meta.app_label, APP)
        old_claim = old_apps.get_model(APP, "ProfileClaimRequest").objects.get(
            pk=claim.pk
        )
        self.assertEqual(old_claim.status, "pending")

        self._forward()
        self.assertTrue(set(MOVE_MIGRATIONS) <= self._applied())
        self.assertEqual(_row_counts(), counts)
        profile = DotaUserProfile.objects.get(pk=profile.pk)
        self.assertEqual(profile.positions_id, positions_id)
        self.assertEqual((profile.positions.carry, profile.positions.mid), (5, 4))
        claim = ProfileClaimRequest.objects.get(pk=claim.pk)
        self.assertEqual(claim.status, ProfileClaimRequest.Status.PENDING)
        self.assertEqual(claim.claimer.username, "user_move_claimer")
        self.assertEqual(claim.target_user.username, "user_move_target")
        self.assertEqual(claim.organization.name, "User Move Org")

    def test_contenttypes_relabelled_and_permissions_follow(self) -> None:
        ids = self._ids()
        user, group = self._grant(ids["positionsmodel"], "follow")
        self.assertTrue(self._has_perm(user, USER))

        self._back()
        self.assertTrue(self._has_perm(user, APP))
        self.assertFalse(self._has_perm(user, USER))

        self._forward()
        self.assertEqual(self._labels(ids), {m: (USER, m) for m in USER_MODELS})
        self.assertTrue(self._has_perm(user, USER))
        self.assertFalse(self._has_perm(user, APP))
        perm = Permission.objects.get(
            content_type__app_label=USER, codename="add_positionsmodel"
        )
        self.assertEqual(perm.content_type_id, ids["positionsmodel"])
        self.assertTrue(group.permissions.filter(pk=perm.pk).exists())

    def test_reverse_restores_app_labels(self) -> None:
        ids = self._ids()

        self._back()
        self.assertEqual(self._labels(ids), {m: (APP, m) for m in USER_MODELS})
        self.assertFalse(
            ContentType.objects.filter(app_label=USER, model__in=USER_MODELS).exists()
        )

        self._forward()
        self.assertEqual(self._labels(ids), {m: (USER, m) for m in USER_MODELS})
        self.assertFalse(
            ContentType.objects.filter(app_label=APP, model__in=USER_MODELS).exists()
        )

    def test_duplicate_contenttype_skipped_both_directions(self) -> None:
        original = self._ids()["positionsmodel"]
        user, _ = self._grant(original, "dup")

        self._back()
        self.assertEqual(self._labels({"o": original}), {"o": (APP, "positionsmodel")})
        duplicate = ContentType.objects.create(app_label=USER, model="positionsmodel")
        expected = {"o": (APP, "positionsmodel"), "d": (USER, "positionsmodel")}
        ids = {"o": original, "d": duplicate.pk}

        with capture_logs() as forward_logs:
            self._forward()
        self.assertEqual(self._labels(ids), expected)
        self.assertTrue(self._has_perm(user, APP))

        with capture_logs() as reverse_logs:
            self._back()
        self.assertEqual(self._labels(ids), expected)
        self.assertTrue(self._has_perm(user, APP))

        skipped = [
            (entry["model"], entry["direction"], entry["system"], entry["subsystem"])
            for entry in forward_logs + reverse_logs
            if entry["event"] == "contenttype_relabel_skipped"
        ]
        self.assertEqual(
            skipped,
            [
                ("positionsmodel", "app->user", "migrations", "contenttypes"),
                ("positionsmodel", "user->app", "migrations", "contenttypes"),
            ],
        )

    def test_no_ddl(self) -> None:
        self._seed()
        schema_before = _schema_rows()
        self.assertEqual(
            {row[2] for row in schema_before}, set(MOVED_TABLES + REFERRING_TABLES)
        )
        names = {row[1] for row in schema_before}
        self.assertTrue(
            {
                "app_profile_organiz_4b1a91_idx",
                "app_profile_claimer_2ce297_idx",
                "unique_pending_claim_request",
            }
            <= names
        )

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
        for app_label, name in MOVE_MIGRATIONS:
            self.assertEqual(
                [node for node in leaves if node[0] == app_label],
                [(app_label, name)],
            )

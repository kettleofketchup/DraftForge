from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.test import TransactionTestCase
from django.utils import timezone

from app.models import CustomUser, League
from events.models import Event
from org.models import Organization, OrgLog, OrgUser

ORG_MODELS = ("organization", "orglog")
MOVED_TABLES = (
    "app_organization",
    "app_organization_admins",
    "app_organization_staff",
    "app_organization_promoters",
    "app_orglog",
)
REFERRING_TABLES = (
    "app_league",
    "app_customuser",
    "org_orguser",
    "events_event",
    "opsnotices_opsnotice",
    "org_orgconductsettings",
    "org_attendanceoutcome",
)
BEFORE_MOVE = [
    ("app", "0110_orglog_conduct_actions"),
    ("org", "0013_conduct"),
    ("events", "0034_event_conduct_finalized_at"),
    ("opsnotices", "0002_opsnotice_emit_id_uniq"),
]
MOVE_MIGRATION = ("app", "0111_move_organization_models_to_org")
RETARGETS = (
    ("org", "0013_conduct"),
    ("org", "0014_move_organization_models_from_app"),
    ("events", "0035_retarget_organization_to_org"),
    ("opsnotices", "0003_retarget_organization_to_org"),
)
APP = "app"
ORG = "org"


def _table_sql() -> dict[str, str]:
    tables = MOVED_TABLES + REFERRING_TABLES
    with connection.cursor() as cursor:
        placeholders = ",".join("%s" for _ in tables)
        cursor.execute(
            f"SELECT name, sql FROM sqlite_master WHERE name IN ({placeholders})",
            list(tables),
        )
        return dict(cursor.fetchall())


def _row_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    with connection.cursor() as cursor:
        for table in MOVED_TABLES:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]
    return counts


class OrganizationMoveMigrationTests(TransactionTestCase):
    def tearDown(self) -> None:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        ContentType.objects.clear_cache()
        super().tearDown()

    def _migrate(self, targets: list[tuple[str, str | None]]) -> None:
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        ContentType.objects.clear_cache()

    def _forward(self) -> None:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        ContentType.objects.clear_cache()

    def _labels(self, ids: dict[str, int]) -> dict[str, tuple[str, str]]:
        return {
            key: tuple(
                ContentType.objects.filter(pk=pk).values_list("app_label", "model")[0]
            )
            for key, pk in ids.items()
        }

    def _grant(
        self, content_type_id: int, suffix: str
    ) -> tuple[Permission, CustomUser, Group]:
        perm, _ = Permission.objects.get_or_create(
            codename="change_organization",
            content_type_id=content_type_id,
            defaults={"name": "Can change organization"},
        )
        user = CustomUser.objects.create_user(username=f"org_perm_user_{suffix}")
        group = Group.objects.create(name=f"org_perm_group_{suffix}")
        user.user_permissions.add(perm)
        group.permissions.add(perm)
        return perm, user, group

    def _assert_grant(
        self, perm: Permission, user: CustomUser, group: Group, content_type_id: int
    ) -> None:
        perm.refresh_from_db()
        self.assertEqual(perm.content_type_id, content_type_id)
        self.assertTrue(user.user_permissions.filter(pk=perm.pk).exists())
        self.assertTrue(group.permissions.filter(pk=perm.pk).exists())

    def _seed(self, owner: CustomUser) -> Organization:
        org = Organization.objects.create(name="Org Move Migration", owner=owner)
        admin = CustomUser.objects.create_user(username="org_move_admin")
        staff = CustomUser.objects.create_user(username="org_move_staff")
        promoter = CustomUser.objects.create_user(username="org_move_promoter")
        org.admins.add(admin)
        org.staff.add(staff)
        org.promoters.add(promoter)
        OrgLog.objects.create(
            organization=org, actor=owner, action="add_admin", target_user=admin
        )
        OrgLog.objects.create(
            organization=org,
            actor=owner,
            action="finalize_attendance",
            details={"event_id": 1, "outcomes": 3},
        )
        OrgUser.objects.create(user=admin, organization=org)
        League.objects.create(
            name="Org Move League", organization=org, steam_league_id=99111
        )
        Event.objects.create(
            organization=org,
            name="Org Move Event",
            scheduled_at=timezone.now(),
            created_by=owner,
        )
        return org

    def test_reverse_then_forward_keeps_schema_and_relabels(self) -> None:
        ids = {
            model: ContentType.objects.get_or_create(app_label=ORG, model=model)[0].pk
            for model in ORG_MODELS
        }
        perm, user, group = self._grant(ids["organization"], "move")
        org = self._seed(user)
        counts = _row_counts()
        self.assertEqual(
            counts,
            {
                "app_organization": 1,
                "app_organization_admins": 1,
                "app_organization_staff": 1,
                "app_organization_promoters": 1,
                "app_orglog": 2,
            },
        )
        sql_before = _table_sql()
        self.assertEqual(set(sql_before), set(MOVED_TABLES + REFERRING_TABLES))

        self._migrate(BEFORE_MOVE)

        self.assertEqual(self._labels(ids), {m: (APP, m) for m in ORG_MODELS})
        self._assert_grant(perm, user, group, ids["organization"])
        self.assertEqual(_row_counts(), counts)
        self.assertEqual(_table_sql(), sql_before)

        self._forward()

        self.assertEqual(self._labels(ids), {m: (ORG, m) for m in ORG_MODELS})
        self._assert_grant(perm, user, group, ids["organization"])
        self.assertEqual(_row_counts(), counts)
        self.assertEqual(_table_sql(), sql_before)
        self.assertEqual(
            League.objects.get(steam_league_id=99111).organization_id, org.pk
        )
        self.assertEqual(
            sorted(
                OrgLog.objects.filter(organization=org).values_list("action", "details")
            ),
            [
                ("add_admin", {}),
                ("finalize_attendance", {"event_id": 1, "outcomes": 3}),
            ],
        )

    def test_duplicate_contenttypes_survive_both_directions(self) -> None:
        original, _ = ContentType.objects.get_or_create(
            app_label=ORG, model="organization"
        )
        perm, user, group = self._grant(original.pk, "dup")

        self._migrate(BEFORE_MOVE)
        self.assertEqual(self._labels({"o": original.pk}), {"o": (APP, "organization")})
        duplicate = ContentType.objects.create(app_label=ORG, model="organization")
        expected = {"o": (APP, "organization"), "d": (ORG, "organization")}
        ids = {"o": original.pk, "d": duplicate.pk}

        self._forward()
        self.assertEqual(self._labels(ids), expected)
        self._assert_grant(perm, user, group, original.pk)

        self._migrate(BEFORE_MOVE)
        self.assertEqual(self._labels(ids), expected)
        self._assert_grant(perm, user, group, original.pk)

    def test_retargets_precede_app_0111(self) -> None:
        plan = MigrationLoader(connection).graph.forwards_plan(MOVE_MIGRATION)
        for retarget in RETARGETS:
            self.assertIn(retarget, plan)

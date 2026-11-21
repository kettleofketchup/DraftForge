import unittest

from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.operations import DeleteModel, RemoveField
from django.test import SimpleTestCase

# django-test-migrations is a dev dep; a stale CI image may lack it.
try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error

DOTA2 = 1
DEADLOCK = 2


class ForwardBackfillTest(MigratorTestCase):
    migrate_from = ("org", "0013_conduct")
    migrate_to = ("org", "0016_remove_orguser_mmr")

    def prepare(self) -> None:
        apps = self.old_state.apps
        CustomUser = apps.get_model("app", "CustomUser")
        Organization = apps.get_model("app", "Organization")
        OrgUser = apps.get_model("org", "OrgUser")
        org = Organization.objects.create(name="Backfill Org")
        self.pks: dict[int, int] = {}
        for mmr in (0, 4000, 9999, -5):
            user = CustomUser.objects.create(username=f"backfill_{mmr}")
            self.pks[mmr] = OrgUser.objects.create(
                user=user, organization=org, mmr=mmr
            ).pk

    def test_zero_mmr_creates_no_row(self) -> None:
        Row = self.new_state.apps.get_model("org", "OrgUserGameMmr")
        self.assertFalse(Row.objects.filter(org_user_id=self.pks[0]).exists())

    def test_nonzero_mmr_copied_verbatim_to_dota(self) -> None:
        Row = self.new_state.apps.get_model("org", "OrgUserGameMmr")
        for mmr in (4000, 9999, -5):
            rows = list(
                Row.objects.filter(org_user_id=self.pks[mmr]).values_list(
                    "game_type", "mmr"
                )
            )
            self.assertEqual(rows, [(DOTA2, mmr)])

    def test_no_deadlock_rows(self) -> None:
        Row = self.new_state.apps.get_model("org", "OrgUserGameMmr")
        self.assertEqual(Row.objects.filter(game_type=DEADLOCK).count(), 0)


class BackfillIdempotencyTest(MigratorTestCase):
    migrate_from = ("org", "0014_orgusergamemmr")
    migrate_to = ("org", "0015_backfill_org_user_game_mmr")

    def prepare(self) -> None:
        apps = self.old_state.apps
        CustomUser = apps.get_model("app", "CustomUser")
        Organization = apps.get_model("app", "Organization")
        OrgUser = apps.get_model("org", "OrgUser")
        Row = apps.get_model("org", "OrgUserGameMmr")
        org = Organization.objects.create(name="Idempotent Org")
        user = CustomUser.objects.create(username="idempotent")
        ou = OrgUser.objects.create(user=user, organization=org, mmr=4000)
        Row.objects.create(org_user=ou, game_type=DOTA2, mmr=4000)
        self.org_user_pk = ou.pk

    def test_existing_row_not_duplicated(self) -> None:
        Row = self.new_state.apps.get_model("org", "OrgUserGameMmr")
        rows = list(
            Row.objects.filter(org_user_id=self.org_user_pk).values_list(
                "game_type", "mmr"
            )
        )
        self.assertEqual(rows, [(DOTA2, 4000)])


class BackfillReverseTest(MigratorTestCase):
    migrate_from = ("org", "0015_backfill_org_user_game_mmr")
    migrate_to = ("org", "0014_orgusergamemmr")

    def prepare(self) -> None:
        apps = self.old_state.apps
        CustomUser = apps.get_model("app", "CustomUser")
        Organization = apps.get_model("app", "Organization")
        OrgUser = apps.get_model("org", "OrgUser")
        Row = apps.get_model("org", "OrgUserGameMmr")
        org = Organization.objects.create(name="Reverse Org")
        both = OrgUser.objects.create(
            user=CustomUser.objects.create(username="rev_both"),
            organization=org,
            mmr=999,
        )
        Row.objects.create(org_user=both, game_type=DOTA2, mmr=4000)
        Row.objects.create(org_user=both, game_type=DEADLOCK, mmr=2500)
        deadlock_only = OrgUser.objects.create(
            user=CustomUser.objects.create(username="rev_deadlock"),
            organization=org,
            mmr=777,
        )
        Row.objects.create(org_user=deadlock_only, game_type=DEADLOCK, mmr=1800)
        self.both_pk = both.pk
        self.deadlock_only_pk = deadlock_only.pk

    def test_orguser_mmr_restored_from_dota_rows(self) -> None:
        OrgUser = self.new_state.apps.get_model("org", "OrgUser")
        self.assertEqual(OrgUser.objects.get(pk=self.both_pk).mmr, 4000)
        self.assertEqual(OrgUser.objects.get(pk=self.deadlock_only_pk).mmr, 0)


class ReverseRestoreTest(MigratorTestCase):
    migrate_from = ("org", "0016_remove_orguser_mmr")
    migrate_to = ("org", "0013_conduct")

    def prepare(self) -> None:
        apps = self.old_state.apps
        CustomUser = apps.get_model("app", "CustomUser")
        Organization = apps.get_model("app", "Organization")
        OrgUser = apps.get_model("org", "OrgUser")
        Row = apps.get_model("org", "OrgUserGameMmr")
        org = Organization.objects.create(name="Restore Org")
        both = OrgUser.objects.create(
            user=CustomUser.objects.create(username="restore_both"),
            organization=org,
        )
        Row.objects.create(org_user=both, game_type=DOTA2, mmr=4200)
        Row.objects.create(org_user=both, game_type=DEADLOCK, mmr=2600)
        deadlock_only = OrgUser.objects.create(
            user=CustomUser.objects.create(username="restore_deadlock"),
            organization=org,
        )
        Row.objects.create(org_user=deadlock_only, game_type=DEADLOCK, mmr=1900)
        none = OrgUser.objects.create(
            user=CustomUser.objects.create(username="restore_none"),
            organization=org,
        )
        self.pks = {"both": both.pk, "deadlock": deadlock_only.pk, "none": none.pk}

    def test_orguser_mmr_restored_from_dota_rows(self) -> None:
        OrgUser = self.new_state.apps.get_model("org", "OrgUser")
        restored = dict(
            OrgUser.objects.filter(pk__in=self.pks.values()).values_list("pk", "mmr")
        )
        self.assertEqual(
            restored,
            {self.pks["both"]: 4200, self.pks["deadlock"]: 0, self.pks["none"]: 0},
        )

    def test_rating_table_dropped(self) -> None:
        self.assertNotIn("org_orgusergamemmr", connection.introspection.table_names())


class OrgMmrMigrationShapeTest(SimpleTestCase):
    def test_only_0016_is_destructive(self) -> None:
        graph = MigrationLoader(None, ignore_no_migrations=True).graph
        destructive: list[tuple[str, str, str]] = []
        for name in (
            "0014_orgusergamemmr",
            "0015_backfill_org_user_game_mmr",
            "0016_remove_orguser_mmr",
        ):
            for op in graph.nodes[("org", name)].operations:
                if isinstance(op, RemoveField):
                    destructive.append((name, op.model_name, op.name))
                elif isinstance(op, DeleteModel):
                    destructive.append((name, op.name, ""))
        self.assertEqual(destructive, [("0016_remove_orguser_mmr", "orguser", "mmr")])
        self.assertIn(
            ("org", "0015_backfill_org_user_game_mmr"),
            graph.nodes[("org", "0016_remove_orguser_mmr")].dependencies,
        )

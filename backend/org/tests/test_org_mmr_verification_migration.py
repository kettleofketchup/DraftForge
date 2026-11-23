import unittest
from datetime import UTC, datetime

try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image."
    ) from _import_error

DOTA2 = 1
DEADLOCK = 2
VERIFIED_ON = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


class VerificationBackfillTest(MigratorTestCase):
    migrate_from = ("org", "0022_retarget_tournament_models")
    migrate_to = ("org", "0023_orgusergamemmr_verification")

    def prepare(self) -> None:
        apps = self.old_state.apps
        CustomUser = apps.get_model("app", "CustomUser")
        Organization = apps.get_model("org", "Organization")
        OrgUser = apps.get_model("org", "OrgUser")
        Row = apps.get_model("org", "OrgUserGameMmr")
        org = Organization.objects.create(name="Verification Backfill Org")
        active = OrgUser.objects.create(
            user=CustomUser.objects.create(username="vb_active"),
            organization=org,
            has_active_dota_mmr=True,
            dota_mmr_last_verified=VERIFIED_ON,
        )
        inactive = OrgUser.objects.create(
            user=CustomUser.objects.create(username="vb_inactive"),
            organization=org,
            has_active_dota_mmr=False,
            dota_mmr_last_verified=VERIFIED_ON,
        )
        no_date = OrgUser.objects.create(
            user=CustomUser.objects.create(username="vb_no_date"),
            organization=org,
            has_active_dota_mmr=True,
        )
        self.active_dota = Row.objects.create(
            org_user=active, game_type=DOTA2, mmr=4000
        ).pk
        self.active_deadlock = Row.objects.create(
            org_user=active, game_type=DEADLOCK, mmr=2000
        ).pk
        self.inactive_dota = Row.objects.create(
            org_user=inactive, game_type=DOTA2, mmr=3000
        ).pk
        self.no_date_dota = Row.objects.create(
            org_user=no_date, game_type=DOTA2, mmr=3500
        ).pk

    def test_backfill_sets_verified_at_from_dota_last_verified(self) -> None:
        Row = self.new_state.apps.get_model("org", "OrgUserGameMmr")
        active = Row.objects.get(pk=self.active_dota)
        self.assertEqual(active.verified_at, VERIFIED_ON)
        self.assertIsNone(active.verified_by_id)
        for pk in (self.active_deadlock, self.inactive_dota, self.no_date_dota):
            other = Row.objects.get(pk=pk)
            self.assertIsNone(other.verified_at)
            self.assertIsNone(other.verified_by_id)

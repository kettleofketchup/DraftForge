import unittest
from datetime import UTC, datetime

# django-test-migrations is a dev dep; a stale CI image may lack it.
try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error

AT = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


class LeadershipLedgerMigrationTest(MigratorTestCase):
    migrate_from = ("org", "0016_backfill_org_user_game_mmr")
    migrate_to = ("org", "0017_leadership")

    def prepare(self) -> None:
        apps = self.old_state.apps
        CustomUser = apps.get_model("app", "CustomUser")
        Organization = apps.get_model("org", "Organization")
        OrgUser = apps.get_model("org", "OrgUser")
        Event = apps.get_model("events", "Event")
        Entry = apps.get_model("org", "ContributionEntry")
        user = CustomUser.objects.create(username="ledger_mig")
        org = Organization.objects.create(name="Ledger Migration Org")
        org_user = OrgUser.objects.create(user=user, organization=org)
        event = Event.objects.create(
            organization=org, name="Ledger Migration Event", scheduled_at=AT
        )
        self.pks = [
            Entry.objects.create(
                org_user=org_user,
                organization=org,
                kind="manual",
                points=3,
                reason="thanks",
                occurred_at=AT,
            ).pk,
            Entry.objects.create(
                org_user=org_user,
                organization=org,
                kind="event_host",
                points=10,
                event=event,
                event_name=event.name,
                occurred_at=AT,
            ).pk,
        ]

    def test_existing_rows_are_contribution(self) -> None:
        Entry = self.new_state.apps.get_model("org", "ContributionEntry")
        self.assertEqual(
            list(
                Entry.objects.filter(pk__in=self.pks)
                .order_by("pk")
                .values_list("track", flat=True)
            ),
            ["contribution", "contribution"],
        )

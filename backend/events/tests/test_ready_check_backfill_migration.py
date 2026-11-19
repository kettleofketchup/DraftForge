import unittest

# django-test-migrations is a dev dep; a stale CI image may lack it.
try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error

HOURS_TO_MINUTES: dict[int, int] = {3: 180, 0: 120, 48: 1440}


class BackfillReadyCheckOpenMinutesMigrationTest(MigratorTestCase):
    """events 0027: ready_check_open_minutes seeded from attendance hours."""

    migrate_from = [
        ("app", "0106_draftoptions_hero_grace_time_ms_and_more"),
        ("events", "0026_ready_check_settings"),
    ]
    migrate_to = ("events", "0027_backfill_ready_check_open_minutes")

    def prepare(self) -> None:
        apps = self.old_state.apps
        Organization = apps.get_model("app", "Organization")
        Event = apps.get_model("events", "Event")
        EventRepeater = apps.get_model("events", "EventRepeater")
        OrgEventDefaults = apps.get_model("events", "OrgEventDefaults")
        org = Organization.objects.create(name="Org")
        self.pks: dict[str, dict[int, int]] = {
            "Event": {},
            "EventRepeater": {},
            "OrgEventDefaults": {},
        }
        for hours in HOURS_TO_MINUTES:
            self.pks["Event"][hours] = Event.objects.create(
                organization=org,
                name=f"e{hours}",
                scheduled_at="2026-11-01T18:00:00Z",
                discord_confirm_attendance_hours=hours,
            ).pk
            self.pks["EventRepeater"][hours] = EventRepeater.objects.create(
                organization=org,
                name=f"r{hours}",
                frequency="weekly",
                time_of_day="18:00",
                starts_at="2026-11-01",
                discord_confirm_attendance_hours=hours,
            ).pk
            self.pks["OrgEventDefaults"][hours] = OrgEventDefaults.objects.create(
                organization=Organization.objects.create(name=f"Org {hours}"),
                discord_confirm_attendance_hours=hours,
            ).pk

    def test_hours_seed_open_minutes(self) -> None:
        for name, pks in self.pks.items():
            model = self.new_state.apps.get_model("events", name)
            for hours, pk in pks.items():
                with self.subTest(model=name, hours=hours):
                    self.assertEqual(
                        model.objects.get(pk=pk).ready_check_open_minutes,
                        HOURS_TO_MINUTES[hours],
                    )

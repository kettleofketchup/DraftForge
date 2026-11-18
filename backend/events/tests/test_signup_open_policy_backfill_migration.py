import unittest

# django-test-migrations is a dev dep; a stale CI image may lack it.
try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error


class BackfillSignupOpenPolicyMigrationTest(MigratorTestCase):
    """events 0027: upcoming events with a legacy signups_open_at become
    scheduled, so the row never says manual with a scheduled time."""

    migrate_from = [
        ("app", "0106_draftoptions_hero_grace_time_ms_and_more"),
        ("events", "0026_signup_open_policy"),
    ]
    migrate_to = ("events", "0027_backfill_signup_open_policy")

    def prepare(self) -> None:
        Organization = self.old_state.apps.get_model("app", "Organization")
        Event = self.old_state.apps.get_model("events", "Event")
        org = Organization.objects.create(name="Org")
        start = "2026-12-10T18:00:00Z"

        def event(name: str, state: str, open_at: str | None) -> int:
            return Event.objects.create(
                organization=org,
                name=name,
                scheduled_at=start,
                state=state,
                signups_open_at=open_at,
            ).pk

        self.pks = {
            "legacy_two_days": event("a", "upcoming", "2026-12-08T18:00:00Z"),
            "legacy_rounds": event("b", "upcoming", "2026-12-09T05:20:00Z"),
            "legacy_after_start": event("c", "upcoming", "2026-12-10T20:00:00Z"),
            "legacy_too_early": event("d", "upcoming", "2026-08-01T18:00:00Z"),
            "manual_no_time": event("e", "upcoming", None),
            "already_open": event("f", "signups_open", "2026-12-08T18:00:00Z"),
        }

    def test_policy(self) -> None:
        Event = self.new_state.apps.get_model("events", "Event")
        policy = {
            key: (
                Event.objects.get(pk=pk).signup_open_mode,
                Event.objects.get(pk=pk).signups_open_hours_before,
            )
            for key, pk in self.pks.items()
        }
        self.assertEqual(
            policy,
            {
                "legacy_two_days": ("scheduled", 48),
                "legacy_rounds": ("scheduled", 37),
                "legacy_after_start": ("scheduled", 0),
                "legacy_too_early": ("scheduled", 1440),
                "manual_no_time": ("manual", 72),
                "already_open": ("manual", 72),
            },
        )

    def test_open_time_kept(self) -> None:
        Event = self.new_state.apps.get_model("events", "Event")
        self.assertEqual(
            Event.objects.get(
                pk=self.pks["legacy_two_days"]
            ).signups_open_at.isoformat(),
            "2026-12-08T18:00:00+00:00",
        )

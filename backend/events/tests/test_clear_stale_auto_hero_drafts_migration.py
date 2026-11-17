import unittest

# django-test-migrations is a dev dep; a stale CI image may lack it.
try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error


class ClearStaleAutoHeroDraftsMigrationTest(MigratorTestCase):
    """events 0022: auto-create stays on only for past tournaments and ones
    whose Event has not finished."""

    migrate_from = [
        ("app", "0105_orglog_reopen_event"),
        ("events", "0021_event_end_and_staff"),
    ]
    migrate_to = ("events", "0022_clear_stale_auto_hero_drafts")

    def prepare(self) -> None:
        apps = self.old_state.apps
        Tournament = apps.get_model("app", "Tournament")
        Organization = apps.get_model("app", "Organization")
        Event = apps.get_model("events", "Event")
        org = Organization.objects.create(name="Org")
        date = "2026-11-01T18:00:00Z"

        def tournament(name: str, state: str, event_state: str | None = None) -> int:
            t = Tournament.objects.create(
                name=name, date_played=date, state=state, auto_create_hero_drafts=True
            )
            if event_state:
                Event.objects.create(
                    organization=org,
                    name=name,
                    scheduled_at=date,
                    state=event_state,
                    tournament=t,
                )
            return t.pk

        self.pks = {
            "standalone_future": tournament("a", "future"),
            "standalone_in_progress": tournament("b", "in_progress"),
            "completed_event": tournament("c", "in_progress", "completed"),
            "cancelled_event": tournament("d", "future", "cancelled"),
            "running_event": tournament("e", "in_progress", "in_progress"),
            "upcoming_event": tournament("f", "future", "signups_open"),
            "past": tournament("g", "past"),
        }

    def test_flags(self) -> None:
        Tournament = self.new_state.apps.get_model("app", "Tournament")
        flags = {
            key: Tournament.objects.get(pk=pk).auto_create_hero_drafts
            for key, pk in self.pks.items()
        }
        self.assertEqual(
            flags,
            {
                "standalone_future": False,
                "standalone_in_progress": False,
                "completed_event": False,
                "cancelled_event": False,
                "running_event": True,
                "upcoming_event": True,
                "past": True,
            },
        )

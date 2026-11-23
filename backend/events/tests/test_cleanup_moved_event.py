import importlib.util
import re
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone as tz

from app.models import CustomUser
from events.constants import EventState, RepeatFrequency, SignupAction, SignupStatus
from events.ledger import ActorRole, SignupMeans
from events.models import Event, EventRepeater, EventSignup, SignupLedgerEntry
from org.models import Organization

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "cleanup_stale_repeater_events.py"
)


def _load_script() -> ModuleType:
    # backend/scripts is not a package, so load the file directly.
    spec = importlib.util.spec_from_file_location(
        "cleanup_stale_repeater_events", _SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cleanup = _load_script()


def _next_sunday(min_days: int) -> datetime:
    day = (tz.now() + timedelta(days=min_days)).astimezone(dt_timezone.utc)
    day += timedelta(days=(6 - day.weekday()) % 7)
    return day.replace(hour=18, minute=0, second=0, microsecond=0)


class CleanupMovedEventTests(TestCase):
    def setUp(self) -> None:
        self.admin = CustomUser.objects.create(username="cme_admin")
        self.org = Organization.objects.create(name="Cleanup Org", owner=self.admin)
        self.mover = CustomUser.objects.create(username="cme_mover")
        self.clash = CustomUser.objects.create(username="cme_clash")
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Cleanup Series",
            frequency=RepeatFrequency.WEEKLY,
            day_of_week=0,
            time_of_day=time(18, 0),
            starts_at=tz.now().date(),
            timezone="UTC",
            created_by=self.admin,
        )
        self.sunday = _next_sunday(3)

    def _event(self, name: str, when: datetime, state: str) -> Event:
        return Event.objects.create(
            organization=self.org,
            event_repeater=self.repeater,
            name=name,
            scheduled_at=when,
            state=state,
            created_by=self.admin,
        )

    def _ledger(self, *events: Event) -> list[SignupLedgerEntry]:
        return list(
            SignupLedgerEntry.objects.filter(event__in=events)
            .exclude(action=SignupAction.BACKFILLED)
            .order_by("pk")
        )

    def test_migrate_signups_records_pair(self) -> None:
        stale = self._event(
            "Stale", self.sunday + timedelta(days=1), EventState.SIGNUPS_OPEN
        )
        target = self._event("Target", self.sunday, EventState.SIGNUPS_OPEN)
        moved_row = EventSignup.objects.create(
            event=stale, user=self.mover, status=SignupStatus.APPROVED
        )
        clash_row = EventSignup.objects.create(
            event=stale, user=self.clash, status=SignupStatus.APPROVED
        )
        EventSignup.objects.create(
            event=target, user=self.clash, status=SignupStatus.APPROVED
        )
        baseline = SignupLedgerEntry.objects.count()

        moved, skipped = cleanup.migrate_signups(
            stale, target, correlation_id="cleanup-0123456789ab"
        )

        self.assertEqual((moved, skipped), (1, 1))
        self.assertEqual(SignupLedgerEntry.objects.count(), baseline + 2)
        source, dest = self._ledger(stale, target)
        moved_row.refresh_from_db()
        self.assertEqual(moved_row.event_id, target.pk)
        for entry in (source, dest):
            self.assertEqual(entry.action, SignupAction.MOVED_EVENT)
            self.assertEqual(entry.actor_role, ActorRole.SYSTEM)
            self.assertEqual(entry.means, SignupMeans.SYSTEM)
            self.assertIsNone(entry.actor_user_id)
            self.assertEqual(entry.correlation_id, "cleanup-0123456789ab")
            self.assertEqual(entry.signup_id, moved_row.pk)
            self.assertEqual(entry.subject_user_id, self.mover.pk)
            self.assertEqual(entry.before["status"], SignupStatus.APPROVED)
            self.assertEqual(entry.after["status"], SignupStatus.APPROVED)
            self.assertEqual(entry.before["extra"], {"event_id": stale.pk})
            self.assertEqual(entry.after["extra"], {"event_id": target.pk})
        self.assertEqual(source.event_id, stale.pk)
        self.assertIsNone(source.caused_by_id)
        self.assertEqual(dest.event_id, target.pk)
        self.assertEqual(dest.caused_by_id, source.pk)
        clash_row.refresh_from_db()
        self.assertEqual(clash_row.event_id, stale.pk)
        self.assertFalse(
            SignupLedgerEntry.objects.filter(subject_user=self.clash).exists()
        )

    def _run_main(self, *argv: str) -> None:
        with (
            patch.object(cleanup, "generate_events_for_repeater", return_value=[]),
            patch("sys.argv", ["cleanup", str(self.repeater.pk), *argv]),
        ):
            cleanup.main()

    def test_main_apply_uses_one_correlation_id_per_run(self) -> None:
        target = self._event("Target", self.sunday, EventState.UPCOMING)
        stale_a = self._event(
            "Stale A", self.sunday + timedelta(days=1), EventState.UPCOMING
        )
        stale_b = self._event(
            "Stale B", self.sunday + timedelta(days=2), EventState.UPCOMING
        )
        EventSignup.objects.create(
            event=stale_a, user=self.mover, status=SignupStatus.APPROVED
        )
        EventSignup.objects.create(
            event=stale_b, user=self.clash, status=SignupStatus.APPROVED
        )

        self._run_main("--apply")

        entries = self._ledger(stale_a, stale_b, target)
        self.assertEqual(len(entries), 4)
        ids = {e.correlation_id for e in entries}
        self.assertEqual(len(ids), 1)
        self.assertRegex(ids.pop(), re.compile(r"^cleanup-[0-9a-f]{12}$"))

    def test_main_dry_run_records_nothing(self) -> None:
        self._event("Target", self.sunday, EventState.UPCOMING)
        stale = self._event(
            "Stale", self.sunday + timedelta(days=1), EventState.UPCOMING
        )
        row = EventSignup.objects.create(
            event=stale, user=self.mover, status=SignupStatus.APPROVED
        )
        baseline = SignupLedgerEntry.objects.count()

        self._run_main()

        self.assertEqual(SignupLedgerEntry.objects.count(), baseline)
        row.refresh_from_db()
        self.assertEqual(row.event_id, stale.pk)

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
from tournament.models import Tournament

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

    def _user(self, name: str) -> CustomUser:
        return CustomUser.objects.create(username=f"cme_{name}")

    def _signup(
        self, event: Event, user: CustomUser, status: str, position: int | None = None
    ) -> EventSignup:
        return EventSignup.objects.create(
            event=event, user=user, status=status, waitlist_position=position
        )

    def test_migrate_signups_seats_only_while_target_has_room(self) -> None:
        stale = self._event(
            "Stale", self.sunday + timedelta(days=1), EventState.SIGNUPS_OPEN
        )
        target = self._event("Target", self.sunday, EventState.SIGNUPS_OPEN)
        target.max_players = 2
        target.save(update_fields=["max_players"])
        self._signup(target, self._user("held"), SignupStatus.APPROVED)
        target_wait = self._signup(
            target, self._user("twait"), SignupStatus.WAITLISTED, 1
        )
        first = self._signup(stale, self._user("first"), SignupStatus.APPROVED)
        second = self._signup(stale, self._user("second"), SignupStatus.CONFIRMED)
        third = self._signup(stale, self._user("third"), SignupStatus.RSVP)
        stale_wait = self._signup(
            stale, self._user("swait"), SignupStatus.WAITLISTED, 1
        )

        moved, skipped = cleanup.migrate_signups(
            stale, target, correlation_id="cleanup-0123456789ab"
        )

        self.assertEqual((moved, skipped), (4, 0))
        for row in (first, second, third, stale_wait, target_wait):
            row.refresh_from_db()
        self.assertEqual(
            (first.status, first.waitlist_position), (SignupStatus.APPROVED, None)
        )
        self.assertEqual(
            [
                (r.pk, r.status, r.waitlist_position)
                for r in EventSignup.objects.filter(
                    event=target, status=SignupStatus.WAITLISTED
                ).order_by("waitlist_position")
            ],
            [
                (target_wait.pk, SignupStatus.WAITLISTED, 1),
                (second.pk, SignupStatus.WAITLISTED, 2),
                (third.pk, SignupStatus.WAITLISTED, 3),
                (stale_wait.pk, SignupStatus.WAITLISTED, 4),
            ],
        )
        dest = SignupLedgerEntry.objects.get(
            event=target, signup=second, action=SignupAction.MOVED_EVENT
        )
        self.assertEqual(dest.before["status"], SignupStatus.CONFIRMED)
        self.assertIsNone(dest.before["waitlist_position"])
        self.assertEqual(dest.after["status"], SignupStatus.WAITLISTED)
        self.assertEqual(dest.after["waitlist_position"], 2)
        source = SignupLedgerEntry.objects.get(
            event=stale, signup=second, action=SignupAction.MOVED_EVENT
        )
        self.assertEqual(source.after, dest.after)
        waited = SignupLedgerEntry.objects.get(
            event=target, signup=stale_wait, action=SignupAction.MOVED_EVENT
        )
        self.assertEqual(waited.before["waitlist_position"], 1)
        self.assertEqual(waited.after["waitlist_position"], 4)
        self.assertFalse(
            SignupLedgerEntry.objects.filter(action=SignupAction.PROMOTED).exists()
        )

    def test_migrate_signups_promotes_moved_waitlist_into_free_seats(self) -> None:
        stale = self._event(
            "Stale", self.sunday + timedelta(days=1), EventState.SIGNUPS_OPEN
        )
        stale.max_players = 1
        stale.save(update_fields=["max_players"])
        target = self._event("Target", self.sunday, EventState.SIGNUPS_OPEN)
        target.max_players = 3
        target.save(update_fields=["max_players"])
        seated = self._signup(stale, self._user("seated"), SignupStatus.APPROVED)
        earlier = self._signup(stale, self._user("earlier"), SignupStatus.WAITLISTED, 2)
        later = self._signup(stale, self._user("later"), SignupStatus.WAITLISTED, 1)

        cleanup.migrate_signups(stale, target, correlation_id="cleanup-0123456789ab")

        for row in (seated, later, earlier):
            row.refresh_from_db()
        self.assertEqual(seated.status, SignupStatus.APPROVED)
        self.assertIsNone(earlier.waitlist_position)
        self.assertNotEqual(earlier.status, SignupStatus.WAITLISTED)
        self.assertIsNone(later.waitlist_position)
        self.assertNotEqual(later.status, SignupStatus.WAITLISTED)
        earlier_move = SignupLedgerEntry.objects.get(
            event=target, signup=earlier, action=SignupAction.MOVED_EVENT
        )
        self.assertEqual(earlier_move.before["waitlist_position"], 1)
        self.assertEqual(earlier_move.after["status"], SignupStatus.WAITLISTED)
        self.assertEqual(earlier_move.after["waitlist_position"], 1)
        later_move = SignupLedgerEntry.objects.get(
            event=target, signup=later, action=SignupAction.MOVED_EVENT
        )
        self.assertEqual(later_move.before["waitlist_position"], 1)
        self.assertEqual(later_move.after["waitlist_position"], 2)
        promoted = SignupLedgerEntry.objects.filter(
            event=target, action=SignupAction.PROMOTED
        )
        self.assertEqual(promoted.count(), 2)
        for entry in promoted:
            self.assertEqual(entry.caused_by_id, earlier_move.pk)
            self.assertEqual(entry.correlation_id, "cleanup-0123456789ab")

    def test_migrate_signups_moves_waitlist_in_line_order(self) -> None:
        stale = self._event(
            "Stale", self.sunday + timedelta(days=1), EventState.SIGNUPS_OPEN
        )
        target = self._event("Target", self.sunday, EventState.SIGNUPS_OPEN)
        target.max_players = 1
        target.save(update_fields=["max_players"])
        self._signup(target, self._user("held"), SignupStatus.APPROVED)
        target_wait = self._signup(
            target, self._user("twait"), SignupStatus.WAITLISTED, 7
        )
        first = self._signup(stale, self._user("first"), SignupStatus.WAITLISTED, 3)
        second = self._signup(stale, self._user("second"), SignupStatus.WAITLISTED, 1)
        third = self._signup(stale, self._user("third"), SignupStatus.WAITLISTED, 2)

        cleanup.migrate_signups(stale, target, correlation_id="cleanup-0123456789ab")

        waiting = list(
            EventSignup.objects.filter(
                event=target, status=SignupStatus.WAITLISTED
            ).in_line_order()
        )
        self.assertEqual(
            [r.pk for r in waiting], [target_wait.pk, first.pk, second.pk, third.pk]
        )
        self.assertEqual([r.waitlist_position for r in waiting[1:]], [8, 9, 10])
        for rank, row in enumerate((first, second, third), start=1):
            dest = SignupLedgerEntry.objects.get(
                event=target, signup=row, action=SignupAction.MOVED_EVENT
            )
            self.assertEqual(dest.before["waitlist_position"], 1)
            self.assertEqual(dest.after["waitlist_position"], rank + 1)

    def test_migrate_tournament_users_skips_overflow(self) -> None:
        stale = self._event(
            "Stale", self.sunday + timedelta(days=1), EventState.SIGNUPS_OPEN
        )
        target = self._event("Target", self.sunday, EventState.SIGNUPS_OPEN)
        target.max_players = 1
        stale.tournament = Tournament.objects.create(name="S", date_played=tz.now())
        target.tournament = Tournament.objects.create(name="T", date_played=tz.now())
        stale.save(update_fields=["tournament"])
        target.save(update_fields=["max_players", "tournament"])
        fits = self._user("fits")
        spills = self._user("spills")
        self._signup(stale, fits, SignupStatus.APPROVED)
        self._signup(stale, spills, SignupStatus.APPROVED)
        stale.tournament.users.add(fits, spills)

        cleanup.migrate_signups(stale, target, correlation_id="cleanup-0123456789ab")
        added = cleanup.migrate_tournament_users(stale, target)

        self.assertEqual(added, 1)
        self.assertEqual(
            set(target.tournament.users.values_list("pk", flat=True)), {fits.pk}
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

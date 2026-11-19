from datetime import timedelta
from io import StringIO
from unittest import mock

from django.apps import apps
from django.core.management import call_command
from django.db import connection
from django.utils import timezone as tz
from structlog.testing import capture_logs

from app.models import CustomUser
from events.constants import EventState, SignupAction, SignupStatus
from events.line_backfill import BackfillResult, backfill_signup_line
from events.models import Event, EventSignup, SignupLedgerEntry
from events.services import process_rsvp
from events.tests.base import EventTestCase
from user.models import BaseUserProfile


class LineBackfillBase(EventTestCase):
    def setUp(self) -> None:
        self.players = [
            CustomUser.objects.create_user(username=f"backfill_p{i}") for i in range(4)
        ]

    def make_event(self, name: str) -> Event:
        return Event.objects.create(
            organization=self.org,
            name=name,
            scheduled_at=tz.now() + timedelta(days=5),
            state=EventState.SIGNUPS_OPEN,
        )

    def signup(
        self, user: CustomUser, *, event: Event | None = None, **kwargs: object
    ) -> EventSignup:
        return EventSignup.objects.create(
            event=event or self.event, user=user, **kwargs
        )

    def unstamp(self, *signups: EventSignup) -> None:
        EventSignup._base_manager.filter(pk__in=[s.pk for s in signups]).update(
            line_seq=None
        )

    def entries_for(self, signup: EventSignup) -> list[SignupLedgerEntry]:
        return list(
            SignupLedgerEntry.objects.filter(
                signup_id=signup.pk, action=SignupAction.BACKFILLED
            )
        )

    def seqs(self) -> dict[int, int | None]:
        return dict(
            EventSignup._base_manager.nocache()
            .filter(event=self.event)
            .values_list("pk", "line_seq")
        )


class LineBackfillTests(LineBackfillBase):
    def test_twice_is_idempotent(self) -> None:
        rows = [self.signup(p) for p in self.players[:3]]
        self.unstamp(*rows)
        first = backfill_signup_line(apps)
        seqs = self.seqs()
        second = backfill_signup_line(apps)

        self.assertFalse(first.rerun)
        self.assertEqual(first.signups_stamped, 3)
        self.assertEqual(first.ledger_entries, 3)
        self.assertEqual(sorted(seqs.values()), [1, 2, 3])
        self.assertTrue(second.rerun)
        self.assertEqual(second.signups_stamped, 0)
        self.assertEqual(second.ledger_entries, 0)
        self.assertEqual(self.seqs(), seqs)
        for row in rows:
            self.assertEqual(len(self.entries_for(row)), 1)

    def test_rerun_appends_null_rows(self) -> None:
        rows = [self.signup(p) for p in self.players[:3]]
        self.unstamp(*rows)
        backfill_signup_line(apps)
        untouched = {
            r["id"]: r
            for r in EventSignup._base_manager.nocache()
            .filter(pk__in=[r.pk for r in rows])
            .values()
        }
        late = self.signup(self.players[3])
        self.unstamp(late)

        result = backfill_signup_line(apps)

        self.assertTrue(result.rerun)
        self.assertEqual(result.signups_stamped, 1)
        self.assertEqual(result.ledger_entries, 1)
        late = EventSignup.objects.nocache().get(pk=late.pk)
        self.assertEqual(late.line_seq, 4)
        self.assertEqual(late.signed_up_at, late.created_at)
        self.assertEqual(late.first_signed_up_at, late.created_at)
        [entry] = self.entries_for(late)
        self.assertEqual(entry.after["line_seq"], 4)
        for pk, values in untouched.items():
            self.assertEqual(
                EventSignup._base_manager.nocache().filter(pk=pk).values().get(),
                values,
            )
            self.assertEqual(len(self.entries_for(EventSignup(pk=pk))), 1)

    def test_decline_only_row_has_no_first_fields(self) -> None:
        declined = self.signup(self.players[0], status=SignupStatus.CANCELLED)
        cancelled = self.signup(self.players[1])
        later = tz.now() + timedelta(hours=1)
        EventSignup._base_manager.filter(pk=declined.pk).update(
            first_signed_up_at=tz.now(), first_commitment="main"
        )
        EventSignup._base_manager.filter(pk=cancelled.pk).update(
            status=SignupStatus.CANCELLED, updated_at=later
        )
        self.unstamp(declined, cancelled)

        backfill_signup_line(apps)

        declined = EventSignup.objects.nocache().get(pk=declined.pk)
        cancelled = EventSignup.objects.nocache().get(pk=cancelled.pk)
        self.assertIsNotNone(declined.line_seq)
        self.assertIsNone(declined.first_signed_up_at)
        self.assertIsNone(declined.first_commitment)
        self.assertIsNone(declined.first_rsvp_class)
        self.assertEqual(cancelled.first_signed_up_at, cancelled.created_at)
        self.assertEqual(cancelled.first_commitment, "main")

    def test_rerun_skips_signups_created_after_backfill(self) -> None:
        self.signup(self.players[0])
        backfill_signup_line(apps)
        fresh = process_rsvp(self.event, self.players[1])

        result = backfill_signup_line(apps)

        self.assertEqual(result.ledger_entries, 0)
        self.assertEqual(self.entries_for(fresh), [])

    def test_user_without_profile(self) -> None:
        user = self.players[0]
        BaseUserProfile.objects.filter(user=user).delete()
        row = self.signup(user)
        self.unstamp(row)

        backfill_signup_line(apps)

        [entry] = self.entries_for(row)
        self.assertIsNone(entry.subject_snapshot["nickname"])
        self.assertEqual(entry.subject_snapshot["username"], user.username)

    def test_nickname_in_snapshot(self) -> None:
        row = self.signup(self.user)
        self.unstamp(row)
        backfill_signup_line(apps)
        [entry] = self.entries_for(row)
        self.assertEqual(entry.subject_snapshot["nickname"], "EventUser")
        self.assertEqual(entry.subject_snapshot["discord_id"], "987654321")

    def test_empty_event_and_waitlist_only_event(self) -> None:
        empty = self.make_event("Empty")
        waitlist_event = self.make_event("Waitlist only")
        positions = [3, 1, None, 2]
        rows = [
            self.signup(
                p,
                event=waitlist_event,
                status=SignupStatus.WAITLISTED,
                waitlist_position=pos,
            )
            for p, pos in zip(self.players, positions)
        ]
        self.unstamp(*rows)

        result = backfill_signup_line(apps)

        self.assertEqual(result.events, Event.objects.count())
        self.assertFalse(EventSignup.objects.filter(event=empty).exists())
        self.assertFalse(SignupLedgerEntry.objects.filter(event_id=empty.pk).exists())
        ordered = list(
            EventSignup.objects.nocache()
            .filter(event=waitlist_event)
            .values_list("waitlist_position", "line_seq")
        )
        self.assertEqual(ordered, [(1, 1), (2, 2), (3, 3), (None, 4)])
        stamps = list(
            EventSignup.objects.nocache()
            .filter(event=waitlist_event)
            .values_list("signed_up_at", flat=True)
        )
        self.assertEqual(stamps, sorted(stamps))

    def test_logs_signup_line_backfilled(self) -> None:
        row = self.signup(self.players[0])
        self.unstamp(row)
        with capture_logs() as logs:
            result = backfill_signup_line(apps)
        [entry] = [e for e in logs if e["event"] == "signup_line_backfilled"]
        self.assertEqual(entry["system"], "events")
        self.assertEqual(entry["subsystem"], "migration")
        self.assertEqual(entry["log_level"], "info")
        self.assertEqual(
            {
                k: entry[k]
                for k in ("events", "signups_stamped", "ledger_entries", "rerun")
            },
            {
                "events": result.events,
                "signups_stamped": 1,
                "ledger_entries": 1,
                "rerun": False,
            },
        )
        self.assertIsInstance(result, BackfillResult)


class BackfillCommandTests(LineBackfillBase):
    patch_target = "events.management.commands.backfill_signup_line.invalidate_model"

    def test_management_command(self) -> None:
        row = self.signup(self.players[0])
        self.unstamp(row)
        buf = StringIO()
        with mock.patch(self.patch_target) as invalidate:
            call_command("backfill_signup_line", stdout=buf)
        invalidate.assert_called_once_with(EventSignup)
        events = Event.objects.count()
        self.assertIn(
            f"events={events} signups_stamped=1 ledger_entries=1 rerun=False",
            buf.getvalue(),
        )

        buf = StringIO()
        with mock.patch(self.patch_target) as invalidate:
            call_command("backfill_signup_line", stdout=buf)
        invalidate.assert_not_called()
        self.assertIn(
            f"events={events} signups_stamped=0 ledger_entries=0 rerun=True",
            buf.getvalue(),
        )

    def test_command_rerun_fixes_old_code_tentative_row(self) -> None:
        stamped = [self.signup(p) for p in self.players[:2]]
        call_command("backfill_signup_line", stdout=StringIO())
        now = tz.now().isoformat()
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO events_eventsignup "
                "(event_id, user_id, signup_type, status, unmet_requirements, "
                "created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, '[]', %s, %s)",
                [self.event.pk, self.players[2].pk, "user", "tentative", now, now],
            )
        old = EventSignup.objects.nocache().get(event=self.event, user=self.players[2])
        self.assertIsNone(old.line_seq)
        self.assertEqual(old.first_commitment, "main")

        call_command("backfill_signup_line", stdout=StringIO())

        row = EventSignup.objects.nocache().get(pk=old.pk)
        self.assertEqual(row.line_seq, max(s.line_seq for s in stamped) + 1)
        self.assertEqual(row.commitment, "maybe")
        self.assertEqual(row.first_commitment, "maybe")
        self.assertEqual(row.first_signed_up_at, row.created_at)
        self.assertEqual(row.signed_up_at, row.created_at)
        self.assertEqual(len(self.entries_for(row)), 1)

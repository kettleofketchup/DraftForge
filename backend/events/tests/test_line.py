import ast
import inspect
import textwrap
from datetime import datetime, timedelta
from typing import Any
from unittest import mock

from django.db import connection
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone as tz
from structlog.testing import capture_logs

from app.models import CustomUser, Organization
from events import line
from events.constants import Commitment, EventState, RsvpClass, SignupStatus
from events.exceptions import ImmutableFieldError
from events.line import (
    EventSignupQuerySet,
    line_order_by,
    next_line_seq,
    restore_place,
    same_gate_distance,
    stamp,
    swap_places,
)
from events.models import Event, EventSignup
from events.schemas import SignupSnapshot
from events.tests.base import EventTestCase

FIRST_COLUMNS = {"first_signed_up_at", "first_commitment", "first_rsvp_class"}


class LineTestBase(EventTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.players = [
            CustomUser.objects.create_user(username=f"line_player_{i}")
            for i in range(5)
        ]
        cls.other_event = Event.objects.create(
            organization=cls.org,
            name="Other Event",
            scheduled_at=tz.now() + timedelta(days=8),
            state=EventState.SIGNUPS_OPEN,
            created_by=cls.admin,
        )

    def signup(self, i: int, event: Event | None = None, **kwargs: Any) -> EventSignup:
        return EventSignup.objects.create(
            event=event or self.event, user=self.players[i], **kwargs
        )


class NextLineSeqTests(LineTestBase):
    def test_next_line_seq_empty_event_is_1(self) -> None:
        self.assertEqual(next_line_seq(self.event), 1)

    def test_next_line_seq_is_max_plus_one(self) -> None:
        s = self.signup(0)
        EventSignup.objects.filter(pk=s.pk).update(line_seq=7)
        self.assertEqual(next_line_seq(self.event), 8)

    def test_next_line_seq_ignores_other_events(self) -> None:
        for i in range(3):
            self.signup(i, self.event)
            self.signup(i, self.other_event)
        for event in (self.event, self.other_event):
            seqs = list(
                EventSignup.objects.filter(event=event).values_list(
                    "line_seq", flat=True
                )
            )
            self.assertEqual(seqs, [1, 2, 3])

    def test_sequential_creates_with_cache_enabled(self) -> None:
        seqs = [self.signup(i).line_seq for i in range(3)]
        self.assertEqual(seqs, [1, 2, 3])

    def test_stamp_keys(self) -> None:
        self.assertEqual(set(stamp(self.event)), {"line_seq", "signed_up_at"})
        at = datetime(2026, 1, 2, tzinfo=tz.get_current_timezone())
        self.assertEqual(stamp(self.event, at=at)["signed_up_at"], at)


class AutoStampTests(LineTestBase):
    def test_auto_stamp_on_create(self) -> None:
        s = self.signup(0)
        s.refresh_from_db()
        self.assertEqual(s.line_seq, 1)
        self.assertIsNotNone(s.signed_up_at)
        self.assertEqual(s.first_signed_up_at, s.signed_up_at)
        self.assertEqual(s.commitment, "main")
        self.assertEqual(s.first_commitment, "main")
        self.assertEqual(s.rsvp_class, "standard")
        self.assertEqual(s.first_rsvp_class, "standard")

    def test_tentative_insert_is_maybe(self) -> None:
        s = self.signup(0, status=SignupStatus.TENTATIVE)
        s.refresh_from_db()
        self.assertEqual(s.commitment, "maybe")
        self.assertEqual(s.first_commitment, "maybe")

    def test_explicit_first_commitment_kept(self) -> None:
        s = self.signup(0, status=SignupStatus.TENTATIVE, first_commitment="main")
        s.refresh_from_db()
        self.assertEqual(s.first_commitment, "main")
        self.assertEqual(s.commitment, "maybe")


class FirstFieldGuardTests(LineTestBase):
    def assert_blocked_log(self, logs: list[dict[str, Any]], signup_id: int) -> None:
        blocked = [
            e for e in logs if e["event"] == "signup_first_fields_mutation_blocked"
        ]
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["system"], "events")
        self.assertEqual(blocked[0]["subsystem"], "line")
        self.assertEqual(blocked[0]["signup_id"], signup_id)
        self.assertIn("first_commitment", blocked[0]["fields"])

    def test_first_fields_immutable_on_save(self) -> None:
        s = EventSignup.objects.get(pk=self.signup(0).pk)
        s.first_commitment = "maybe"
        with capture_logs() as logs, self.assertRaises(ImmutableFieldError):
            s.save()
        self.assert_blocked_log(logs, s.pk)

        with capture_logs() as logs, self.assertRaises(ImmutableFieldError):
            s.save(update_fields=["status"])
        self.assert_blocked_log(logs, s.pk)

        fresh = EventSignup.objects.get(pk=s.pk)
        fresh.status = SignupStatus.APPROVED
        fresh.save()
        self.assertEqual(
            EventSignup.objects.nocache().get(pk=s.pk).first_commitment, "main"
        )

    def test_first_fields_guard_without_from_db(self) -> None:
        existing = self.signup(0)
        original = EventSignup.objects.nocache().get(pk=existing.pk)
        clone = EventSignup(
            pk=existing.pk,
            event=self.event,
            user=self.players[0],
            first_signed_up_at=original.first_signed_up_at - timedelta(days=3),
        )
        self.assertTrue(clone._state.adding)
        with capture_logs() as logs, self.assertRaises(ImmutableFieldError):
            clone.save()
        blocked = [
            e for e in logs if e["event"] == "signup_first_fields_mutation_blocked"
        ]
        self.assertEqual(len(blocked), 1)
        self.assertIn("first_signed_up_at", blocked[0]["fields"])
        row = EventSignup.objects.nocache().get(pk=existing.pk)
        self.assertEqual(row.first_signed_up_at, original.first_signed_up_at)
        self.assertEqual(row.line_seq, original.line_seq)

        unused_pk = existing.pk + 1000
        fresh = EventSignup(pk=unused_pk, event=self.event, user=self.players[1])
        fresh.save()
        row = EventSignup.objects.nocache().get(pk=unused_pk)
        self.assertEqual(row.line_seq, 2)
        self.assertEqual(row.first_commitment, "main")

    def test_deferred_first_fields_skip_guard(self) -> None:
        pk = self.signup(0).pk
        s = EventSignup.objects.only("id", "status", "event").get(pk=pk)
        s.status = SignupStatus.APPROVED
        with CaptureQueriesContext(connection) as ctx:
            s.save(update_fields=["status"])
        for q in ctx.captured_queries:
            sql = q["sql"]
            if not sql.lstrip().upper().startswith("SELECT"):
                continue
            cols = sql.split("FROM", 1)[0]
            selected = {
                c.strip().split(".")[-1].strip('"')
                for c in cols[len("SELECT") :].split(",")
            }
            self.assertFalse(selected and selected <= FIRST_COLUMNS, sql)
        self.assertEqual(
            EventSignup.objects.nocache().get(pk=pk).status, SignupStatus.APPROVED
        )

    def test_refresh_from_db_rebuilds_loaded_state(self) -> None:
        s = EventSignup.objects.get(pk=self.signup(0).pk)
        EventSignup._base_manager.filter(pk=s.pk).update(event=self.other_event)
        s.refresh_from_db()
        seq = s.line_seq
        with capture_logs() as logs:
            s.save()
        self.assertEqual(EventSignup.objects.nocache().get(pk=s.pk).line_seq, seq)
        self.assertFalse(
            [e for e in logs if e["event"] == "signup_line_restamped_on_event_change"]
        )

    def test_queryset_update_first_field_raises(self) -> None:
        s = self.signup(0)
        with capture_logs() as logs, self.assertRaises(ImmutableFieldError):
            EventSignup.objects.filter(pk=s.pk).update(first_commitment="maybe")
        blocked = [
            e for e in logs if e["event"] == "signup_first_fields_mutation_blocked"
        ]
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["system"], "events")
        self.assertEqual(blocked[0]["subsystem"], "line")
        self.assertEqual(blocked[0]["fields"], ["first_commitment"])

        self.assertEqual(
            EventSignup.objects.filter(pk=s.pk).update(status="approved"), 1
        )
        s.first_rsvp_class = "standard"
        with self.assertRaises(ImmutableFieldError):
            EventSignup.objects.bulk_update([s], ["first_rsvp_class"])
        EventSignup._base_manager.bulk_update([s], ["first_rsvp_class"])


class EventChangeTests(LineTestBase):
    def test_event_change_restamps(self) -> None:
        self.signup(0, self.other_event)
        self.signup(1, self.other_event)
        mover = EventSignup.objects.get(pk=self.signup(2).pk)
        old_signed = mover.signed_up_at
        old_first = (
            mover.first_signed_up_at,
            mover.first_commitment,
            mover.first_rsvp_class,
        )
        mover.event = self.other_event
        with capture_logs() as logs:
            mover.save(update_fields=["event", "event_team", "updated_at"])
        self.assertEqual(mover.line_seq, 3)
        row = EventSignup.objects.nocache().get(pk=mover.pk)
        self.assertEqual(row.line_seq, 3)
        self.assertEqual(row.event_id, self.other_event.pk)
        self.assertGreater(row.signed_up_at, old_signed)
        self.assertEqual(
            (row.first_signed_up_at, row.first_commitment, row.first_rsvp_class),
            old_first,
        )
        restamped = [
            e for e in logs if e["event"] == "signup_line_restamped_on_event_change"
        ]
        self.assertEqual(len(restamped), 1)
        self.assertEqual(restamped[0]["system"], "events")
        self.assertEqual(restamped[0]["subsystem"], "line")
        self.assertEqual(restamped[0]["signup_id"], mover.pk)
        self.assertEqual(restamped[0]["from_event_id"], self.event.pk)
        self.assertEqual(restamped[0]["event_id"], self.other_event.pk)
        self.assertEqual(restamped[0]["line_seq"], 3)

        back = EventSignup.objects.get(pk=mover.pk)
        back.event = self.event
        back.line_seq = 42
        with capture_logs() as logs:
            back.save()
        self.assertEqual(EventSignup.objects.nocache().get(pk=mover.pk).line_seq, 42)
        self.assertFalse(
            [e for e in logs if e["event"] == "signup_line_restamped_on_event_change"]
        )

    def test_event_change_outside_update_fields_does_not_restamp(self) -> None:
        self.signup(0, self.other_event)
        self.signup(1, self.other_event)
        mover = EventSignup.objects.get(pk=self.signup(2).pk)
        before = (mover.line_seq, mover.signed_up_at)
        mover.event = self.other_event
        mover.status = SignupStatus.TENTATIVE
        with capture_logs() as logs:
            mover.save(update_fields=["status"])
        self.assertFalse(
            [e for e in logs if e["event"] == "signup_line_restamped_on_event_change"]
        )
        row = EventSignup.objects.nocache().get(pk=mover.pk)
        self.assertEqual(row.event_id, self.event.pk)
        self.assertEqual((row.line_seq, row.signed_up_at), before)
        self.assertEqual(row.status, SignupStatus.TENTATIVE)

        with capture_logs() as logs:
            mover.save()
        row = EventSignup.objects.nocache().get(pk=mover.pk)
        self.assertEqual(row.event_id, self.other_event.pk)
        self.assertEqual(row.line_seq, 3)
        self.assertEqual(
            len(
                [
                    e
                    for e in logs
                    if e["event"] == "signup_line_restamped_on_event_change"
                ]
            ),
            1,
        )


class OrderingTests(LineTestBase):
    def test_default_ordering_and_in_line_order(self) -> None:
        a, b, c, d = (self.signup(i) for i in range(4))
        EventSignup.objects.filter(pk=a.pk).update(line_seq=3)
        EventSignup.objects.filter(pk=b.pk).update(line_seq=None)
        EventSignup.objects.filter(pk=c.pk).update(line_seq=1)
        EventSignup.objects.filter(pk=d.pk).update(line_seq=1)
        expected = [c.pk, d.pk, a.pk, b.pk]
        self.assertEqual(
            [s.pk for s in EventSignup.objects.nocache().filter(event=self.event)],
            expected,
        )
        self.assertEqual(
            [
                s.pk
                for s in EventSignup.objects.nocache()
                .filter(event=self.event)
                .order_by("-pk")
                .in_line_order()
            ],
            expected,
        )

    def test_tentative_keeps_seq_position(self) -> None:
        a = self.signup(0)
        b = self.signup(1, status=SignupStatus.TENTATIVE)
        c = self.signup(2)
        self.assertEqual(
            [s.pk for s in EventSignup.objects.filter(event=self.event)],
            [a.pk, b.pk, c.pk],
        )
        self.assertEqual(EventSignup.objects.get(pk=b.pk).commitment, "maybe")

    def test_line_order_by_keys(self) -> None:
        names = [expr.expression.name for expr in line_order_by()]
        self.assertEqual(names, ["line_seq", "pk"])
        self.assertTrue(line_order_by()[0].nulls_last)

    def test_same_gate_distance_true(self) -> None:
        self.assertTrue(same_gate_distance(self.signup(0), self.signup(1)))


class NoClassPriorityTests(LineTestBase):
    def test_no_class_priority_guard(self) -> None:
        forbidden = {"role", "member_class", "OrgUser", "rsvp_class", "commitment"}
        for fn in (line_order_by, EventSignupQuerySet.in_line_order):
            tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, forbidden)
                elif isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, forbidden)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.assertNotIn(node.value, forbidden)
        source = inspect.getsource(line)
        for needle in ("OrgUser", "member_class", ".role"):
            self.assertNotIn(needle, source)


class OldColumnInsertTests(LineTestBase):
    def test_old_column_insert_succeeds(self) -> None:
        now = tz.now().isoformat()
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO events_eventsignup "
                "(event_id, user_id, signup_type, status, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                [self.event.pk, self.players[0].pk, "user", "rsvp", now, now],
            )
        row = EventSignup.objects.nocache().get(event=self.event, user=self.players[0])
        self.assertIsNone(row.line_seq)
        self.assertEqual(row.commitment, "main")
        self.assertEqual(row.first_commitment, "main")
        self.assertEqual(row.rsvp_class, "standard")
        self.assertIsNotNone(row.first_signed_up_at)
        self.assertIsNotNone(row.signed_up_at)


class InsertStampAtomicTests(TransactionTestCase):
    def test_insert_stamp_runs_in_atomic(self) -> None:
        owner = CustomUser.objects.create_user(username="line_atomic_owner")
        org = Organization.objects.create(name="Line Atomic Org", owner=owner)
        event = Event.objects.create(
            organization=org,
            name="Line Atomic Event",
            scheduled_at=tz.now() + timedelta(days=3),
            state=EventState.SIGNUPS_OPEN,
        )
        seen: list[bool] = []
        real = line.next_line_seq

        def recording(e: Event) -> int:
            seen.append(connection.in_atomic_block)
            return real(e)

        self.assertFalse(connection.in_atomic_block)
        with mock.patch("events.line.next_line_seq", side_effect=recording):
            EventSignup.objects.create(event=event, user=owner)
        self.assertEqual(seen, [True])


class LineMutatorTests(LineTestBase):
    def test_restore_place_sets_fields(self) -> None:
        s = self.signup(0)
        before_first = (s.first_signed_up_at, s.first_commitment, s.first_rsvp_class)
        at = tz.now() - timedelta(days=2)
        snap = SignupSnapshot(
            status=SignupStatus.WAITLISTED,
            commitment=Commitment.MAYBE,
            rsvp_class=RsvpClass.STANDARD,
            signed_up_at=at,
            line_seq=7,
            waitlist_position=2,
        )
        with (
            mock.patch("events.line.invalidate_after_commit") as inv,
            capture_logs() as logs,
            self.captureOnCommitCallbacks(execute=True),
        ):
            restore_place(s, snap)
        inv.assert_called_once_with(s.event)
        row = EventSignup.objects.nocache().get(pk=s.pk)
        self.assertEqual(row.status, SignupStatus.WAITLISTED)
        self.assertEqual(row.commitment, Commitment.MAYBE)
        self.assertEqual(row.rsvp_class, RsvpClass.STANDARD)
        self.assertEqual(row.signed_up_at, at)
        self.assertEqual(row.line_seq, 7)
        self.assertEqual(row.waitlist_position, 2)
        self.assertEqual(
            (row.first_signed_up_at, row.first_commitment, row.first_rsvp_class),
            before_first,
        )
        restored = [e for e in logs if e["event"] == "signup_line_place_restored"]
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["system"], "events")
        self.assertEqual(restored[0]["subsystem"], "line")
        self.assertEqual(restored[0]["signup_id"], s.pk)
        self.assertEqual(restored[0]["event_id"], self.event.pk)
        self.assertEqual(restored[0]["line_seq"], 7)

    def test_restore_place_logs_only_on_commit(self) -> None:
        s = self.signup(0)
        snap = SignupSnapshot(
            status=SignupStatus.WAITLISTED,
            commitment=s.commitment,
            rsvp_class=s.rsvp_class,
            signed_up_at=s.signed_up_at,
            line_seq=s.line_seq,
        )
        with capture_logs() as logs, self.captureOnCommitCallbacks() as callbacks:
            restore_place(s, snap)
            self.assertFalse(
                [e for e in logs if e["event"] == "signup_line_place_restored"]
            )
        self.assertTrue(callbacks)

    def test_restore_place_saves_only_changed_fields(self) -> None:
        s = self.signup(0)
        snap = SignupSnapshot(
            status=SignupStatus.WAITLISTED,
            commitment=s.commitment,
            rsvp_class=s.rsvp_class,
            signed_up_at=s.signed_up_at,
            line_seq=s.line_seq,
            waitlist_position=s.waitlist_position,
        )
        with mock.patch.object(EventSignup, "save", autospec=True) as save:
            restore_place(s, snap)
        save.assert_called_once()
        self.assertEqual(
            sorted(save.call_args.kwargs["update_fields"]), ["status", "updated_at"]
        )

    def test_restore_place_with_reused_seq(self) -> None:
        gone = self.signup(0)
        gone_snap = SignupSnapshot(
            status=gone.status,
            commitment=gone.commitment,
            rsvp_class=gone.rsvp_class,
            signed_up_at=gone.signed_up_at,
            line_seq=gone.line_seq,
            waitlist_position=gone.waitlist_position,
        )
        gone.delete()
        other = self.signup(1)
        self.assertEqual(other.line_seq, gone_snap.line_seq)
        target = self.signup(0)
        other_before = EventSignup.objects.nocache().get(pk=other.pk)
        with self.captureOnCommitCallbacks(execute=True):
            restore_place(EventSignup.objects.get(pk=target.pk), gone_snap)
        target_row = EventSignup.objects.nocache().get(pk=target.pk)
        other_row = EventSignup.objects.nocache().get(pk=other.pk)
        self.assertEqual(target_row.line_seq, gone_snap.line_seq)
        self.assertEqual(target_row.signed_up_at, gone_snap.signed_up_at)
        self.assertEqual(other_row.line_seq, other_before.line_seq)
        self.assertEqual(other_row.signed_up_at, other_before.signed_up_at)
        self.assertEqual(other_row.updated_at, other_before.updated_at)

    def test_swap_places_swaps_line_fields_only(self) -> None:
        a = self.signup(0, status=SignupStatus.RSVP)
        b = self.signup(1, status=SignupStatus.WAITLISTED, waitlist_position=1)
        a_seq, a_at = a.line_seq, a.signed_up_at
        b_seq, b_at = b.line_seq, b.signed_up_at
        self.assertEqual((a_seq, b_seq), (1, 2))
        with (
            mock.patch("events.line.invalidate_after_commit") as inv,
            capture_logs() as logs,
            self.captureOnCommitCallbacks(execute=True),
        ):
            swap_places(a, b)
        inv.assert_called_once_with(a.event)
        a_row = EventSignup.objects.nocache().get(pk=a.pk)
        b_row = EventSignup.objects.nocache().get(pk=b.pk)
        self.assertEqual((a_row.line_seq, a_row.signed_up_at), (b_seq, b_at))
        self.assertEqual((b_row.line_seq, b_row.signed_up_at), (a_seq, a_at))
        self.assertEqual(a_row.status, SignupStatus.RSVP)
        self.assertEqual(b_row.status, SignupStatus.WAITLISTED)
        self.assertIsNone(a_row.waitlist_position)
        self.assertEqual(b_row.waitlist_position, 1)
        swapped = [e for e in logs if e["event"] == "signup_line_places_swapped"]
        self.assertEqual(len(swapped), 1)
        self.assertEqual(swapped[0]["system"], "events")
        self.assertEqual(swapped[0]["subsystem"], "line")
        self.assertEqual(swapped[0]["event_id"], self.event.pk)
        self.assertEqual(swapped[0]["signup_ids"], [a.pk, b.pk])
        self.assertEqual(swapped[0]["line_seqs"], [b_seq, a_seq])

    def test_swap_places_other_event_raises(self) -> None:
        a = self.signup(0)
        b = self.signup(1, event=self.other_event)
        with (
            mock.patch("events.line.invalidate_after_commit") as inv,
            capture_logs() as logs,
            self.captureOnCommitCallbacks(execute=True),
            self.assertRaises(ValueError),
        ):
            swap_places(a, b)
        inv.assert_not_called()
        self.assertFalse(
            [e for e in logs if e["event"] == "signup_line_places_swapped"]
        )
        for s in (a, b):
            row = EventSignup.objects.nocache().get(pk=s.pk)
            self.assertEqual(
                (row.line_seq, row.signed_up_at), (s.line_seq, s.signed_up_at)
            )
        self.assertEqual((a.line_seq, b.line_seq), (1, 1))

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone as tz

from app.models import CustomUser
from events.constants import EventState, SignupAction, SignupStatus
from events.ledger import (
    ActorRole,
    SignupActor,
    SignupMeans,
    record_signup_change,
    snapshot,
)
from events.merge import merge_user_signups
from events.models import Event, EventSignup, SignupLedgerEntry
from org.models import Organization


class MergeUserSignupsTests(TestCase):
    def setUp(self) -> None:
        self.admin = CustomUser.objects.create(username="mus_admin")
        self.org = Organization.objects.create(name="Merge Org", owner=self.admin)
        self.keep = CustomUser.objects.create(username="mus_keep")
        self.drop = CustomUser.objects.create(username="mus_drop")
        self.actor = SignupActor(
            user=self.admin,
            role=ActorRole.STAFF,
            means=SignupMeans.WEB,
            correlation_id="claim-abc",
        )

    def _event(self, name: str) -> Event:
        return Event.objects.create(
            organization=self.org,
            name=name,
            scheduled_at=tz.now() + timedelta(days=3),
            state=EventState.SIGNUPS_OPEN,
            created_by=self.admin,
        )

    def _entries(self, event: Event) -> list[SignupLedgerEntry]:
        return list(
            SignupLedgerEntry.objects.filter(
                event=event, action=SignupAction.ACCOUNT_MERGED
            ).order_by("pk")
        )

    def test_moves_row_and_records_account_merged(self) -> None:
        event = self._event("A")
        row = EventSignup.objects.create(
            event=event, user=self.drop, status=SignupStatus.APPROVED
        )

        written = merge_user_signups(self.drop, self.keep, actor=self.actor)

        self.assertEqual(written, 1)
        row.refresh_from_db()
        self.assertEqual(row.user_id, self.keep.pk)
        [entry] = self._entries(event)
        self.assertEqual(entry.signup_id, row.pk)
        self.assertEqual(entry.subject_user_id, self.keep.pk)
        self.assertEqual(entry.actor_user_id, self.admin.pk)
        self.assertEqual(entry.actor_role, ActorRole.STAFF)
        self.assertEqual(entry.means, SignupMeans.WEB)
        self.assertEqual(entry.correlation_id, "claim-abc")
        self.assertTrue(entry.on_behalf)
        self.assertIsNone(entry.caused_by_id)
        self.assertEqual(entry.before["status"], SignupStatus.APPROVED)
        self.assertEqual(entry.after["status"], SignupStatus.APPROVED)
        self.assertEqual(entry.before["extra"], {"from_user_id": self.drop.pk})
        self.assertEqual(entry.after["extra"], {"from_user_id": self.drop.pk})

    def test_conflict_records_discarded_duplicate_against_keep_row(self) -> None:
        event = self._event("B")
        keep_row = EventSignup.objects.create(
            event=event, user=self.keep, status=SignupStatus.APPROVED
        )
        drop_row = EventSignup.objects.create(
            event=event, user=self.drop, status=SignupStatus.CANCELLED
        )
        drop_row_pk = drop_row.pk

        written = merge_user_signups(self.drop, self.keep, actor=self.actor)

        self.assertEqual(written, 1)
        self.assertFalse(EventSignup.objects.filter(pk=drop_row_pk).exists())
        [entry] = self._entries(event)
        self.assertEqual(entry.signup_id, keep_row.pk)
        self.assertEqual(entry.subject_user_id, self.keep.pk)
        self.assertEqual(entry.before["status"], SignupStatus.CANCELLED)
        self.assertEqual(
            entry.before["extra"],
            {
                "from_user_id": self.drop.pk,
                "discarded_signup_id": drop_row_pk,
                "discarded_duplicate": True,
            },
        )
        self.assertEqual(entry.after["status"], SignupStatus.APPROVED)
        self.assertEqual(entry.after["extra"], {})
        latest = (
            SignupLedgerEntry.objects.filter(event=event, subject_user=self.keep)
            .order_by("-pk")
            .first()
        )
        self.assertEqual(latest.after["status"], keep_row.status)

    def test_moves_and_conflicts_across_events(self) -> None:
        moved_event = self._event("A")
        conflict_event = self._event("B")
        EventSignup.objects.create(event=moved_event, user=self.drop)
        EventSignup.objects.create(event=conflict_event, user=self.keep)
        EventSignup.objects.create(event=conflict_event, user=self.drop)

        written = merge_user_signups(self.drop, self.keep, actor=self.actor)

        self.assertEqual(written, 2)
        self.assertFalse(EventSignup.objects.filter(user=self.drop).exists())
        self.assertEqual(
            EventSignup.objects.filter(user=self.keep).count(),
            2,
        )
        self.assertEqual(len(self._entries(moved_event)), 1)
        self.assertEqual(len(self._entries(conflict_event)), 1)

    def test_repoints_earlier_ledger_rows(self) -> None:
        event = self._event("A")
        row = EventSignup.objects.create(event=event, user=self.drop)
        as_subject = record_signup_change(
            event=event,
            subject=self.drop,
            actor=SignupActor.system(),
            action=SignupAction.SIGNED_UP,
            signup=row,
            after=snapshot(row),
        )
        other = CustomUser.objects.create(username="mus_other")
        as_actor = record_signup_change(
            event=event,
            subject=other,
            actor=SignupActor(
                user=self.drop, role=ActorRole.STAFF, means=SignupMeans.WEB
            ),
            action=SignupAction.STAFF_ADDED,
        )

        merge_user_signups(self.drop, self.keep, actor=self.actor)

        as_subject.refresh_from_db()
        as_actor.refresh_from_db()
        self.assertEqual(as_subject.subject_user_id, self.keep.pk)
        self.assertEqual(as_actor.actor_user_id, self.keep.pk)
        self.assertEqual(as_actor.subject_user_id, other.pk)
        self.assertFalse(
            SignupLedgerEntry.objects.filter(subject_user=self.drop).exists()
        )
        self.assertFalse(
            SignupLedgerEntry.objects.filter(actor_user=self.drop).exists()
        )

    def test_discarded_seated_duplicate_promotes_from_waitlist(self) -> None:
        event = self._event("Full")
        event.max_players = 2
        event.save(update_fields=["max_players"])
        EventSignup.objects.create(
            event=event, user=self.keep, status=SignupStatus.APPROVED
        )
        EventSignup.objects.create(
            event=event, user=self.drop, status=SignupStatus.APPROVED
        )
        waiting = EventSignup.objects.create(
            event=event,
            user=CustomUser.objects.create(username="mus_waiting"),
            status=SignupStatus.WAITLISTED,
            waitlist_position=1,
        )

        written = merge_user_signups(self.drop, self.keep, actor=self.actor)

        self.assertEqual(written, 1)
        entries = list(
            SignupLedgerEntry.objects.filter(event=event)
            .exclude(action=SignupAction.BACKFILLED)
            .order_by("pk")
        )
        self.assertEqual(
            [e.action for e in entries],
            [SignupAction.ACCOUNT_MERGED, SignupAction.PROMOTED],
        )
        merged, promoted = entries
        self.assertEqual(promoted.caused_by_id, merged.pk)
        self.assertEqual(promoted.correlation_id, "claim-abc")
        self.assertEqual(promoted.signup_id, waiting.pk)
        waiting.refresh_from_db()
        self.assertNotEqual(waiting.status, SignupStatus.WAITLISTED)

    def test_discarded_unseated_duplicate_promotes_nobody(self) -> None:
        event = self._event("Full")
        event.max_players = 1
        event.save(update_fields=["max_players"])
        EventSignup.objects.create(
            event=event, user=self.keep, status=SignupStatus.APPROVED
        )
        EventSignup.objects.create(
            event=event,
            user=self.drop,
            status=SignupStatus.WAITLISTED,
            waitlist_position=1,
        )
        waiting = EventSignup.objects.create(
            event=event,
            user=CustomUser.objects.create(username="mus_waiting"),
            status=SignupStatus.WAITLISTED,
            waitlist_position=2,
        )

        merge_user_signups(self.drop, self.keep, actor=self.actor)

        waiting.refresh_from_db()
        self.assertEqual(waiting.status, SignupStatus.WAITLISTED)
        self.assertFalse(
            SignupLedgerEntry.objects.filter(
                event=event, action=SignupAction.PROMOTED
            ).exists()
        )

    def test_zero_signups_writes_nothing(self) -> None:
        count = SignupLedgerEntry.objects.count()

        written = merge_user_signups(self.drop, self.keep, actor=self.actor)

        self.assertEqual(written, 0)
        self.assertEqual(SignupLedgerEntry.objects.count(), count)

    def test_keep_rows_on_other_events_untouched(self) -> None:
        event = self._event("A")
        keep_row = EventSignup.objects.create(event=event, user=self.keep)

        written = merge_user_signups(self.drop, self.keep, actor=self.actor)

        self.assertEqual(written, 0)
        keep_row.refresh_from_db()
        self.assertEqual(keep_row.user_id, self.keep.pk)
        self.assertEqual(self._entries(event), [])

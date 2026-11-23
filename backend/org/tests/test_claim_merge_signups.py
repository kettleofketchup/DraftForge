from django.test import TestCase
from django.utils import timezone

from events.constants import EventState, SignupAction, SignupStatus
from events.ledger import (
    ActorRole,
    SignupActor,
    SignupMeans,
    record_signup_change,
    snapshot,
)
from events.models import Event, EventSignup, SignupLedgerEntry
from org.tests.test_claim_merge_game_mmrs import ClaimFixtures


class ClaimMergeSignupsTests(ClaimFixtures, TestCase):
    def setUp(self) -> None:
        self.build()

    def _event(self, name: str) -> Event:
        return Event.objects.create(
            name=name,
            organization=self.org,
            scheduled_at=timezone.now() + timezone.timedelta(days=2),
            state=EventState.SIGNUPS_OPEN,
            created_by=self.admin,
        )

    def _merged(self, event: Event) -> SignupLedgerEntry:
        return SignupLedgerEntry.objects.get(
            event=event, action=SignupAction.ACCOUNT_MERGED
        )

    def test_claim_moves_target_signup_and_records_staff_entry(self) -> None:
        event = self._event("Claim Night")
        signup = EventSignup.objects.create(
            event=event, user=self.target, status=SignupStatus.APPROVED
        )
        target_pk = self.target.pk

        self.assertEqual(self.approve(), 200)

        moved = EventSignup.objects.nocache().get(pk=signup.pk)
        self.assertEqual(moved.user_id, self.claimer.pk)
        entry = self._merged(event)
        self.assertEqual(entry.signup_id, signup.pk)
        self.assertEqual(entry.subject_user_id, self.claimer.pk)
        self.assertEqual(entry.actor_user_id, self.admin.pk)
        self.assertEqual(entry.actor_role, ActorRole.STAFF)
        self.assertEqual(entry.means, SignupMeans.WEB)
        self.assertTrue(entry.on_behalf)
        self.assertRegex(entry.correlation_id, r"^claim-[0-9a-f]{12}$")
        self.assertEqual(entry.before["extra"], {"from_user_id": target_pk})
        self.assertEqual(entry.after["status"], SignupStatus.APPROVED)

    def test_claim_repoints_target_ledger_rows(self) -> None:
        event = self._event("Claim History")
        signup = EventSignup.objects.create(event=event, user=self.target)
        earlier = record_signup_change(
            event=event,
            subject=self.target,
            actor=SignupActor.system(),
            action=SignupAction.SIGNED_UP,
            signup=signup,
            after=snapshot(signup),
        )

        self.assertEqual(self.approve(), 200)

        earlier.refresh_from_db()
        self.assertEqual(earlier.subject_user_id, self.claimer.pk)

    def test_claim_conflict_records_discarded_duplicate(self) -> None:
        event = self._event("Claim Clash")
        keep_row = EventSignup.objects.create(
            event=event, user=self.claimer, status=SignupStatus.APPROVED
        )
        drop_row = EventSignup.objects.create(
            event=event, user=self.target, status=SignupStatus.CANCELLED
        )
        drop_row_pk = drop_row.pk

        self.assertEqual(self.approve(), 200)

        self.assertFalse(EventSignup.objects.filter(pk=drop_row_pk).exists())
        entry = self._merged(event)
        self.assertEqual(entry.signup_id, keep_row.pk)
        self.assertEqual(entry.before["extra"]["discarded_signup_id"], drop_row_pk)
        self.assertIs(entry.before["extra"]["discarded_duplicate"], True)
        self.assertEqual(entry.after["status"], SignupStatus.APPROVED)

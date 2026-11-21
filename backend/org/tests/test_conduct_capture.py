from datetime import datetime, timedelta

from django.db import transaction
from django.urls import reverse
from django.utils import timezone as tz
from rest_framework.test import APIClient

from app.models import CustomUser
from discordbot.models import DiscordMessageLog
from events.constants import ActorRole, EventState, SignupMeans, SignupStatus
from events.discord import handle_decline_button, handle_reaction_cancel
from events.ledger import SignupActor
from events.models import Event, EventSignup
from events.services import cancel_signup, create_tentative_signup
from org.conduct.capture import capture_late_cancel
from org.conduct.constants import Outcome, OutcomeSource
from org.models import OrgUser
from org.models_conduct import AttendanceOutcome, OrgConductSettings
from org.tests.conduct_base import ConductTestCase


class CaptureLateCancelTest(ConductTestCase):
    def setUp(self) -> None:
        self.now = tz.now()
        self.member = self.make_user()

    def _event(
        self, *, starts_in: timedelta = timedelta(hours=1), **kw: object
    ) -> Event:
        return self.make_event(scheduled_at=self.now + starts_in, **kw)

    def _capture(
        self, signup: EventSignup, prior_status: str, now: datetime | None = None
    ) -> AttendanceOutcome | None:
        with transaction.atomic():
            return capture_late_cancel(
                signup, prior_status=prior_status, now=now or self.now
            )

    def _cancelled(self, event: Event, user: CustomUser | None = None) -> EventSignup:
        return self.signup(event, user or self.member, SignupStatus.CANCELLED)

    def test_inside_window_is_late_cancel(self) -> None:
        self.unlock()
        event = self._event()
        row = self._capture(self._cancelled(event), SignupStatus.APPROVED)
        assert row is not None
        row.refresh_from_db()
        self.assertEqual(row.outcome, Outcome.LATE_CANCEL)
        self.assertEqual(row.source, OutcomeSource.LATE_CANCEL)
        self.assertEqual(row.cancelled_at, self.now)
        self.assertEqual(row.event_starts_at, event.scheduled_at)
        self.assertEqual(row.event_name, event.name)
        self.assertTrue(row.committed)
        self.assertEqual(row.organization_id, self.org.pk)

    def test_outside_window_ignored(self) -> None:
        self.unlock()
        event = self._event(starts_in=timedelta(hours=3))
        self.assertIsNone(self._capture(self._cancelled(event), SignupStatus.APPROVED))
        self.assertFalse(AttendanceOutcome.objects.nocache().exists())

    def test_after_start_is_no_show(self) -> None:
        self.unlock()
        event = self._event(
            starts_in=-timedelta(minutes=10), state=EventState.IN_PROGRESS
        )
        row = self._capture(self._cancelled(event), SignupStatus.CONFIRMED)
        assert row is not None
        self.assertEqual(row.outcome, Outcome.NO_SHOW)
        self.assertEqual(row.source, OutcomeSource.LATE_CANCEL)

    def test_after_start_captured_with_zero_hours(self) -> None:
        self.unlock()
        OrgConductSettings.objects.create(organization=self.org, late_cancel_hours=0)
        started = self._event(
            starts_in=-timedelta(minutes=10), state=EventState.IN_PROGRESS
        )
        row = self._capture(self._cancelled(started), SignupStatus.APPROVED)
        assert row is not None
        self.assertEqual(row.outcome, Outcome.NO_SHOW)
        upcoming = self._event()
        self.assertIsNone(
            self._capture(self._cancelled(upcoming), SignupStatus.APPROVED)
        )

    def test_waitlisted_prior_not_counted(self) -> None:
        self.unlock()
        event = self._event()
        self.assertIsNone(
            self._capture(self._cancelled(event), SignupStatus.WAITLISTED)
        )
        self.assertFalse(AttendanceOutcome.objects.nocache().exists())

    def test_rsvp_counts_only_on_manual_approval(self) -> None:
        self.unlock()
        auto = self._event(auto_approve=True)
        self.assertIsNone(self._capture(self._cancelled(auto), SignupStatus.RSVP))
        manual = self._event(auto_approve=False)
        row = self._capture(self._cancelled(manual), SignupStatus.RSVP)
        assert row is not None
        self.assertEqual(row.outcome, Outcome.LATE_CANCEL)

    def test_feature_locked_noop(self) -> None:
        event = self._event()
        self.assertIsNone(self._capture(self._cancelled(event), SignupStatus.APPROVED))
        self.assertFalse(AttendanceOutcome.objects.nocache().exists())

    def test_completed_or_finalized_noop(self) -> None:
        self.unlock()
        completed = self._event(
            starts_in=-timedelta(minutes=10), state=EventState.COMPLETED
        )
        self.assertIsNone(
            self._capture(self._cancelled(completed), SignupStatus.APPROVED)
        )
        finalized = self._event(
            starts_in=-timedelta(minutes=10),
            state=EventState.IN_PROGRESS,
            conduct_finalized_at=self.now,
        )
        self.assertIsNone(
            self._capture(self._cancelled(finalized), SignupStatus.APPROVED)
        )
        self.assertFalse(AttendanceOutcome.objects.nocache().exists())

    def test_existing_staff_row_untouched(self) -> None:
        self.unlock()
        event = self._event()
        staff_row = self.outcome(
            self.member,
            event=event,
            outcome=Outcome.ATTENDED,
            source=OutcomeSource.STAFF,
            finalized=False,
            reason="Marked by staff",
        )
        self.assertIsNone(self._capture(self._cancelled(event), SignupStatus.APPROVED))
        staff_row.refresh_from_db()
        self.assertEqual(staff_row.outcome, Outcome.ATTENDED)
        self.assertEqual(staff_row.source, OutcomeSource.STAFF)
        self.assertIsNone(staff_row.cancelled_at)

    def test_existing_finalized_row_untouched(self) -> None:
        self.unlock()
        event = self._event()
        row = self.outcome(self.member, event=event, outcome=Outcome.ATTENDED)
        self.assertIsNone(self._capture(self._cancelled(event), SignupStatus.APPROVED))
        row.refresh_from_db()
        self.assertEqual(row.outcome, Outcome.ATTENDED)

    def test_existing_automatic_row_replaced(self) -> None:
        self.unlock()
        event = self._event()
        self.outcome(
            self.member,
            event=event,
            outcome=Outcome.PENDING,
            source=OutcomeSource.READY_CHECK,
            finalized=False,
        )
        row = self._capture(self._cancelled(event), SignupStatus.APPROVED)
        assert row is not None
        self.assertEqual(row.outcome, Outcome.LATE_CANCEL)
        self.assertEqual(row.source, OutcomeSource.LATE_CANCEL)
        self.assertEqual(
            AttendanceOutcome.objects.nocache().filter(event=event).count(), 1
        )

    def test_stale_event_instance_sees_finalized_state(self) -> None:
        self.unlock()
        event = self._event()
        signup = self._cancelled(event)
        stale = Event.objects.nocache().get(pk=event.pk)
        Event.objects.filter(pk=event.pk).update(
            conduct_finalized_at=self.now, state=EventState.COMPLETED
        )
        signup.event = stale
        self.assertEqual(stale.state, EventState.SIGNUPS_OPEN)
        self.assertIsNone(self._capture(signup, SignupStatus.APPROVED))
        self.assertFalse(AttendanceOutcome.objects.nocache().exists())

    def test_capture_creates_missing_org_user(self) -> None:
        self.unlock()
        user = CustomUser.objects.create_user(
            username="conduct_no_org_user", password="testpass"
        )
        OrgUser.objects.filter(user=user, organization=self.org).delete()
        event = self._event()
        row = self._capture(self._cancelled(event, user), SignupStatus.APPROVED)
        assert row is not None
        org_user = OrgUser.objects.nocache().get(user=user, organization=self.org)
        self.assertEqual(row.org_user_id, org_user.pk)


class CaptureWiringTest(ConductTestCase):
    def setUp(self) -> None:
        self.unlock()
        self.client = APIClient()
        self.member = self.make_user()
        self.member.discordId = "555000111222333444"
        self.member.save()
        self.event = self.make_event(scheduled_at=tz.now() + timedelta(hours=1))

    def _rows(self) -> int:
        return AttendanceOutcome.objects.nocache().filter(event=self.event).count()

    def _web_cancel(self, actor: CustomUser, signup: EventSignup) -> None:
        self.client.force_authenticate(actor)
        response = self.client.post(
            reverse("event-signup-cancel-signup", args=[signup.pk])
        )
        self.assertEqual(response.status_code, 200, response.content)

    def _member_actor(self) -> SignupActor:
        return SignupActor(
            user=self.member, role=ActorRole.MEMBER, means=SignupMeans.WEB
        )

    def test_member_web_cancel_captures(self) -> None:
        signup = self.signup(self.event, self.member, SignupStatus.APPROVED)
        self._web_cancel(self.member, signup)
        row = AttendanceOutcome.objects.nocache().get(event=self.event)
        self.assertEqual(row.outcome, Outcome.LATE_CANCEL)
        self.assertEqual(row.source, OutcomeSource.LATE_CANCEL)

    def test_staff_web_cancel_does_not_capture(self) -> None:
        signup = self.signup(self.event, self.member, SignupStatus.APPROVED)
        self._web_cancel(self.admin, signup)
        self.assertEqual(self._rows(), 0)

    def test_staff_cancelling_own_signup_captures(self) -> None:
        signup = self.signup(self.event, self.admin, SignupStatus.APPROVED)
        self._web_cancel(self.admin, signup)
        row = AttendanceOutcome.objects.nocache().get(event=self.event)
        self.assertEqual(row.org_user.user_id, self.admin.pk)

    def test_discord_decline_captures(self) -> None:
        self.signup(self.event, self.member, SignupStatus.APPROVED)
        result = handle_decline_button(self.event.pk, self.member.discordId)
        self.assertEqual(result["action"], "declined")
        row = AttendanceOutcome.objects.nocache().get(event=self.event)
        self.assertEqual(row.outcome, Outcome.LATE_CANCEL)

    def _reaction_message(self) -> str:
        DiscordMessageLog.objects.create(
            channel_id="1482767177063858216",
            embed_data={"title": "Test"},
            source="event_announcement",
            source_id=self.event.pk,
            discord_message_id="777666555",
            success=True,
        )
        return "777666555"

    def test_reaction_removal_captures(self) -> None:
        message_id = self._reaction_message()
        self.signup(self.event, self.member, SignupStatus.APPROVED)
        success, detail = handle_reaction_cancel(message_id, self.member.discordId)
        self.assertTrue(success, detail)
        row = AttendanceOutcome.objects.nocache().get(event=self.event)
        self.assertEqual(row.outcome, Outcome.LATE_CANCEL)

    def test_reaction_removal_on_completed_event_noop(self) -> None:
        message_id = self._reaction_message()
        Event.objects.filter(pk=self.event.pk).update(
            state=EventState.COMPLETED, conduct_finalized_at=tz.now()
        )
        self.signup(self.event, self.member, SignupStatus.APPROVED)
        before = self.outcome(self.member, event=self.event)
        handle_reaction_cancel(message_id, self.member.discordId)
        after = AttendanceOutcome.objects.nocache().get(pk=before.pk)
        self.assertEqual(after.outcome, Outcome.ATTENDED)
        self.assertEqual(after.updated_at, before.updated_at)
        self.assertEqual(self._rows(), 1)

    def test_member_cancel_after_completed_and_finalized_noop(self) -> None:
        Event.objects.filter(pk=self.event.pk).update(
            state=EventState.COMPLETED, conduct_finalized_at=tz.now()
        )
        signup = self.signup(self.event, self.member, SignupStatus.APPROVED)
        before = self.outcome(self.member, event=self.event)
        self._web_cancel(self.member, signup)
        after = AttendanceOutcome.objects.nocache().get(pk=before.pk)
        self.assertEqual(after.outcome, Outcome.ATTENDED)
        self.assertEqual(after.updated_at, before.updated_at)

    def test_cancel_after_staff_cancel_creates_no_row(self) -> None:
        Event.objects.filter(pk=self.event.pk).update(state=EventState.CANCELLED)
        signup = self.signup(self.event, self.member, SignupStatus.APPROVED)
        with transaction.atomic():
            cancel_signup(signup, actor=self._member_actor())
        self.assertEqual(self._rows(), 0)

    def test_tentative_switch_captures_once(self) -> None:
        self.signup(self.event, self.member, SignupStatus.APPROVED)
        create_tentative_signup(self.event, self.member, actor=self._member_actor())
        self.assertEqual(AttendanceOutcome.objects.nocache().count(), 1)
        row = AttendanceOutcome.objects.nocache().get(event=self.event)
        self.assertEqual(row.outcome, Outcome.LATE_CANCEL)
        self.assertEqual(
            EventSignup.objects.get(event=self.event, user=self.member).status,
            SignupStatus.TENTATIVE,
        )

    def test_tentative_from_waitlist_no_capture(self) -> None:
        self.signup(self.event, self.member, SignupStatus.WAITLISTED)
        create_tentative_signup(self.event, self.member, actor=self._member_actor())
        self.assertEqual(self._rows(), 0)

from datetime import time, timedelta

from django.contrib.admin.sites import site as admin_site
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory
from django.utils import timezone as tz

from app.models import CustomUser
from events.constants import RepeatFrequency, SignupStatus
from events.models import (
    Event,
    EventRepeater,
    EventSignup,
    EventVoicePresence,
    OrgEventDefaults,
    ReadyCheck,
    ReadyCheckEntry,
    RollCallMode,
)
from events.ready_check_constants import (
    REMOVED_SIGNUP_STATUSES,
    PostCullFillMode,
    ReadyCheckLowCompletionAction,
    ReadyCheckPhase,
    ReadyCheckScope,
)
from events.tests.base import EventTestCase

EXPECTED_DEFAULTS: dict[str, object] = {
    "roll_call_enabled": False,
    "roll_call_mode": RollCallMode.MANUAL,
    "auto_confirm": False,
    "ready_check_scope": ReadyCheckScope.MAIN_ONLY,
    "ready_check_open_minutes": 120,
    "ready_check_escalation_minutes": 30,
    "ready_check_close_minutes": 10,
    "ready_check_chase_minutes": 30,
    "ready_check_min_completion_pct": 70,
    "ready_check_low_completion_action": ReadyCheckLowCompletionAction.NON_BINDING,
    "ready_check_notify_on_signup": True,
    "ready_check_drop_notice": True,
    "start_cull_enabled": False,
    "start_cull_minutes_after": 1,
    "post_cull_fill_mode": PostCullFillMode.LINE_ORDER,
    "event_voice_channel_id": "",
    "voice_presence_confirms": False,
}


class ReadyCheckModelTests(EventTestCase):
    def _event(self, name: str = "RC Event") -> Event:
        return Event.objects.create(
            organization=self.org,
            name=name,
            scheduled_at=tz.now() + timedelta(days=1),
        )

    def _signup(self, event: Event, user: CustomUser | None = None) -> EventSignup:
        return EventSignup.objects.create(
            event=event, user=user or self.user, status=SignupStatus.APPROVED
        )

    def test_defaults_on_all_config_models(self) -> None:
        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Weekly",
            frequency=RepeatFrequency.DAILY,
            time_of_day=time(20, 0),
            timezone="UTC",
            starts_at=tz.now().date() + timedelta(days=30),
            created_by=self.admin,
        )
        defaults = OrgEventDefaults.objects.create(organization=self.org)
        event = self._event()
        for row in (repeater, defaults, event):
            row.refresh_from_db()
        rows = {"event": event, "series": repeater, "defaults": defaults}
        for label, row in rows.items():
            for field, expected in EXPECTED_DEFAULTS.items():
                with self.subTest(target=label, field=field):
                    self.assertEqual(getattr(row, field), expected)

    def test_roll_call_mode_labels(self) -> None:
        self.assertEqual(RollCallMode.MANUAL, "manual")
        self.assertEqual(RollCallMode.MANUAL.label, "Staff-verified")
        self.assertEqual(RollCallMode.AUTOMATIC, "automatic")

    def test_removed_signup_statuses(self) -> None:
        self.assertEqual(REMOVED_SIGNUP_STATUSES, ("cancelled", "rejected", "dropped"))
        self.assertEqual(SignupStatus.DROPPED, "dropped")

    def test_second_live_check_rejected(self) -> None:
        event = self._event()
        ReadyCheck.objects.create(event=event)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReadyCheck.objects.create(event=event)

    def test_new_check_allowed_after_cancel(self) -> None:
        event = self._event()
        ReadyCheck.objects.create(event=event, phase=ReadyCheckPhase.CANCELLED)
        ReadyCheck.objects.create(event=event)
        self.assertEqual(event.ready_checks.count(), 2)

        closed_event = self._event("Closed")
        ReadyCheck.objects.create(event=closed_event, phase=ReadyCheckPhase.CLOSED)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReadyCheck.objects.create(event=closed_event)

    def test_entry_unique_per_signup_and_user(self) -> None:
        event = self._event()
        rc = ReadyCheck.objects.create(event=event)
        signup = self._signup(event)
        ReadyCheckEntry.objects.create(ready_check=rc, signup=signup, user=self.user)

        with self.assertRaises(IntegrityError), transaction.atomic():
            ReadyCheckEntry.objects.create(
                ready_check=rc, signup=signup, user=self.admin
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReadyCheckEntry.objects.create(ready_check=rc, signup=None, user=self.user)

        ReadyCheckEntry.objects.create(ready_check=rc, signup=None, user=self.admin)
        ReadyCheckEntry.objects.create(
            ready_check=rc, signup=None, user=self.unrelated_user
        )
        self.assertEqual(rc.entries.filter(signup__isnull=True).count(), 2)

    def test_for_signup_derives_user(self) -> None:
        event = self._event()
        rc = ReadyCheck.objects.create(event=event)
        signup = self._signup(event)
        entry = ReadyCheckEntry.for_signup(rc, signup)
        self.assertEqual(entry.user_id, signup.user_id)
        self.assertEqual(entry.signup_id, signup.pk)
        self.assertIsNone(entry.pk)

    def test_clean_rejects_mismatch(self) -> None:
        event = self._event()
        rc = ReadyCheck.objects.create(event=event)
        signup = self._signup(event)

        wrong_user = ReadyCheckEntry(ready_check=rc, signup=signup, user=self.admin)
        with self.assertRaises(ValidationError):
            wrong_user.full_clean()

        other_signup = self._signup(self._event("Other"))
        wrong_event = ReadyCheckEntry(
            ready_check=rc, signup=other_signup, user=self.user
        )
        with self.assertRaises(ValidationError):
            wrong_event.full_clean()

        ReadyCheckEntry.for_signup(rc, signup).full_clean()

    def test_clean_without_ready_check_raises_validation_error(self) -> None:
        signup = self._signup(self._event())
        entry = ReadyCheckEntry(signup=signup, user=self.user)
        with self.assertRaises(ValidationError) as ctx:
            entry.full_clean()
        self.assertIn("ready_check", ctx.exception.message_dict)

    def test_admin_add_disabled(self) -> None:
        request = RequestFactory().get("/")
        request.user = CustomUser.objects.create_superuser(
            username="rc_superuser", password="x"
        )
        for model in (ReadyCheck, ReadyCheckEntry, EventVoicePresence):
            with self.subTest(model=model.__name__):
                self.assertFalse(
                    admin_site._registry[model].has_add_permission(request)
                )

    def test_signup_delete_keeps_entry(self) -> None:
        event = self._event()
        rc = ReadyCheck.objects.create(event=event)
        signup = self._signup(event)
        entry = ReadyCheckEntry.for_signup(rc, signup)
        entry.save()

        signup.delete()

        entry.refresh_from_db()
        self.assertIsNone(entry.signup_id)
        self.assertEqual(entry.user_id, self.user.pk)

    def test_presence_unique_and_cascade(self) -> None:
        event = self._event()
        event_pk = event.pk
        presence = EventVoicePresence.objects.create(event=event, user=self.user)
        with self.assertRaises(IntegrityError), transaction.atomic():
            EventVoicePresence.objects.create(event=event, user=self.user)

        rc = ReadyCheck.objects.create(event=event)
        ReadyCheckEntry.for_signup(rc, self._signup(event)).save()

        event.delete()

        self.assertFalse(ReadyCheck.objects.filter(pk=rc.pk).exists())
        self.assertFalse(ReadyCheckEntry.objects.filter(ready_check_id=rc.pk).exists())
        self.assertFalse(EventVoicePresence.objects.filter(pk=presence.pk).exists())
        self.assertFalse(EventVoicePresence.objects.filter(event_id=event_pk).exists())

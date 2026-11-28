"""Verify which stored Discord messages an event write wakes up."""

from django.db import transaction
from django.test import override_settings

from discordbot.live_messages import track_message
from discordbot.live_signals import connect_live_signals
from discordbot.models import LiveDiscordMessage
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from events.tests.base import EventTestCase
from org.models import Organization


@override_settings(TEST=False)
class LiveSignalTests(EventTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.sibling = self.make_event()
        other_org = Organization.objects.create(name="Other organization")
        self.other = self.make_event(organization=other_org)
        for event in (self.event, self.sibling, self.other):
            track_message(
                renderer="event_signup_reminder",
                subject_id=event.pk,
                channel_id="100",
                message_id=str(500 + event.pk),
            )

    def revisions(self) -> list[int]:
        return list(
            LiveDiscordMessage.objects.order_by("pk").values_list("revision", flat=True)
        )

    def test_model_and_organization_updates_follow_field_subscriptions(self):
        connect_live_signals()  # repeated Django app setup must not multiply receivers
        self.event.min_players = 3
        self.event.save(update_fields=["min_players"])
        self.assertEqual(self.revisions(), [1, 1, 1])
        self.event.max_players = 20
        self.event.save(update_fields=["max_players"])
        self.assertEqual(self.revisions(), [2, 1, 1])
        self.org.name = "New club name"
        self.org.save(update_fields=["name"])
        self.assertEqual(self.revisions(), [3, 2, 1])

    def test_signup_partial_save_move_and_delete(self):
        signup = EventSignup.objects.create(
            event=self.event, user=self.admin, status=SignupStatus.RSVP
        )
        self.assertEqual(self.revisions(), [2, 1, 1])
        signup.event = self.sibling
        signup.status = SignupStatus.WAITLISTED
        signup.save(
            update_fields=["status"]
        )  # event assignment still exists only in memory
        self.assertEqual(self.revisions(), [3, 1, 1])
        signup.save(update_fields=["event"])
        self.assertEqual(self.revisions(), [4, 2, 1])
        signup.delete()
        self.assertEqual(self.revisions(), [4, 3, 1])

    def test_bulk_state_transition_rolls_back_with_dirty_mark(self):
        with transaction.atomic():
            self.event.transition_state(EventState.ROLL_CALL)
            self.assertEqual(self.revisions(), [2, 1, 1])
            transaction.set_rollback(True)
        self.assertEqual(self.revisions(), [1, 1, 1])
        self.assertEqual(
            Event.objects.get(pk=self.event.pk).state, EventState.SIGNUPS_OPEN
        )
        self.event.delete()
        self.assertEqual(self.revisions(), [2, 1, 1])

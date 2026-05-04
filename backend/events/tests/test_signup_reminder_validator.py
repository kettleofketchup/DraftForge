"""Tests that the discord_signup_reminder × event_repeater validator only fires
when the request actually changes one of those fields.

Regression for the bug where any PATCH to a single event hit a 400 because
discord_signup_reminder defaults to True.
"""

from datetime import date, timedelta

from django.utils import timezone as tz
from rest_framework.test import APIClient

from events.tests.test_discord_tasks import _DiscordTaskTestCase


class SignupReminderValidatorScopeTest(_DiscordTaskTestCase):
    """The validator must only fire when the request changes signup_reminder
    or event_repeater. Pre-existing invalid state must not block unrelated patches."""

    def _client(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        return client

    def test_unrelated_patch_succeeds_on_single_event_with_default_reminder(self):
        """The bug: PATCH name on a single event with reminder=True (default)
        used to fail because the validator read instance state and tripped.
        Should succeed now."""
        client = self._client()
        # self.event from base.py has no event_repeater + default reminder=True
        resp = client.patch(
            f"/api/events/{self.event.pk}/",
            {"name": "Edited"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_setting_reminder_true_on_single_event_still_rejected(self):
        client = self._client()
        resp = client.patch(
            f"/api/events/{self.event.pk}/",
            {"discord_signup_reminder": True},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("discord_signup_reminder", resp.json())

    def test_clearing_reminder_to_false_succeeds_as_escape_hatch(self):
        """Users must be able to fix the invalid state."""
        client = self._client()
        resp = client.patch(
            f"/api/events/{self.event.pk}/",
            {"discord_signup_reminder": False},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_setting_reminder_true_on_repeating_event_succeeds(self):
        """If the event already has a repeater (set via DB), patching
        discord_signup_reminder=True should succeed."""
        from events.models import EventRepeater, RepeatFrequency

        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Test Repeater",
            frequency=RepeatFrequency.WEEKLY,
            time_of_day="20:00:00",
            starts_at=date.today(),
        )
        # event_repeater is read-only in the serializer; set it directly.
        self.event.__class__.objects.filter(pk=self.event.pk).update(
            event_repeater=repeater
        )
        client = self._client()
        resp = client.patch(
            f"/api/events/{self.event.pk}/",
            {"discord_signup_reminder": True},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_create_with_default_reminder_no_repeater_still_rejected(self):
        """Create-time validation still applies — model default is True."""
        client = self._client()
        resp = client.post(
            "/api/events/",
            {
                "organization": self.org.pk,
                "name": "New Single Event",
                "scheduled_at": (tz.now() + timedelta(days=3)).isoformat(),
                # No discord_signup_reminder → model default True
                # No event_repeater → single event
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("discord_signup_reminder", resp.json())

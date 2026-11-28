from unittest.mock import patch

from django.test import override_settings

from discordbot.live_renderers import render_live_message
from discordbot.payload_schema import DiscordMessage
from discordbot.payloads import V2_FLAG
from events.constants import EventState, SignupStatus
from events.models import EventSignup
from events.tests.base import EventTestCase


@override_settings(TEST=False)
class LiveReminderRenderTests(EventTestCase):
    def test_counts_only_current_seat_holders_and_keeps_event_controls(self) -> None:
        signups = {
            status: EventSignup.objects.create(
                event=self.event, user=self.make_user(), status=status
            )
            for status in SignupStatus.values
        }
        body = render_live_message("event_signup_reminder", self.event.pk)
        self.assertEqual(DiscordMessage.model_validate(body).flags, V2_FLAG)
        self.assertNotIn("embeds", body)
        self.assertEqual(body["allowed_mentions"], {"parse": []})
        components = body["components"][0]["components"]
        self.assertIn("**Signed up:** 4/10 players", components[-2]["content"])
        signup, link = components[-1]["components"]
        self.assertEqual(signup["custom_id"], f"event_signup:{self.event.pk}")
        self.assertTrue(link["url"].endswith(f"/events/{self.event.pk}"))

        signups[SignupStatus.APPROVED].delete()
        self.event.state = EventState.CANCELLED
        self.event.name = "Rescheduled Cup"
        self.event.save(update_fields=["state", "name"])
        updated = render_live_message("event_signup_reminder", self.event.pk)
        components = updated["components"][0]["components"]
        self.assertIn("Rescheduled Cup", components[0]["components"][0]["content"])
        self.assertIn("cancelled", components[1]["content"])
        self.assertIn("**Signed up:** 3/10 players", components[-2]["content"])
        self.assertEqual(components[-1]["components"], [link])

    @patch("events.discord.embeds.SITE_URL", "")
    def test_closed_event_without_link_omits_action_row(self) -> None:
        self.event.state = EventState.CANCELLED
        self.event.save(update_fields=["state"])
        body = render_live_message("event_signup_reminder", self.event.pk)
        children = body["components"][0]["components"]
        self.assertFalse(any(child["type"] == 1 for child in children))

    def test_deleted_event_and_unknown_renderer(self) -> None:
        pk = self.event.pk
        self.event.delete()
        self.assertIsNone(render_live_message("event_signup_reminder", pk))
        with self.assertRaisesRegex(ValueError, "Unknown live message renderer"):
            render_live_message("typo", pk)

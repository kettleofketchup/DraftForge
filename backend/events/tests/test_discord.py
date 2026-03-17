from django.test import TestCase

from events.discord import (
    build_announcement_embed,
    build_attendance_reminder_embed,
    build_new_event_embed,
    build_profile_reminder_embed,
    build_signup_reminder_embed,
    build_signup_update_embed,
)
from events.tests.base import EventTestCase


class BuildAnnouncementEmbedTest(EventTestCase):
    def test_uses_event_name_as_title(self):
        embed = build_announcement_embed(self.event)
        self.assertIn(self.event.name, embed["title"])

    def test_includes_scheduled_time(self):
        embed = build_announcement_embed(self.event)
        self.assertIn("description", embed)

    def test_has_color(self):
        embed = build_announcement_embed(self.event)
        self.assertIsInstance(embed["color"], int)


class BuildSignupUpdateEmbedTest(EventTestCase):
    def test_includes_event_name(self):
        embed = build_signup_update_embed(self.event)
        self.assertIn(self.event.name, embed["title"])

    def test_includes_signup_count_field(self):
        embed = build_signup_update_embed(self.event)
        field_names = [f["name"] for f in embed.get("fields", [])]
        self.assertTrue(
            any("sign" in n.lower() or "player" in n.lower() for n in field_names)
        )


class BuildNewEventEmbedTest(EventTestCase):
    def test_includes_event_name(self):
        embed = build_new_event_embed(self.event)
        self.assertIn(self.event.name, embed["title"])


class BuildSignupReminderEmbedTest(EventTestCase):
    def test_includes_event_name(self):
        embed = build_signup_reminder_embed(self.event)
        self.assertIn(self.event.name, embed["title"])


class BuildAttendanceReminderEmbedTest(EventTestCase):
    def test_includes_event_name(self):
        embed = build_attendance_reminder_embed(self.event)
        self.assertIn(self.event.name, embed["title"])


class BuildProfileReminderEmbedTest(EventTestCase):
    def test_includes_event_name(self):
        embed = build_profile_reminder_embed(self.event)
        self.assertIn(self.event.name, embed["title"])

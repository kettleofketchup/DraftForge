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


class BuildAnnouncementEmbedSignupListTest(EventTestCase):
    def test_empty_signup_list(self):
        embed = build_announcement_embed(self.event)
        field_names = [f["name"] for f in embed.get("fields", [])]
        # No signup fields when no signups
        self.assertFalse(any("Signed Up" in n for n in field_names))

    def test_signup_list_shows_confirmed_users(self):
        from events.models import EventSignup, SignupStatus

        EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.CONFIRMED
        )
        embed = build_announcement_embed(self.event)
        field_names = [f["name"] for f in embed.get("fields", [])]
        self.assertTrue(any("Signed Up" in n for n in field_names))

    def test_signup_list_shows_status_icons(self):
        from events.models import EventSignup, SignupStatus

        EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.CONFIRMED
        )
        embed = build_announcement_embed(self.event)
        signed_up_field = next(f for f in embed["fields"] if "Signed Up" in f["name"])
        self.assertIn("\u2705", signed_up_field["value"])

    def test_waitlisted_in_separate_field(self):
        from app.models import CustomUser, PositionsModel
        from events.models import EventSignup, SignupStatus

        self.event.max_players = 1
        self.event.save()
        EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.CONFIRMED
        )
        pos = PositionsModel.objects.create()
        user2 = CustomUser.objects.create(username="waitlisted_user", positions=pos)
        EventSignup.objects.create(
            event=self.event,
            user=user2,
            status=SignupStatus.WAITLISTED,
            waitlist_position=1,
        )
        embed = build_announcement_embed(self.event)
        field_names = [f["name"] for f in embed["fields"]]
        self.assertTrue(any("Waitlisted" in n for n in field_names))

    def test_signup_fields_are_inline(self):
        from events.models import EventSignup, SignupStatus

        EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.CONFIRMED
        )
        embed = build_announcement_embed(self.event)
        signed_up_field = next(f for f in embed["fields"] if "Signed Up" in f["name"])
        self.assertTrue(signed_up_field["inline"])

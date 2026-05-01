from django.test import TestCase

from events.serializers import EventSlimSerializer


# Fields that fire_due_reminders reads off slim payloads from get_events_list.
# If the serializer omits any of these, getattr() returns None and the fire
# path silently uses defaults. The CI test below catches the trap.
REMINDER_FIELDS_REQUIRED_BY_FIRE_PATH = [
    "discord_announcement",
    "discord_announcement_hours",
    "discord_announcement_channel_id",
    "discord_signup_reminder",
    "discord_signup_reminder_hours",
    "discord_confirm_attendance",
    "discord_confirm_attendance_hours",
    "discord_profile_reminder",
    "discord_profile_reminder_hours",
]


class EventSlimSerializerReminderFieldsTest(TestCase):
    def test_slim_serializer_exposes_all_reminder_fields(self):
        exposed = set(EventSlimSerializer.Meta.fields)
        missing = [f for f in REMINDER_FIELDS_REQUIRED_BY_FIRE_PATH if f not in exposed]
        self.assertEqual(missing, [], f"EventSlimSerializer missing: {missing}")

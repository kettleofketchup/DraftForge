from django.test import TestCase
from django.utils import timezone

from discordbot.models import (
    ChannelType,
    DiscordEvent,
    DiscordEventDM,
    DiscordEventLog,
    DiscordEventMsgAnnouncement,
    DiscordEventMsgSignup,
    DMType,
)


def _make_event():
    """Create a minimal Event (and its required Organization + User)."""
    from app.models import CustomUser, Organization
    from events.models import Event

    user = CustomUser.objects.create_user(username="tester", password="pw")
    org = Organization.objects.create(name="Test Org", owner=user)
    event = Event.objects.create(
        organization=org,
        name="Test Event",
        scheduled_at=timezone.now(),
        created_by=user,
    )
    return event, org, user


class DiscordEventMsgSignupTest(TestCase):
    def test_create_with_defaults(self):
        event, _org, _user = _make_event()
        msg = DiscordEventMsgSignup.objects.create(
            event=event,
            channel_id="111222333444555666",
        )
        self.assertFalse(msg.has_posted)
        self.assertEqual(msg.channel_type, ChannelType.TEXT)
        self.assertIsNone(msg.message_id)
        self.assertIsNone(msg.thread_id)
        self.assertIsNotNone(msg.created_at)

    def test_channel_type_choices(self):
        event, _org, _user = _make_event()
        for ct in ChannelType:
            msg = DiscordEventMsgSignup.objects.create(
                event=event,
                channel_id="111",
                channel_type=ct,
            )
            self.assertEqual(msg.channel_type, ct)

    def test_str(self):
        event, _org, _user = _make_event()
        msg = DiscordEventMsgSignup.objects.create(
            event=event,
            channel_id="111",
        )
        self.assertIn("Signup msg", str(msg))


class DiscordEventMsgAnnouncementTest(TestCase):
    def test_create(self):
        event, _org, _user = _make_event()
        msg = DiscordEventMsgAnnouncement.objects.create(
            event=event,
            channel_id="222333444555666777",
            channel_type=ChannelType.ANNOUNCEMENT,
        )
        self.assertEqual(msg.channel_type, ChannelType.ANNOUNCEMENT)
        self.assertFalse(msg.has_posted)

    def test_str(self):
        event, _org, _user = _make_event()
        msg = DiscordEventMsgAnnouncement.objects.create(
            event=event,
            channel_id="222",
        )
        self.assertIn("Announcement msg", str(msg))


class DiscordEventTest(TestCase):
    def test_create(self):
        event, _org, _user = _make_event()
        de = DiscordEvent.objects.create(
            event=event,
            guild_id="999888777666555444",
        )
        self.assertEqual(de.guild_id, "999888777666555444")
        self.assertIsNone(de.signup_message)
        self.assertIsNone(de.announcement)
        self.assertIsNone(de.scheduled_event_id)

    def test_one_to_one_event(self):
        event, _org, _user = _make_event()
        DiscordEvent.objects.create(event=event, guild_id="111")
        # Accessible via reverse relation
        self.assertEqual(event.discord_event.guild_id, "111")

    def test_link_signup_message(self):
        event, _org, _user = _make_event()
        signup = DiscordEventMsgSignup.objects.create(
            event=event,
            channel_id="444",
        )
        de = DiscordEvent.objects.create(
            event=event,
            guild_id="111",
            signup_message=signup,
        )
        self.assertEqual(de.signup_message, signup)

    def test_scheduled_event_id(self):
        event, _org, _user = _make_event()
        de = DiscordEvent.objects.create(
            event=event,
            guild_id="111",
            scheduled_event_id="888777666",
        )
        self.assertEqual(de.scheduled_event_id, "888777666")

    def test_str(self):
        event, _org, _user = _make_event()
        de = DiscordEvent.objects.create(event=event, guild_id="111")
        self.assertIn("DiscordEvent", str(de))


class DiscordEventDMTest(TestCase):
    def test_create(self):
        event, org, user = _make_event()
        from org.models import OrgUser

        org_user = OrgUser.objects.create(user=user, organization=org)
        de = DiscordEvent.objects.create(event=event, guild_id="111")
        dm = DiscordEventDM.objects.create(
            discord_event=de,
            org_user=org_user,
            dm_type=DMType.SIGNUP_REMINDER,
        )
        self.assertFalse(dm.delivered)
        self.assertFalse(dm.responded)
        self.assertEqual(dm.dm_type, DMType.SIGNUP_REMINDER)
        self.assertIsNotNone(dm.created_at)

    def test_discord_user_id_property(self):
        event, org, user = _make_event()
        user.discordId = "123456789"
        user.save()
        from org.models import OrgUser

        org_user = OrgUser.objects.create(user=user, organization=org)
        de = DiscordEvent.objects.create(event=event, guild_id="111")
        dm = DiscordEventDM.objects.create(
            discord_event=de,
            org_user=org_user,
            dm_type=DMType.TEAM_DRAFT_STARTED,
        )
        self.assertEqual(dm.discord_user_id, "123456789")

    def test_can_send_true_when_discord_id_set(self):
        event, org, user = _make_event()
        user.discordId = "123456789"
        user.save()
        from org.models import OrgUser

        org_user = OrgUser.objects.create(user=user, organization=org)
        de = DiscordEvent.objects.create(event=event, guild_id="111")
        dm = DiscordEventDM.objects.create(
            discord_event=de,
            org_user=org_user,
            dm_type=DMType.ATTENDANCE_CONFIRM,
        )
        self.assertTrue(dm.can_send)

    def test_can_send_false_when_no_discord_id(self):
        event, org, user = _make_event()
        # user.discordId is None by default
        from org.models import OrgUser

        org_user = OrgUser.objects.create(user=user, organization=org)
        de = DiscordEvent.objects.create(event=event, guild_id="111")
        dm = DiscordEventDM.objects.create(
            discord_event=de,
            org_user=org_user,
            dm_type=DMType.PROFILE_UPDATE,
        )
        self.assertFalse(dm.can_send)

    def test_str(self):
        event, org, user = _make_event()
        from org.models import OrgUser

        org_user = OrgUser.objects.create(user=user, organization=org)
        de = DiscordEvent.objects.create(event=event, guild_id="111")
        dm = DiscordEventDM.objects.create(
            discord_event=de,
            org_user=org_user,
            dm_type=DMType.SIGNUP_REMINDER,
        )
        self.assertIn("Signup Reminder", str(dm))


class DiscordEventLogTest(TestCase):
    def test_create(self):
        event, _org, _user = _make_event()
        de = DiscordEvent.objects.create(event=event, guild_id="111")
        log = DiscordEventLog.objects.create(
            discord_event=de,
            action="create_event",
            status_code=200,
            success=True,
        )
        self.assertTrue(log.success)
        self.assertEqual(log.action, "create_event")
        self.assertIsNotNone(log.created_at)

    def test_linked_to_discord_event(self):
        event, _org, _user = _make_event()
        de = DiscordEvent.objects.create(event=event, guild_id="111")
        DiscordEventLog.objects.create(
            discord_event=de,
            action="post_signup",
            success=True,
        )
        self.assertEqual(de.logs.count(), 1)

    def test_linked_to_dm(self):
        event, org, user = _make_event()
        from org.models import OrgUser

        org_user = OrgUser.objects.create(user=user, organization=org)
        de = DiscordEvent.objects.create(event=event, guild_id="111")
        dm = DiscordEventDM.objects.create(
            discord_event=de,
            org_user=org_user,
            dm_type=DMType.SIGNUP_REMINDER,
        )
        log = DiscordEventLog.objects.create(
            discord_event=de,
            dm=dm,
            action="send_dm",
            status_code=200,
            success=True,
        )
        self.assertEqual(log.dm, dm)
        self.assertEqual(dm.logs.count(), 1)

    def test_error_fields(self):
        event, _org, _user = _make_event()
        de = DiscordEvent.objects.create(event=event, guild_id="111")
        log = DiscordEventLog.objects.create(
            discord_event=de,
            action="create_event",
            status_code=403,
            error_message="Missing Access",
            response_data={"code": 50001},
            success=False,
        )
        self.assertFalse(log.success)
        self.assertEqual(log.error_message, "Missing Access")
        self.assertEqual(log.response_data["code"], 50001)

    def test_str(self):
        event, _org, _user = _make_event()
        de = DiscordEvent.objects.create(event=event, guild_id="111")
        log = DiscordEventLog.objects.create(
            discord_event=de,
            action="post_signup",
            success=True,
        )
        self.assertIn("post_signup", str(log))
        self.assertIn("ok", str(log))

from unittest.mock import MagicMock, patch

from discordbot.models import DiscordMessageLog
from events.constants import EventState
from events.tests.base import EventTestCase


class SendEventAnnouncementTaskTest(EventTestCase):
    @patch("discordbot.utils.requests.post")
    def test_announcement_creates_log(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": "111222333"}),
        )
        mock_post.return_value.raise_for_status = MagicMock()
        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()
        from events.tasks import send_event_announcement

        send_event_announcement(self.event.pk)
        log = DiscordMessageLog.objects.get(
            source="event_announcement", source_id=self.event.pk
        )
        self.assertTrue(log.success)
        self.assertEqual(log.channel_id, "1482767177063858216")

    @patch("discordbot.utils.requests.post")
    def test_announcement_skipped_when_disabled(self, mock_post):
        self.event.discord_announcement = False
        self.event.save()
        from events.tasks import send_event_announcement

        send_event_announcement(self.event.pk)
        self.assertEqual(
            DiscordMessageLog.objects.filter(source="event_announcement").count(), 0
        )
        mock_post.assert_not_called()


class SendSignupUpdateTaskTest(EventTestCase):
    @patch("discordbot.utils.requests.patch")
    @patch("discordbot.utils.requests.post")
    def test_signup_update_edits_announcement(self, mock_post, mock_patch):
        """signup update should PATCH the original announcement message."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": "444555666"}),
        )
        mock_post.return_value.raise_for_status = MagicMock()
        mock_patch.return_value = MagicMock(status_code=200)
        mock_patch.return_value.json.return_value = {"id": "444555666"}
        mock_patch.return_value.raise_for_status = MagicMock()

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()

        # First create the announcement
        from events.tasks import send_event_announcement

        send_event_announcement(self.event.pk)

        # Then update it
        from events.tasks import send_signup_update

        send_signup_update(self.event.pk)

        mock_patch.assert_called_once()
        call_url = mock_patch.call_args[0][0]
        self.assertIn("444555666", call_url)

    def test_signup_update_skipped_when_no_announcement(self):
        from events.tasks import send_signup_update

        result = send_signup_update(self.event.pk)
        self.assertEqual(result, "Skipped: no announcement message")


class SendEventAnnouncementComponentsTest(EventTestCase):
    @patch("discordbot.utils.requests.post")
    def test_announcement_includes_components_in_payload(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": "comp111"}),
        )
        mock_post.return_value.raise_for_status = MagicMock()

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()

        from events.tasks import send_event_announcement

        send_event_announcement(self.event.pk)

        call_args = mock_post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        self.assertIn("components", payload)
        self.assertTrue(len(payload["components"]) >= 1)

    @patch("discordbot.utils.requests.post")
    def test_announcement_components_contain_signup_button(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": "comp222"}),
        )
        mock_post.return_value.raise_for_status = MagicMock()

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()

        from events.tasks import send_event_announcement

        send_event_announcement(self.event.pk)

        call_args = mock_post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        buttons = payload["components"][0]["components"]
        custom_ids = [b.get("custom_id") for b in buttons if b.get("custom_id")]
        self.assertIn(f"event_signup:{self.event.pk}", custom_ids)


class SendSignupUpdateEditsMessageTest(EventTestCase):
    @patch("discordbot.utils.requests.patch")
    @patch("discordbot.utils.requests.post")
    def test_signup_update_edits_original_announcement(self, mock_post, mock_patch):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": "orig111"}),
        )
        mock_post.return_value.raise_for_status = MagicMock()

        self.event.discord_announcement = True
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()

        from events.tasks import send_event_announcement

        send_event_announcement(self.event.pk)

        mock_patch.return_value = MagicMock(status_code=200)
        mock_patch.return_value.json.return_value = {"id": "orig111"}
        mock_patch.return_value.raise_for_status = MagicMock()

        from events.tasks import send_signup_update

        send_signup_update(self.event.pk)

        mock_patch.assert_called_once()
        call_url = mock_patch.call_args[0][0]
        self.assertIn("orig111", call_url)

    def test_signup_update_skips_when_no_announcement(self):
        from events.tasks import send_signup_update

        result = send_signup_update(self.event.pk)
        self.assertEqual(result, "Skipped: no announcement message")


class CheckEventRemindersTaskTest(EventTestCase):
    @patch("discordbot.utils.requests.post")
    def test_signup_reminder_sent_when_due(self, mock_post):
        from datetime import timedelta

        from django.utils import timezone

        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": "rem111"}),
        )
        mock_post.return_value.raise_for_status = MagicMock()
        self.event.scheduled_at = timezone.now() + timedelta(hours=23)
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.discord_signup_reminder = True
        self.event.discord_signup_reminder_hours = 24
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()
        from events.tasks import check_event_reminders

        check_event_reminders()
        self.assertTrue(
            DiscordMessageLog.objects.filter(
                source="signup_reminder", source_id=self.event.pk
            ).exists()
        )

    @patch("discordbot.utils.requests.post")
    def test_signup_reminder_not_sent_twice(self, mock_post):
        from datetime import timedelta

        from django.utils import timezone

        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": "rem222"}),
        )
        mock_post.return_value.raise_for_status = MagicMock()
        self.event.scheduled_at = timezone.now() + timedelta(hours=23)
        self.event.state = EventState.SIGNUPS_OPEN
        self.event.discord_signup_reminder = True
        self.event.discord_signup_reminder_hours = 24
        self.event.discord_announcement_channel_id = "1482767177063858216"
        self.event.save()
        from events.tasks import check_event_reminders

        check_event_reminders()
        check_event_reminders()  # Run again — should NOT send duplicate
        self.assertEqual(
            DiscordMessageLog.objects.filter(
                source="signup_reminder", source_id=self.event.pk
            ).count(),
            1,
        )

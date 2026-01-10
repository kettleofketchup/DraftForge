from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from discordbot.models import RSVP, EventTemplate, ScheduledEvent

User = get_user_model()


class EventTemplateModelTest(TestCase):
    def test_create_event_template(self):
        """EventTemplate can be created with required fields."""
        template = EventTemplate.objects.create(
            name="Weekly Tournament",
            template_type="event",
            title="DTX Weekly",
            description="Join us for the weekly tournament!",
            color="#00FF00",
            channel_id="123456789012345678",
            include_rsvp=True,
        )
        self.assertEqual(template.name, "Weekly Tournament")
        self.assertEqual(template.template_type, "event")


class ScheduledEventModelTest(TestCase):
    def setUp(self):
        self.template = EventTemplate.objects.create(
            name="Test Event",
            template_type="announcement",
            title="Test",
            description="Test description",
            color="#FF0000",
            channel_id="123456789012345678",
        )

    def test_create_scheduled_event(self):
        """ScheduledEvent can be created linked to a template."""
        from datetime import time

        from django.utils import timezone

        event = ScheduledEvent.objects.create(
            template=self.template,
            is_recurring=True,
            day_of_week=0,  # Monday
            time_of_day=time(19, 0),  # 7 PM
            next_post_at=timezone.now(),
        )
        self.assertTrue(event.is_recurring)
        self.assertEqual(event.day_of_week, 0)


class RSVPModelTest(TestCase):
    def setUp(self):
        self.template = EventTemplate.objects.create(
            name="Test Event",
            template_type="event",
            title="Test",
            description="Test",
            color="#0000FF",
            channel_id="123456789012345678",
        )
        from datetime import time

        from django.utils import timezone

        self.scheduled_event = ScheduledEvent.objects.create(
            template=self.template,
            next_post_at=timezone.now(),
        )

    def test_create_rsvp(self):
        """RSVP can be created for a scheduled event."""
        rsvp = RSVP.objects.create(
            scheduled_event=self.scheduled_event,
            discord_user_id="987654321098765432",
            discord_username="TestUser",
            status="yes",
        )
        self.assertEqual(rsvp.status, "yes")
        self.assertEqual(rsvp.discord_username, "TestUser")


class EmbedBuildersTest(TestCase):
    def test_event_announcement_embed(self):
        """event_announcement_embed returns dict with correct structure."""
        from discordbot.embeds import event_announcement_embed

        template = EventTemplate.objects.create(
            name="Test",
            template_type="event",
            title="Weekly Game Night",
            description="Join us for fun!",
            color="#5865F2",
            channel_id="123",
        )
        embed = event_announcement_embed(template)

        self.assertEqual(embed["title"], "Weekly Game Night")
        self.assertEqual(embed["description"], "Join us for fun!")
        self.assertEqual(embed["color"], 0x5865F2)
        self.assertIn("footer", embed)

    def test_tournament_created_embed(self):
        """tournament_created_embed returns dict with tournament info."""
        from datetime import date

        from app.models import Tournament
        from discordbot.embeds import tournament_created_embed

        tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        embed = tournament_created_embed(tournament)

        self.assertIn("Test Tournament", embed["title"])
        self.assertIn("color", embed)


class UtilsTest(TestCase):
    @patch("discordbot.utils.requests.post")
    def test_sync_send_embed(self, mock_post):
        """sync_send_embed sends POST to Discord webhook."""
        from discordbot.utils import sync_send_embed

        mock_post.return_value = MagicMock(status_code=200)

        result = sync_send_embed(
            channel_id="123456789",
            title="Test Title",
            description="Test Description",
            color=0x00FF00,
        )

        self.assertTrue(mock_post.called)

    @patch("discordbot.utils.requests.post")
    def test_sync_send_templated_embed(self, mock_post):
        """sync_send_templated_embed sends embed from EventTemplate."""
        from discordbot.utils import sync_send_templated_embed

        mock_post.return_value = MagicMock(status_code=200)

        template = EventTemplate.objects.create(
            name="Test",
            template_type="announcement",
            title="Test Title",
            description="Test Desc",
            color="#FF0000",
            channel_id="123456789",
        )

        sync_send_templated_embed(template)
        self.assertTrue(mock_post.called)

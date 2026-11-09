from datetime import date, time, timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import Tournament
from discordbot.embeds import event_announcement_embed, tournament_created_embed
from discordbot.models import RSVP, EventTemplate, ScheduledEvent
from discordbot.tasks import check_scheduled_events
from discordbot.utils import sync_send_embed, sync_send_templated_embed
from events.schemas import ScheduledEventDueSchema

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
        event = ScheduledEvent.objects.create(
            template=self.template,
            is_recurring=True,
            day_of_week=0,  # Sunday
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
        mock_post.return_value = MagicMock(status_code=200)

        sync_send_embed(
            channel_id="123456789",
            title="Test Title",
            description="Test Description",
            color=0x00FF00,
        )

        self.assertTrue(mock_post.called)

    @patch("discordbot.utils.requests.post")
    def test_sync_send_templated_embed(self, mock_post):
        """sync_send_templated_embed sends embed from EventTemplate."""
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


TOKEN = "test-internal-token"


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class DueScheduledEventsEndpointTest(TestCase):
    """The internal due-events endpoint returns only active, due, unposted events."""

    def setUp(self):
        self.template = EventTemplate.objects.create(
            name="Test Event",
            template_type="announcement",
            title="Test",
            description="Test description",
            color="#FF0000",
            channel_id="123456789012345678",
        )

    def _due_pks(self):
        resp = APIClient().get(
            "/api/internal/scheduled-events/due/", HTTP_X_INTERNAL_TOKEN=TOKEN
        )
        self.assertEqual(resp.status_code, 200)
        return [row["pk"] for row in resp.json()]

    def test_returns_due_event(self):
        due = ScheduledEvent.objects.create(
            template=self.template,
            next_post_at=timezone.now() - timedelta(minutes=5),
            is_active=True,
        )
        self.assertEqual(self._due_pks(), [due.pk])

    def test_skips_future_posted_and_inactive_events(self):
        past = timezone.now() - timedelta(minutes=5)
        ScheduledEvent.objects.create(
            template=self.template,
            next_post_at=timezone.now() + timedelta(hours=1),
            is_active=True,
        )
        ScheduledEvent.objects.create(
            template=self.template,
            next_post_at=past,
            is_active=True,
            discord_message_id="already-posted",
        )
        ScheduledEvent.objects.create(
            template=self.template, next_post_at=past, is_active=False
        )
        self.assertEqual(self._due_pks(), [])


def _due(pk, *, is_recurring=False, next_post_at=None, include_rsvp=True):
    return ScheduledEventDueSchema.model_validate(
        {
            "pk": pk,
            "is_recurring": is_recurring,
            "next_post_at": next_post_at,
            "template": {
                "name": "Test Event",
                "title": "Test",
                "description": "Test description",
                "color": "#FF0000",
                "channel_id": "123456789012345678",
                "include_rsvp": include_rsvp,
            },
        }
    )


@patch("app.internal_client.update_scheduled_event")
@patch("discordbot.utils.sync_add_reactions")
@patch("discordbot.utils.sync_send_embed")
class CheckScheduledEventsTaskTest(SimpleTestCase):
    """check_scheduled_events posts what the internal API reports as due."""

    @patch("app.internal_client.get_due_scheduled_events")
    def test_posts_due_event_and_stores_message_id(
        self, mock_due, mock_send, mock_reactions, mock_update
    ):
        mock_due.return_value = [_due(7)]
        mock_send.return_value = {"id": "999888777"}

        check_scheduled_events()

        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.kwargs["channel_id"], "123456789012345678")
        mock_reactions.assert_called_once_with("123456789012345678", "999888777")
        mock_update.assert_called_once_with(7, discord_message_id="999888777")

    @patch("app.internal_client.get_due_scheduled_events", return_value=[])
    def test_nothing_due_posts_nothing(
        self, mock_due, mock_send, mock_reactions, mock_update
    ):
        check_scheduled_events()

        mock_send.assert_not_called()
        mock_update.assert_not_called()

    @patch("app.internal_client.get_due_scheduled_events")
    def test_recurring_event_reschedules_a_week_later(
        self, mock_due, mock_send, mock_reactions, mock_update
    ):
        original = timezone.now() - timedelta(minutes=5)
        mock_due.return_value = [
            _due(8, is_recurring=True, next_post_at=original.isoformat())
        ]
        mock_send.return_value = {"id": "111222333"}

        check_scheduled_events()

        mock_update.assert_called_once_with(
            8,
            discord_message_id=None,
            next_post_at=(original + timedelta(days=7)).isoformat(),
        )

    @patch("app.internal_client.get_due_scheduled_events")
    def test_failed_post_is_not_marked_posted(
        self, mock_due, mock_send, mock_reactions, mock_update
    ):
        mock_due.return_value = [_due(9)]
        mock_send.return_value = None

        check_scheduled_events()

        mock_reactions.assert_not_called()
        mock_update.assert_not_called()

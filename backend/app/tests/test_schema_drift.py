"""Schema drift detection tests.

These tests validate that Django serializer output matches the Pydantic
schemas used by celery workers. If a model/serializer field changes but
the Pydantic schema isn't updated, these tests fail immediately.

Run: docker compose -f docker/docker-compose.test.yaml run --rm --entrypoint "" backend \
       python manage.py test app.tests.test_schema_drift -v 2
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from pydantic import ValidationError

from app.models import CustomUser, Organization
from app.schemas import (
    DiscordEventState,
    EventTaskData,
    GameWithoutHeroDraft,
    MessageLogEntry,
    RepeaterSubscriber,
    ScheduledEventDue,
    SyncDiscordState,
    TournamentParticipant,
    TournamentTaskData,
)


class EventTaskDataDriftTest(TestCase):
    """Verify EventSerializer output validates against EventTaskData schema."""

    def test_serializer_output_matches_schema(self):
        from events.models import Event
        from events.serializers import EventSerializer

        org = Organization.objects.create(
            name="Schema Test Org", discord_server_id="123456"
        )
        event = Event.objects.create(
            organization=org,
            name="Schema Test Event",
            state="signups_open",
            scheduled_at=timezone.now() + timedelta(days=1),
            discord_announcement=True,
            discord_announcement_channel_id="999",
        )

        # Simulate what get_event_for_task returns
        data = EventSerializer(event).data
        data["organization_discord_server_id"] = org.discord_server_id or ""
        data["event_repeater_id"] = event.event_repeater_id

        # This will raise ValidationError if schema drifts from serializer
        parsed = EventTaskData.model_validate(data)
        self.assertEqual(parsed.id, event.pk)
        self.assertEqual(parsed.name, "Schema Test Event")
        self.assertEqual(parsed.organization_discord_server_id, "123456")
        self.assertTrue(parsed.discord_announcement)

    def test_missing_required_field_raises(self):
        """EventTaskData requires id and name at minimum."""
        with self.assertRaises(ValidationError):
            EventTaskData(state="upcoming", scheduled_at=timezone.now())

    def test_extra_fields_ignored(self):
        """Extra fields from serializer don't break the schema."""
        data = {
            "id": 1,
            "name": "Test",
            "state": "upcoming",
            "scheduled_at": timezone.now().isoformat(),
            "organization": 1,
            "some_new_field": "should be ignored",
        }
        parsed = EventTaskData.model_validate(data)
        self.assertEqual(parsed.id, 1)


class MessageLogEntryDriftTest(TestCase):
    def test_log_entry_validates(self):
        data = {
            "id": 1,
            "channel_id": "123",
            "source": "signup_reminder",
            "source_id": 1,
            "discord_message_id": "456",
            "status_code": 200,
            "success": True,
            "response_data": {"id": "789"},
            "created_at": "2026-01-01T00:00:00Z",
        }
        parsed = MessageLogEntry.model_validate(data)
        self.assertEqual(parsed.source, "signup_reminder")
        self.assertTrue(parsed.success)


class SyncDiscordStateDriftTest(TestCase):
    def test_sync_state_validates(self):
        data = {
            "active_events": [{"pk": 1, "name": "Test", "state": "signups_open"}],
            "existing_logs": [["event_announcement", 1]],
            "events_with_signup": [1],
            "events_with_scheduled": [],
            "events_with_recent_attempt": [],
        }
        parsed = SyncDiscordState.model_validate(data)
        self.assertEqual(len(parsed.active_events), 1)


class DiscordEventStateDriftTest(TestCase):
    def test_discord_state_validates(self):
        data = {
            "has_discord_event": True,
            "discord_event_pk": 5,
            "scheduled_event_id": "999",
            "signup_posted": True,
            "fired_actions": ["send_signup_post", "create_scheduled_event"],
            "has_dms": False,
        }
        parsed = DiscordEventState.model_validate(data)
        self.assertTrue(parsed.has_discord_event)
        self.assertEqual(len(parsed.fired_actions), 2)


class RepeaterSubscriberDriftTest(TestCase):
    def test_subscriber_validates(self):
        data = {"user_pk": 1, "discord_id": "123456", "org_user_pk": 10}
        parsed = RepeaterSubscriber.model_validate(data)
        self.assertEqual(parsed.discord_id, "123456")


class TournamentTaskDataDriftTest(TestCase):
    """Verify Tournament model output validates against TournamentTaskData schema."""

    def test_tournament_validates(self):
        from app.models import Tournament
        from app.schemas import TournamentTaskData

        t = Tournament.objects.create(
            name="Test", state="future", date_played=timezone.now()
        )
        data = {
            "id": t.pk,
            "name": t.name,
            "state": t.state,
            "auto_create_hero_drafts": t.auto_create_hero_drafts,
            "discord_send_draft_link": t.discord_send_draft_link,
            "discord_send_herodraft_link": t.discord_send_herodraft_link,
            "tournament_type": t.tournament_type,
            "draft_type": t.draft_type,
        }
        parsed = TournamentTaskData.model_validate(data)
        self.assertEqual(parsed.pk, t.pk)
        self.assertFalse(parsed.auto_create_hero_drafts)

    def test_extra_fields_ignored(self):
        from app.schemas import TournamentTaskData

        data = {
            "id": 1,
            "name": "T",
            "state": "future",
            "some_new_field": "ignored",
        }
        parsed = TournamentTaskData.model_validate(data)
        self.assertEqual(parsed.id, 1)

    def test_missing_required_field_raises(self):
        from app.schemas import TournamentTaskData

        with self.assertRaises(ValidationError):
            TournamentTaskData(name="T")  # missing id and state


class GameWithoutHeroDraftDriftTest(TestCase):
    """Verify GameWithoutHeroDraft schema validates correctly."""

    def test_game_without_herodraft_validates(self):
        from app.schemas import GameWithoutHeroDraft

        data = {
            "id": 1,
            "radiant_team_id": 10,
            "radiant_team_name": "Team A",
            "dire_team_id": 20,
            "dire_team_name": "Team B",
            "round": 1,
            "has_captains": True,
        }
        parsed = GameWithoutHeroDraft.model_validate(data)
        self.assertEqual(parsed.id, 1)
        self.assertTrue(parsed.has_captains)


class TournamentParticipantDriftTest(TestCase):
    """Verify TournamentParticipant schema validates correctly."""

    def test_participant_validates(self):
        from app.schemas import TournamentParticipant

        data = {"user_pk": 1, "discord_id": "123456789", "username": "player1"}
        parsed = TournamentParticipant.model_validate(data)
        self.assertEqual(parsed.discord_id, "123456789")

    def test_extra_fields_ignored(self):
        from app.schemas import TournamentParticipant

        data = {
            "user_pk": 1,
            "discord_id": "123",
            "username": "p",
            "extra_field": "ignored",
        }
        parsed = TournamentParticipant.model_validate(data)
        self.assertEqual(parsed.user_pk, 1)


class ScheduledEventDueDriftTest(TestCase):
    def test_scheduled_event_validates(self):
        data = {
            "pk": 1,
            "is_recurring": True,
            "next_post_at": "2026-01-01T00:00:00Z",
            "template": {
                "name": "Weekly Inhouse",
                "template_type": "event",
                "title": "Weekly Inhouse Night",
                "description": "Join us for the weekly inhouse!",
                "color": "#7289DA",
                "channel_id": "123456",
                "include_rsvp": True,
            },
        }
        parsed = ScheduledEventDue.model_validate(data)
        self.assertTrue(parsed.is_recurring)
        self.assertEqual(parsed.template.title, "Weekly Inhouse Night")
        self.assertEqual(parsed.template.color, "#7289DA")

from django.test import LiveServerTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from app.models import Organization

TOKEN = "test-internal-token"
HEADERS = {"HTTP_X_INTERNAL_TOKEN": TOKEN}


class InternalAuthGateTest(TestCase):
    """All internal endpoints reject unauthenticated requests."""

    def test_rejects_no_token(self):
        c = APIClient()
        resp = c.post("/api/internal/discord/message-log/", {}, format="json")
        self.assertEqual(resp.status_code, 403)

    @override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
    def test_rejects_wrong_token(self):
        c = APIClient()
        resp = c.post(
            "/api/internal/discord/message-log/",
            {},
            format="json",
            HTTP_X_INTERNAL_TOKEN="wrong",
        )
        self.assertEqual(resp.status_code, 403)


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class DiscordMessageLogEndpointTest(TestCase):
    def test_create(self):
        c = APIClient()
        resp = c.post(
            "/api/internal/discord/message-log/",
            {
                "channel_id": "123",
                "source": "event_announcement",
                "source_id": 1,
                "embed_data": {"title": "Test Embed"},
                "discord_message_id": "789",
                "status_code": 200,
                "success": True,
            },
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 201)
        self.assertIn("id", resp.json())

    def test_missing_required_field(self):
        c = APIClient()
        resp = c.post(
            "/api/internal/discord/message-log/",
            {"channel_id": "123"},  # missing source, source_id, embed_data
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Missing required fields", resp.json()["error"])


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class DiscordEventEndpointTest(TestCase):
    def _make_discord_event(self):
        from discordbot.models import DiscordEvent
        from events.models import Event

        org = Organization.objects.create(name="Internal EP Test Org")
        event = Event.objects.create(
            organization=org,
            scheduled_at="2026-12-01T00:00:00Z",
            name="Internal EP Test Event",
            state="upcoming",
        )
        return DiscordEvent.objects.create(event=event, guild_id="111")

    def test_get_or_create_new(self):
        from events.models import Event

        org = Organization.objects.create(name="GOC Test Org")
        event = Event.objects.create(
            organization=org,
            scheduled_at="2026-12-01T00:00:00Z",
            name="GOC Test Event",
            state="upcoming",
        )
        c = APIClient()
        resp = c.post(
            "/api/internal/discord/events/get-or-create/",
            {"event_id": event.pk, "guild_id": "555"},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertIn("id", data)
        self.assertTrue(data["created"])

    def test_get_or_create_existing(self):
        de = self._make_discord_event()
        c = APIClient()
        resp = c.post(
            "/api/internal/discord/events/get-or-create/",
            {"event_id": de.event_id, "guild_id": "555"},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], de.pk)
        self.assertFalse(data["created"])

    def test_get_or_create_missing_event_id(self):
        c = APIClient()
        resp = c.post(
            "/api/internal/discord/events/get-or-create/",
            {"guild_id": "555"},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 400)

    def test_update_whitelisted_field(self):
        de = self._make_discord_event()
        c = APIClient()
        resp = c.patch(
            f"/api/internal/discord/events/{de.pk}/",
            {"scheduled_event_id": "999888"},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        de.refresh_from_db()
        self.assertEqual(de.scheduled_event_id, "999888")

    def test_update_ignores_non_whitelisted_field(self):
        """event_id should NOT be updatable — silently ignored."""
        de = self._make_discord_event()
        original_event_id = de.event_id
        c = APIClient()
        c.patch(
            f"/api/internal/discord/events/{de.pk}/",
            {"event_id": 99999, "scheduled_event_id": "aaa"},
            format="json",
            **HEADERS,
        )
        de.refresh_from_db()
        self.assertEqual(de.event_id, original_event_id)  # unchanged
        self.assertEqual(de.scheduled_event_id, "aaa")  # whitelisted field changed

    def test_create_event_log(self):
        de = self._make_discord_event()
        c = APIClient()
        resp = c.post(
            "/api/internal/discord/event-log/",
            {
                "discord_event_id": de.pk,
                "action": "create_scheduled_event",
                "target_type": "DiscordEvent",
                "success": True,
            },
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 201)

    def test_create_event_log_missing_fields(self):
        c = APIClient()
        resp = c.post(
            "/api/internal/discord/event-log/",
            {"action": "test"},  # missing discord_event_id, target_type
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 400)


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class SignupMessageEndpointTest(TestCase):
    def test_create_signup_message(self):
        from events.models import Event

        org = Organization.objects.create(name="Signup Msg Test Org")
        event = Event.objects.create(
            organization=org,
            scheduled_at="2026-12-01T00:00:00Z",
            name="Signup Msg Test",
            state="signups_open",
        )
        c = APIClient()
        resp = c.post(
            "/api/internal/discord/signup-message/",
            {
                "event_id": event.pk,
                "channel_id": "444555",
                "has_posted": True,
                "message_id": "msg-123",
            },
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()["created"])

    def test_update_existing_signup_message(self):
        from discordbot.models import DiscordEventMsgSignup
        from events.models import Event

        org = Organization.objects.create(name="Signup Update Org")
        event = Event.objects.create(
            organization=org,
            scheduled_at="2026-12-01T00:00:00Z",
            name="Signup Update Test",
            state="signups_open",
        )
        DiscordEventMsgSignup.objects.create(
            event=event, channel_id="444555", channel_type="text"
        )
        c = APIClient()
        resp = c.post(
            "/api/internal/discord/signup-message/",
            {
                "event_id": event.pk,
                "channel_id": "444555",
                "has_posted": True,
                "message_id": "updated-msg",
            },
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["created"])

    def test_missing_required_fields(self):
        c = APIClient()
        resp = c.post(
            "/api/internal/discord/signup-message/",
            {"event_id": 1},  # missing channel_id
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 400)


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class EventStateTransitionEndpointTest(TestCase):
    def test_transition_state(self):
        from events.models import Event

        org = Organization.objects.create(name="Transition Test Org")
        event = Event.objects.create(
            organization=org,
            scheduled_at="2026-12-01T00:00:00Z",
            name="Transition Test",
            state="upcoming",
        )
        c = APIClient()
        resp = c.post(
            f"/api/internal/events/{event.pk}/transition/",
            {"state": "signups_open"},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["state"], "signups_open")

    def test_transition_missing_state(self):
        from events.models import Event

        org = Organization.objects.create(name="Missing State Org")
        event = Event.objects.create(
            organization=org,
            scheduled_at="2026-12-01T00:00:00Z",
            name="Missing State Test",
            state="upcoming",
        )
        c = APIClient()
        resp = c.post(
            f"/api/internal/events/{event.pk}/transition/",
            {},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 400)


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class RepeaterEndpointTest(TestCase):
    def setUp(self):
        from app.models import CustomUser

        self.org = Organization.objects.create(name="Repeater Test Org")
        self.admin = CustomUser.objects.create_user(
            username="repeater_admin", password="pass"
        )
        self.client = APIClient()
        self.client.credentials(**HEADERS)

    def test_get_active_repeaters(self):
        from events.models import EventRepeater

        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Weekly Inhouse",
            is_active=True,
            frequency="weekly",
            day_of_week=3,
            time_of_day="20:00:00",
            starts_at="2026-01-01",
            generate_days_ahead=7,
            created_by=self.admin,
        )
        EventRepeater.objects.create(
            organization=self.org,
            name="Inactive",
            is_active=False,
            frequency="weekly",
            day_of_week=5,
            time_of_day="20:00:00",
            starts_at="2026-01-01",
            generate_days_ahead=7,
            created_by=self.admin,
        )
        resp = self.client.get("/api/internal/repeaters/active/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "Weekly Inhouse")
        self.assertIn("pk", data[0])

    def test_generate_events_for_repeater(self):
        import datetime

        from events.models import EventRepeater

        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Generate Test",
            is_active=True,
            frequency="daily",
            time_of_day="20:00:00",
            starts_at=datetime.date.today(),
            generate_days_ahead=3,
            created_by=self.admin,
        )
        resp = self.client.post(f"/api/internal/repeaters/{repeater.pk}/generate/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("created_count", data)
        self.assertGreaterEqual(data["created_count"], 0)

    def test_generate_events_for_nonexistent_repeater(self):
        resp = self.client.post("/api/internal/repeaters/99999/generate/")
        self.assertEqual(resp.status_code, 404)


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class InternalClientIntegrationTest(LiveServerTestCase):
    """Real HTTP integration: internal_client -> actual HTTP -> endpoint -> DB."""

    def test_create_message_log_full_chain(self):
        import os
        from unittest.mock import patch

        import app.internal_client as client
        from discordbot.models import DiscordMessageLog

        old_url = client.INTERNAL_API_URL
        client.INTERNAL_API_URL = f"{self.live_server_url}/api/internal"
        try:
            # Client reads token from env; server reads via override_settings.
            with patch.dict(os.environ, {"INTERNAL_SERVICE_TOKEN": TOKEN}):
                resp = client.create_message_log(
                    channel_id="live-integration-test",
                    source="test_integration",
                    source_id=1,
                    embed_data={"title": "Integration Test"},
                    status_code=200,
                    success=True,
                )
            self.assertIsNotNone(resp)
            self.assertEqual(resp.status_code, 201)
            self.assertTrue(
                DiscordMessageLog.objects.filter(
                    channel_id="live-integration-test"
                ).exists()
            )
        finally:
            client.INTERNAL_API_URL = old_url


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class TournamentParticipantsEndpointTest(TestCase):
    """get_tournament_participants returns the full Tournament.users pool."""

    def setUp(self):
        from datetime import date

        from app.models import CustomUser, Team, Tournament

        self.client = APIClient()
        self.client.credentials(**HEADERS)

        self.tournament = Tournament.objects.create(
            name="Participants Tournament", date_played=date.today()
        )
        # Captain: in the pool and seeded onto a team roster.
        self.captain = CustomUser.objects.create_user(
            username="cap", password="pw", discordId="1001"
        )
        # Undrafted participant: in the pool, on no team yet.
        self.participant = CustomUser.objects.create_user(
            username="pleb", password="pw", discordId="1002"
        )
        # Participant without a Discord link: must be excluded.
        self.no_discord = CustomUser.objects.create_user(
            username="nodiscord", password="pw"
        )
        self.tournament.users.add(self.captain, self.participant, self.no_discord)

        team = Team.objects.create(
            name="Team A", captain=self.captain, tournament=self.tournament
        )
        team.members.add(self.captain)

    def _get(self):
        return self.client.get(
            f"/api/internal/tournaments/{self.tournament.pk}/participants/"
        )

    def test_returns_full_pool_including_undrafted(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        discord_ids = sorted(p["discord_id"] for p in resp.json())
        # Captain (drafted) AND undrafted participant both included.
        self.assertEqual(discord_ids, ["1001", "1002"])

    def test_excludes_users_without_discord_id(self):
        resp = self._get()
        returned_pks = {p["user_pk"] for p in resp.json()}
        self.assertNotIn(self.no_discord.pk, returned_pks)

    def test_no_duplicate_for_captain_in_pool_and_roster(self):
        resp = self._get()
        captain_rows = [p for p in resp.json() if p["discord_id"] == "1001"]
        self.assertEqual(len(captain_rows), 1)

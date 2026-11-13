from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, GameMode, GameType, League, Organization, Tournament
from app.serializers import TournamentSerializer
from events.models import Event, EventRepeater


class TournamentSourceEventSerializerTest(TestCase):
    """Test that TournamentSerializer includes source_event data."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser", password="testpass"
        )
        self.org = Organization.objects.create(name="Test Org", owner=self.user)
        self.league = League.objects.create(
            name="Test League",
            organization=self.org,
            steam_league_id=99999,
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            league=self.league,
            tournament_type="double_elimination",
            date_played=timezone.now(),
        )

    def test_source_event_null_when_no_event(self):
        serializer = TournamentSerializer(self.tournament)
        self.assertIn("source_event", serializer.data)
        self.assertIsNone(serializer.data["source_event"])

    def test_source_event_with_event(self):
        repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Weekly Inhouse",
            frequency="weekly",
            day_of_week=3,
            time_of_day="19:00:00",
            starts_at="2026-01-01",
        )
        event = Event.objects.create(
            organization=self.org,
            event_repeater=repeater,
            name="Week 12 Inhouse",
            scheduled_at=timezone.now(),
            tournament=self.tournament,
        )

        serializer = TournamentSerializer(self.tournament)
        source = serializer.data["source_event"]
        self.assertIsNotNone(source)
        self.assertEqual(source["id"], event.id)
        self.assertEqual(source["name"], "Week 12 Inhouse")
        self.assertIsNotNone(source["event_repeater"])
        self.assertEqual(source["event_repeater"]["id"], repeater.id)
        self.assertEqual(source["event_repeater"]["name"], "Weekly Inhouse")

    def test_source_event_without_repeater(self):
        event = Event.objects.create(
            organization=self.org,
            name="One-off Event",
            scheduled_at=timezone.now(),
            tournament=self.tournament,
        )

        serializer = TournamentSerializer(self.tournament)
        source = serializer.data["source_event"]
        self.assertIsNotNone(source)
        self.assertEqual(source["id"], event.id)
        self.assertEqual(source["name"], "One-off Event")
        self.assertIsNone(source["event_repeater"])

    def test_source_event_includes_organization_id(self) -> None:
        Event.objects.create(
            organization=self.org,
            name="Org Event",
            scheduled_at=timezone.now(),
            tournament=self.tournament,
        )

        serializer = TournamentSerializer(self.tournament)
        self.assertEqual(
            serializer.data["source_event"]["organization_id"], self.org.pk
        )


class TournamentLobbyConfigFieldsTest(TestCase):
    def test_lobby_config_fields_serialized(self) -> None:
        tournament = Tournament.objects.create(
            name="Turbo Night",
            tournament_type="double_elimination",
            date_played=timezone.now(),
            game_mode=GameMode.TURBO,
            captains_draft_time=25,
            custom_game_name="x",
            lobby_steam_league_id=17940,
        )

        data = TournamentSerializer(tournament).data
        self.assertEqual(data["game_type"], GameType.DOTA2)
        self.assertEqual(data["game_type"], 1)
        self.assertEqual(data["game_mode"], "turbo")
        self.assertEqual(data["captains_draft_time"], 25)
        self.assertEqual(data["custom_game_name"], "x")
        self.assertEqual(data["lobby_steam_league_id"], 17940)

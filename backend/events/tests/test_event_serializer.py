from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, Organization
from events.models import Event, EventRepeater
from events.serializers import EventSerializer


class EventRepeaterNameSerializerTest(TestCase):
    """Test that EventSerializer includes event_repeater_name."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser", password="testpass"
        )
        self.org = Organization.objects.create(name="Test Org", owner=self.user)

    def test_event_repeater_name_null_when_no_repeater(self):
        event = Event.objects.create(
            organization=self.org,
            name="Standalone Event",
            scheduled_at=timezone.now(),
        )
        serializer = EventSerializer(event)
        self.assertIn("event_repeater_name", serializer.data)
        self.assertIsNone(serializer.data["event_repeater_name"])

    def test_event_repeater_name_present(self):
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
        )
        serializer = EventSerializer(event)
        self.assertEqual(serializer.data["event_repeater_name"], "Weekly Inhouse")


from datetime import timedelta

from django.test import TestCase
from django.utils import timezone as tz
from rest_framework.exceptions import ValidationError

from app.models import CustomUser, League, Organization, PositionsModel
from events.constants import EventState
from events.models import Event
from events.serializers import EventSerializer


class ValidateTournamentLeagueTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = CustomUser.objects.create_user(username="vt_owner", password="x")
        cls.owner.positions = PositionsModel.objects.create()
        cls.owner.save()
        cls.org_a = Organization.objects.create(name="Org A", owner=cls.owner)
        cls.org_b = Organization.objects.create(name="Org B", owner=cls.owner)
        cls.league_a = League.objects.create(
            name="League A",
            organization=cls.org_a,
            steam_league_id=20001,
        )
        cls.league_a_alt = League.objects.create(
            name="League A Alt",
            organization=cls.org_a,
            steam_league_id=20002,
        )
        cls.league_b = League.objects.create(
            name="League B",
            organization=cls.org_b,
            steam_league_id=20003,
        )
        cls.event = Event.objects.create(
            organization=cls.org_a,
            name="VT Event",
            scheduled_at=tz.now() + timedelta(days=1),
            state=EventState.SIGNUPS_OPEN,
            created_by=cls.owner,
            tournament_name="T",
            tournament_league=cls.league_a,
        )

    def _validate(self, league, instance=None, initial_data=None):
        serializer = EventSerializer(instance=instance, data=initial_data or {})
        if initial_data is not None:
            serializer.initial_data = initial_data
        return serializer.validate_tournament_league(league)

    def test_accepts_same_org_league(self):
        result = self._validate(self.league_a_alt, instance=self.event)
        self.assertEqual(result, self.league_a_alt)

    def test_rejects_different_org_league(self):
        with self.assertRaises(ValidationError):
            self._validate(self.league_b, instance=self.event)

    def test_accepts_none(self):
        result = self._validate(None, instance=self.event)
        self.assertIsNone(result)

    def test_create_path_rejects_org_mismatch(self):
        with self.assertRaises(ValidationError):
            self._validate(
                self.league_b,
                instance=None,
                initial_data={"organization": self.org_a.pk},
            )

    def test_create_path_accepts_same_org(self):
        result = self._validate(
            self.league_a_alt,
            instance=None,
            initial_data={"organization": self.org_a.pk},
        )
        self.assertEqual(result, self.league_a_alt)

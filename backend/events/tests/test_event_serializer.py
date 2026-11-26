from datetime import time, timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone
from django.utils import timezone as tz
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser
from events.constants import EventState, RepeatFrequency
from events.models import Event, EventRepeater, OrgEventDefaults
from events.serializers import (
    EventRepeaterSerializer,
    EventSerializer,
    OneOffEventCreateSerializer,
    OrgEventDefaultsSerializer,
)
from events.tests.base import EventTestCase
from league.models import League
from org.models import Organization
from user.models import PositionsModel


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


class SignupOpenPolicyFieldsTest(TestCase):
    def test_policy_fields_on_all_config_serializers(self) -> None:
        for serializer in (
            EventSerializer,
            EventRepeaterSerializer,
            OrgEventDefaultsSerializer,
            OneOffEventCreateSerializer,
        ):
            for field in ("signup_open_mode", "signups_open_hours_before"):
                self.assertIn(field, serializer.Meta.fields, serializer.__name__)


POST_CHANNEL_FIELDS = (
    "discord_confirm_attendance_channel_id",
    "discord_profile_reminder_channel_id",
    "discord_new_event_channel_id",
)


class PostChannelFieldsTest(EventTestCase):
    TARGETS = ("event", "series", "defaults")

    def setUp(self) -> None:
        self.repeater = EventRepeater.objects.create(
            organization=self.org,
            name="Weekly",
            frequency=RepeatFrequency.DAILY,
            time_of_day=time(20, 0),
            timezone="UTC",
            starts_at=tz.now().date() + timedelta(days=30),
            created_by=self.admin,
        )
        self.defaults, _ = OrgEventDefaults.objects.get_or_create(organization=self.org)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _url(self, target: str) -> str:
        if target == "event":
            return f"/api/events/{self.event.pk}/"
        if target == "series":
            return f"/api/events/repeaters/{self.repeater.pk}/"
        return f"/api/events/defaults/{self.defaults.pk}/"

    def _get(self, target: str) -> Response:
        if target == "defaults":
            return self.client.get(
                "/api/events/defaults/", {"organization": self.org.pk}
            )
        return self.client.get(self._url(target))

    def test_post_channel_fields_on_all_config_serializers(self) -> None:
        for serializer in (
            EventSerializer,
            EventRepeaterSerializer,
            OrgEventDefaultsSerializer,
            OneOffEventCreateSerializer,
        ):
            for field in POST_CHANNEL_FIELDS:
                self.assertIn(field, serializer.Meta.fields, serializer.__name__)

    @patch("events.services.notify_create_discord_event", MagicMock())
    @patch("events.services.notify_new_event", MagicMock())
    def test_post_channel_fields_round_trip(self) -> None:
        for target in self.TARGETS:
            for field in POST_CHANNEL_FIELDS:
                for value in ("123456789012345678", ""):
                    with self.subTest(target=target, field=field, value=value):
                        url = self._url(target)
                        resp = self.client.patch(url, {field: value}, format="json")
                        self.assertEqual(resp.status_code, 200, resp.content)
                        self.assertEqual(resp.data[field], value)
                        got = self._get(target)
                        self.assertEqual(got.status_code, 200, got.content)
                        self.assertEqual(got.data[field], value)

    @patch("events.services.notify_create_discord_event", MagicMock())
    @patch("events.services.notify_new_event", MagicMock())
    def test_post_channel_fields_reject_invalid_id(self) -> None:
        for target in self.TARGETS:
            for field in POST_CHANNEL_FIELDS:
                for value in ("abc", "1" * 21):
                    with self.subTest(target=target, field=field, value=value):
                        resp = self.client.patch(
                            self._url(target), {field: value}, format="json"
                        )
                        self.assertEqual(resp.status_code, 400, resp.content)
                        self.assertIn(field, resp.data)

    @patch("events.services.notify_create_discord_event", MagicMock())
    @patch("events.services.notify_new_event", MagicMock())
    def test_one_off_create_accepts_post_channels(self) -> None:
        resp = self.client.post(
            f"/api/events/repeaters/{self.repeater.pk}/create-event/",
            {
                "scheduled_at": (tz.now() + timedelta(days=3)).isoformat(),
                "discord_confirm_attendance_channel_id": "123456789012345678",
            },
            format="json",
        )
        self.assertIn(resp.status_code, (200, 201), resp.content)
        event = Event.objects.get(pk=resp.data["id"])
        self.assertEqual(
            event.discord_confirm_attendance_channel_id, "123456789012345678"
        )

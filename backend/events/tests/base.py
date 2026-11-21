import itertools
from datetime import timedelta
from typing import ClassVar

from django.test import TestCase
from django.utils import timezone as tz

from app.models import CustomUser, League, PositionsModel
from events.constants import EventState
from events.models import Event
from org.models import Organization, OrgUser

_helper_ids = itertools.count(1)


class EventTestCase(TestCase):
    """Shared setUp for all events tests."""

    org: ClassVar[Organization]
    admin: ClassVar[CustomUser]

    @classmethod
    def setUpTestData(cls):
        cls.positions = PositionsModel.objects.create()
        cls.admin = CustomUser.objects.create_user(
            username="event_admin", password="testpass"
        )
        cls.admin.positions = cls.positions
        cls.admin.steamid = 76561198000000001
        cls.admin.discordId = "123456789"
        cls.admin.nickname = "EventAdmin"
        cls.admin.has_active_dota_mmr = True
        cls.admin.save()

        cls.user = CustomUser.objects.create_user(
            username="event_user", password="testpass"
        )
        cls.user.positions = PositionsModel.objects.create()
        cls.user.steamid = 76561198000000002
        cls.user.discordId = "987654321"
        cls.user.nickname = "EventUser"
        cls.user.save()

        cls.user_incomplete = CustomUser.objects.create_user(
            username="incomplete_user", password="testpass"
        )
        cls.user_incomplete.positions = PositionsModel.objects.create()
        cls.user_incomplete.save()

        cls.league_staff = CustomUser.objects.create_user(
            username="event_league_staff", password="testpass"
        )
        cls.league_staff.positions = PositionsModel.objects.create()
        cls.league_staff.save()

        cls.unrelated_user = CustomUser.objects.create_user(
            username="event_unrelated", password="testpass"
        )
        cls.unrelated_user.positions = PositionsModel.objects.create()
        cls.unrelated_user.save()

        cls.org = Organization.objects.create(name="Event Test Org", owner=cls.admin)
        cls.org.staff.add(cls.admin)

        cls.league = League.objects.create(
            name="Event Test League",
            organization=cls.org,
            steam_league_id=99999,
        )
        cls.league.staff.add(cls.league_staff)

        cls.event = Event.objects.create(
            organization=cls.org,
            name="Test Event",
            description="A test event for unit tests.",
            scheduled_at=tz.now() + timedelta(days=7),
            state=EventState.SIGNUPS_OPEN,
            created_by=cls.admin,
            tournament_name="Test Event Tourney",
            tournament_league=cls.league,
            max_players=10,
            require_steam_id=True,
            require_mmr_verified=True,
            require_profile_complete=True,
        )

    def make_event(self, **overrides: object) -> Event:
        fields: dict[str, object] = {
            "organization": self.org,
            "name": f"Helper Event {next(_helper_ids)}",
            "scheduled_at": tz.now() + timedelta(days=7),
            "state": EventState.SIGNUPS_OPEN,
            "created_by": self.admin,
            "auto_approve": True,
            "require_steam_id": False,
            "require_mmr_verified": False,
            "require_profile_complete": False,
        }
        fields.update(overrides)
        return Event.objects.create(**fields)

    def make_user(self, *, steamid: int | None = None) -> CustomUser:
        user = CustomUser.objects.create_user(
            username=f"helper_user_{next(_helper_ids)}", password="testpass"
        )
        if steamid is not None:
            user.steamid = steamid
            user.save()
        OrgUser.objects.get_or_create(user=user, organization=self.org)
        return user

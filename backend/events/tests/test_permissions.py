from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.utils import timezone as tz

from app.models import CustomUser, League, Organization, PositionsModel
from app.permissions_org import has_event_staff_access
from events.constants import EventState
from events.models import Event


class HasEventStaffAccessTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org_staff = CustomUser.objects.create_user(username="org_staff_p", password="x")
        cls.league_staff = CustomUser.objects.create_user(username="league_staff_p", password="x")
        cls.unrelated = CustomUser.objects.create_user(username="unrelated_p", password="x")
        cls.owner = CustomUser.objects.create_user(username="owner_p", password="x")
        for u in (cls.org_staff, cls.league_staff, cls.unrelated, cls.owner):
            u.positions = PositionsModel.objects.create()
            u.save()

        cls.org = Organization.objects.create(name="Perm Test Org", owner=cls.owner)
        cls.org.staff.add(cls.org_staff)
        cls.league = League.objects.create(name="Perm Test League", organization=None, steam_league_id=88888)
        cls.league.staff.add(cls.league_staff)

        cls.event_with_league = Event.objects.create(
            organization=cls.org,
            name="With League",
            scheduled_at=tz.now() + timedelta(days=1),
            state=EventState.ROLL_CALL,
            created_by=cls.owner,
            tournament_name="T",
            tournament_league=cls.league,
        )
        cls.event_no_league = Event.objects.create(
            organization=cls.org,
            name="No League",
            scheduled_at=tz.now() + timedelta(days=1),
            state=EventState.ROLL_CALL,
            created_by=cls.owner,
            tournament_name="T",
        )

    def test_org_staff_has_access(self):
        assert has_event_staff_access(self.org_staff, self.event_with_league)
        assert has_event_staff_access(self.org_staff, self.event_no_league)

    def test_league_staff_has_access_when_league_set(self):
        assert has_event_staff_access(self.league_staff, self.event_with_league)

    def test_league_staff_has_no_access_when_no_league_on_event(self):
        assert not has_event_staff_access(self.league_staff, self.event_no_league)

    def test_unrelated_user_denied(self):
        assert not has_event_staff_access(self.unrelated, self.event_with_league)
        assert not has_event_staff_access(self.unrelated, self.event_no_league)

    def test_anonymous_denied(self):
        assert not has_event_staff_access(AnonymousUser(), self.event_with_league)

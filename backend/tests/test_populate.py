"""
Populate guard regression tests.

These tests assert invariants of the test-data populate pipeline that, if
broken, would silently invalidate Playwright auth fixtures and event-staff
permission specs.
"""

from django.test import TestCase

from app.models import CustomUser, League, Organization
from tests.data.leagues import EVENTS_LEAGUE
from tests.data.organizations import EVENTS_ORG
from tests.data.users import EVENT_LEAGUE_STAFF_USER


class EventLeagueStaffIsolationTest(TestCase):
    """Regression guard: event_league_staff must be staff of league 7 only,
    never of org 7. Used by Playwright tests to assert league-staff-only
    access on event pages.
    """

    @classmethod
    def setUpTestData(cls):
        from tests.populate.events import populate_events_data
        from tests.populate.organizations import populate_organizations_and_leagues
        from tests.populate.users import populate_test_auth_users

        # Run populate dependencies in order. populate_events_data creates
        # league pk=7 and is responsible for the league.staff assignment.
        populate_organizations_and_leagues(force=True)
        populate_test_auth_users(force=True)
        populate_events_data(force=True)

    def test_event_league_staff_isolation(self):
        user = CustomUser.objects.get(pk=EVENT_LEAGUE_STAFF_USER.pk)
        league = League.objects.get(pk=EVENTS_LEAGUE.pk)
        org = Organization.objects.get(pk=EVENTS_ORG.pk)

        assert user in league.staff.all(), "Should be staff of league 7"
        assert user not in org.staff.all(), "MUST NOT be staff of org 7"
        assert user not in org.admins.all(), "MUST NOT be admin of org 7"

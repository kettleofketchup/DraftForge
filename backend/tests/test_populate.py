"""
Populate guard regression tests.

These tests assert invariants of the test-data populate pipeline that, if
broken, would silently invalidate Playwright auth fixtures and event-staff
permission specs.
"""

from django.test import TestCase, override_settings

from app.models import CustomUser, Draft, DraftRound, League, Organization
from tests.data.leagues import EVENTS_LEAGUE
from tests.data.organizations import EVENTS_ORG
from tests.helpers.tournament_config import populate_test_tournaments
from tests.populate.demo import (
    populate_demo_shuffle_draft_tournament,
    populate_demo_snake_draft_tournament,
)
from tests.populate.organizations import populate_organizations_and_leagues
from tests.populate.shuffle_tie import populate_shuffle_tie_data
from tests.populate.users import populate_test_auth_users, populate_users
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


class PopulateBuiltDraftsAreUntimedTest(TestCase):
    @classmethod
    @override_settings(DISCORD_BOT_TOKEN=None, DEBUG=True)
    def setUpTestData(cls):
        populate_organizations_and_leagues(force=True)
        populate_users(force=True)
        populate_test_auth_users(force=True)
        populate_test_tournaments(force=True)
        populate_shuffle_tie_data(force=True)
        populate_demo_snake_draft_tournament(force=True)
        populate_demo_shuffle_draft_tournament(force=True)

    def test_every_populate_draft_without_opt_in_is_drafting_and_unarmed(self):
        checked = 0
        for draft in Draft.objects.select_related("tournament").all():
            if not draft.draft_rounds.exists() or draft.tournament.get_draft_options().timer_enabled:
                continue
            checked += 1
            finished = not draft.draft_rounds.filter(choice__isnull=True).exists()
            expected = "completed" if finished else "drafting"
            self.assertEqual(draft.state, expected, draft.tournament.name)
            self.assertFalse(DraftRound.objects.filter(draft=draft, started_at__isnull=False).exists(), draft.tournament.name)
        self.assertGreaterEqual(checked, 6)

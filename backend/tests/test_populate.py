"""
Populate guard regression tests.

These tests assert invariants of the test-data populate pipeline that, if
broken, would silently invalidate Playwright auth fixtures and event-staff
permission specs.
"""

from rest_framework.test import APIRequestFactory
from django.test import TestCase, override_settings

from app.models import CustomUser, Draft, DraftRound, League, Organization
from tests.data.leagues import EVENTS_LEAGUE
from tests.data.organizations import EVENTS_ORG
from tests.helpers.tournament_config import TEST_TOURNAMENTS, populate_test_tournaments
from tests.populate.demo import (
    populate_demo_shuffle_draft_tournament,
    populate_demo_snake_draft_tournament,
)
from tests.populate.organizations import populate_organizations_and_leagues
from tests.populate.shuffle_tie import populate_shuffle_tie_data
from tests.populate.users import populate_test_auth_users, populate_users
from tests.test_auth import reset_tournament_by_key
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


TIMER_KEYS: list[str] = [
    "draft_timer_ready",
    "draft_timer_countdown",
    "draft_timer_skip",
    "draft_timer_pause",
    "shuffle_timer_skip",
]


class PopulateTimerLobbiesTest(TestCase):
    @classmethod
    @override_settings(DISCORD_BOT_TOKEN=None, DEBUG=True)
    def setUpTestData(cls) -> None:
        populate_organizations_and_leagues(force=True)
        populate_users(force=True)
        populate_test_auth_users(force=True)
        populate_test_tournaments(force=True)
        populate_shuffle_tie_data(force=True)
        populate_demo_snake_draft_tournament(force=True)
        populate_demo_shuffle_draft_tournament(force=True)

    def test_only_the_five_timer_lobbies_are_pending_with_rounds(self) -> None:
        names = sorted(
            Draft.objects.filter(state="pending", draft_rounds__isnull=False)
            .distinct()
            .values_list("tournament__name", flat=True)
        )
        expected = sorted(c.name for c in TEST_TOURNAMENTS if c.key in TIMER_KEYS)
        self.assertEqual(len(expected), 5)
        self.assertEqual(names, expected)

    @override_settings(DEBUG=True)
    def test_reset_tournament_by_key_rebuilds_each_timer_lobby(self) -> None:
        factory = APIRequestFactory()
        for key in TIMER_KEYS:
            config = next(c for c in TEST_TOURNAMENTS if c.key == key)
            response = reset_tournament_by_key(factory.post(f"/api/tests/reset-tournament/{key}/"), key)
            self.assertEqual(response.status_code, 200, key)
            draft = Draft.objects.get(tournament__name=config.name)
            self.assertEqual(draft.state, "pending", key)
            opts = draft.tournament.get_draft_options(fresh=True)
            self.assertEqual(
                (opts.timer_enabled, opts.grace_time_ms, opts.reserve_time_ms),
                (True, config.grace_time_ms, config.reserve_time_ms),
                key,
            )

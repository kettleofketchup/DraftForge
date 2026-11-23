from django.test import TestCase, override_settings
from django.urls import resolve, reverse
from rest_framework.test import APIClient, APIRequestFactory

from league.models import League
from tests.helpers.team_management_fixture import (
    TEAM_MANAGEMENT_GHOST,
    TEAM_MANAGEMENT_SEARCH_TARGET,
    TEAM_MANAGEMENT_TOURNAMENT_NAME,
    TEAM_MANAGEMENT_USER_PREFIX,
    populate_team_management_tournament,
)
from tests.populate.constants import DTX_STEAM_LEAGUE_ID
from tests.populate.organizations import populate_organizations_and_leagues
from tests.test_auth import reset_tournament_by_key
from tournament.models import Team, Tournament


class TeamManagementFixtureTests(TestCase):
    def setUp(self) -> None:
        populate_organizations_and_leagues()

    def build(self) -> Tournament:
        populate_team_management_tournament(force=True)
        return populate_team_management_tournament(force=True)

    def team(self, tournament: Tournament, name: str) -> Team:
        return Team.objects.nocache().get(tournament=tournament, name=name)

    def test_force_rebuild_leaves_one_tournament_on_dtx_league(self) -> None:
        tournament = self.build()
        matches = Tournament.objects.nocache().filter(
            name=TEAM_MANAGEMENT_TOURNAMENT_NAME
        )
        self.assertEqual(matches.count(), 1)
        self.assertEqual(tournament.league.steam_league_id, DTX_STEAM_LEAGUE_ID)
        self.assertEqual(
            sorted(tournament.teams.values_list("name", flat=True)),
            ["TM Alpha", "TM Bravo", "TM Ghost"],
        )

    def test_users_are_prefixed_tournament_users(self) -> None:
        tournament = self.build()
        users = list(tournament.users.values_list("username", flat=True))
        self.assertTrue(users)
        self.assertTrue(all(u.startswith(TEAM_MANAGEMENT_USER_PREFIX) for u in users))
        rostered = {
            pk
            for team in tournament.teams.all()
            for pk in [
                *team.members.values_list("pk", flat=True),
                *team.dropin_members.values_list("pk", flat=True),
            ]
        }
        self.assertTrue(rostered <= set(tournament.users.values_list("pk", flat=True)))

    def test_ghost_captain_is_on_no_team(self) -> None:
        tournament = self.build()
        ghost_team = self.team(tournament, "TM Ghost")
        self.assertEqual(ghost_team.captain.username, TEAM_MANAGEMENT_GHOST)
        self.assertFalse(ghost_team.members.filter(pk=ghost_team.captain_id).exists())
        self.assertTrue(tournament.users.filter(pk=ghost_team.captain_id).exists())
        on_teams = Team.objects.nocache().filter(tournament=tournament)
        self.assertFalse(on_teams.filter(members=ghost_team.captain_id).exists())
        self.assertFalse(on_teams.filter(dropin_members=ghost_team.captain_id).exists())

    def test_alpha_and_bravo_rosters(self) -> None:
        tournament = self.build()
        alpha = self.team(tournament, "TM Alpha")
        bravo = self.team(tournament, "TM Bravo")
        self.assertEqual(alpha.members.count(), 5)
        self.assertTrue(alpha.members.filter(pk=alpha.captain_id).exists())
        self.assertTrue(alpha.members.filter(pk=alpha.deputy_captain_id).exists())
        self.assertNotEqual(alpha.captain_id, alpha.deputy_captain_id)
        self.assertEqual(bravo.members.count(), 5)
        self.assertEqual(bravo.dropin_members.count(), 1)

    def test_search_target_is_tournament_user_on_no_team(self) -> None:
        tournament = self.build()
        target = tournament.users.get(username=TEAM_MANAGEMENT_SEARCH_TARGET)
        teams = Team.objects.nocache().filter(tournament=tournament)
        self.assertFalse(teams.filter(members=target).exists())
        self.assertFalse(teams.filter(dropin_members=target).exists())

    def test_api_reports_ghost_captain(self) -> None:
        tournament = self.build()
        resp = APIClient().get(reverse("tournaments-detail", args=[tournament.pk]))
        self.assertEqual(resp.status_code, 200, resp.content)
        problems = {
            row["name"]: [p["code"] for p in row["leadership_problems"]]
            for row in resp.json()["teams"]
        }
        self.assertEqual(problems["TM Ghost"], ["captain_not_member"])
        self.assertEqual(problems["TM Alpha"], [])
        self.assertEqual(problems["TM Bravo"], [])

    def test_missing_dtx_league_raises(self) -> None:
        League.objects.filter(steam_league_id=DTX_STEAM_LEAGUE_ID).delete()
        with self.assertRaises(League.DoesNotExist):
            populate_team_management_tournament(force=True)

    @override_settings(DEBUG=True, TEST=True, RELEASE=False)
    def test_reset_endpoint_rebuilds_fixture(self) -> None:
        path = reverse(
            "test-reset-tournament", urlconf="tests.urls", args=["team_management"]
        )
        match = resolve(path, urlconf="tests.urls")
        self.assertIs(match.func, reset_tournament_by_key)
        request = APIRequestFactory().post(f"/api/tests{path}")
        for _ in range(2):
            resp = match.func(request, **match.kwargs)
            self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["name"], TEAM_MANAGEMENT_TOURNAMENT_NAME)
        self.assertEqual(
            sorted(team["name"] for team in resp.data["teams"]),
            ["TM Alpha", "TM Bravo", "TM Ghost"],
        )

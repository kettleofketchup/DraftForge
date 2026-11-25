from django.test import TestCase, override_settings
from django.urls import resolve, reverse
from rest_framework.test import APIRequestFactory

from tests.data.tournaments import PLACEMENT_REOPEN_CONFLICT_TOURNAMENT
from tests.populate.bracket import populate_placement_reopen_conflict_tournament
from tests.populate.organizations import populate_organizations_and_leagues
from tests.test_auth import reset_tournament_by_key
from tournament.models import Game, Team, Tournament
from tournament.services.team_management import live_conflicts


class PlacementReopenConflictFixtureTests(TestCase):
    def setUp(self) -> None:
        populate_organizations_and_leagues()

    def team(self, tournament: Tournament, index: int) -> Team:
        name = PLACEMENT_REOPEN_CONFLICT_TOURNAMENT.teams[index].name
        return Team.objects.nocache().get(tournament=tournament, name=name)

    def game(self, tournament: Tournament, round_: int, position: int) -> Game:
        return Game.objects.nocache().get(
            tournament=tournament, round=round_, position=position
        )

    def test_fixture_state(self) -> None:
        populate_placement_reopen_conflict_tournament(force=True)
        tournament = populate_placement_reopen_conflict_tournament(force=True)
        self.assertEqual(
            Tournament.objects.nocache()
            .filter(name=PLACEMENT_REOPEN_CONFLICT_TOURNAMENT.name)
            .count(),
            1,
        )
        a, b, c, d = (self.team(tournament, i) for i in range(4))
        self.assertEqual(a.placement, 3)
        self.assertEqual([b.placement, c.placement, d.placement], [None, None, None])

        semi1 = self.game(tournament, 1, 0)
        self.assertEqual(semi1.status, "completed")
        self.assertEqual(
            (semi1.radiant_team_id, semi1.dire_team_id, semi1.winning_team_id),
            (a.pk, b.pk, b.pk),
        )
        semi2 = self.game(tournament, 1, 1)
        self.assertEqual(semi2.status, "pending")
        self.assertEqual((semi2.radiant_team_id, semi2.dire_team_id), (c.pk, d.pk))
        final = self.game(tournament, 2, 0)
        self.assertEqual(final.radiant_team_id, b.pk)
        self.assertIsNone(final.dire_team_id)

        self.assertEqual(
            [u.username for u in live_conflicts(a)], ["reopen_conflict_a2"]
        )

    @override_settings(DEBUG=True, TEST=True, RELEASE=False)
    def test_reset_endpoint_rebuilds_fixture(self) -> None:
        path = reverse(
            "test-reset-tournament",
            urlconf="tests.urls",
            args=["placement_reopen_conflict"],
        )
        match = resolve(path, urlconf="tests.urls")
        self.assertIs(match.func, reset_tournament_by_key)
        request = APIRequestFactory().post(f"/api/tests{path}")
        for _ in range(2):
            resp = match.func(request, **match.kwargs)
            self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["name"], PLACEMENT_REOPEN_CONFLICT_TOURNAMENT.name)

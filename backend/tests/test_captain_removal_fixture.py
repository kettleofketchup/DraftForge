from django.test import TestCase

from tests.helpers.captain_removal_fixture import (
    CAPTAIN_REMOVAL_FRESH_TEAM,
    CAPTAIN_REMOVAL_PLAYED_TEAM,
    CAPTAIN_REMOVAL_TOURNAMENT_NAME,
    populate_captain_removal_tournament,
)
from tests.populate.organizations import populate_organizations_and_leagues
from tournament.models import Game, Team, Tournament


class CaptainRemovalFixtureTests(TestCase):
    def setUp(self) -> None:
        populate_organizations_and_leagues()

    def test_force_rebuild_leaves_one_played_and_one_fresh_team(self) -> None:
        populate_captain_removal_tournament(force=True)
        tournament = populate_captain_removal_tournament(force=True)

        self.assertEqual(
            Tournament.objects.filter(name=CAPTAIN_REMOVAL_TOURNAMENT_NAME).count(), 1
        )
        played = Team.objects.get(
            tournament=tournament, name=CAPTAIN_REMOVAL_PLAYED_TEAM
        )
        fresh = Team.objects.get(tournament=tournament, name=CAPTAIN_REMOVAL_FRESH_TEAM)
        self.assertEqual(played.placement, 3)
        self.assertTrue(Game.objects.filter(radiant_team=played).exists())
        self.assertEqual(
            list(fresh.members.values_list("pk", flat=True)), [fresh.captain_id]
        )

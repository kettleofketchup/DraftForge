from datetime import date

from django.test import TestCase

from app.models import (
    CustomUser,
    DraftTeam,
    Game,
    HeroDraft,
    HeroDraftEvent,
    HeroDraftRound,
    Team,
    Tournament,
)


class HeroDraftModelTest(TestCase):
    def setUp(self):
        self.user1 = CustomUser.objects.create_user(
            username="captain1", password="test"
        )
        self.user2 = CustomUser.objects.create_user(
            username="captain2", password="test"
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        self.team1 = Team.objects.create(
            name="Team 1",
            tournament=self.tournament,
            captain=self.user1,
        )
        self.team2 = Team.objects.create(
            name="Team 2",
            tournament=self.tournament,
            captain=self.user2,
        )
        self.game = Game.objects.create(
            tournament=self.tournament, radiant_team=self.team1, dire_team=self.team2
        )

    def test_create_herodraft(self):
        """HeroDraft can be created and linked to a game."""
        draft = HeroDraft.objects.create(game=self.game)
        self.assertEqual(draft.state, "waiting_for_captains")
        self.assertIsNone(draft.roll_winner)
        self.assertEqual(draft.game, self.game)

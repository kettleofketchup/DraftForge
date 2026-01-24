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


class DraftTeamModelTest(TestCase):
    def setUp(self):
        self.user1 = CustomUser.objects.create_user(
            username="captain1", password="test"
        )
        self.user2 = CustomUser.objects.create_user(
            username="captain2", password="test"
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played=date.today()
        )
        self.team1 = Team.objects.create(
            name="Team 1", tournament=self.tournament, captain=self.user1
        )
        self.team2 = Team.objects.create(
            name="Team 2", tournament=self.tournament, captain=self.user2
        )
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
        )
        self.draft = HeroDraft.objects.create(game=self.game)

    def test_create_draft_team(self):
        """DraftTeam can be created with default values."""
        draft_team = DraftTeam.objects.create(
            draft=self.draft,
            tournament_team=self.team1,
        )
        self.assertEqual(draft_team.reserve_time_remaining, 90000)
        self.assertFalse(draft_team.is_ready)
        self.assertFalse(draft_team.is_connected)
        self.assertIsNone(draft_team.is_first_pick)
        self.assertIsNone(draft_team.is_radiant)

    def test_captain_property(self):
        """DraftTeam.captain returns the tournament team's captain."""
        draft_team = DraftTeam.objects.create(
            draft=self.draft,
            tournament_team=self.team1,
        )
        self.assertEqual(draft_team.captain, self.user1)


class HeroDraftRoundModelTest(TestCase):
    def setUp(self):
        self.user1 = CustomUser.objects.create_user(
            username="captain1", password="test"
        )
        self.user2 = CustomUser.objects.create_user(
            username="captain2", password="test"
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played=date.today()
        )
        self.team1 = Team.objects.create(
            name="Team 1", tournament=self.tournament, captain=self.user1
        )
        self.team2 = Team.objects.create(
            name="Team 2", tournament=self.tournament, captain=self.user2
        )
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
        )
        self.draft = HeroDraft.objects.create(game=self.game)
        self.draft_team = DraftTeam.objects.create(
            draft=self.draft,
            tournament_team=self.team1,
        )

    def test_create_round(self):
        """HeroDraftRound can be created."""
        round = HeroDraftRound.objects.create(
            draft=self.draft,
            draft_team=self.draft_team,
            round_number=1,
            action_type="ban",
        )
        self.assertEqual(round.state, "planned")
        self.assertEqual(round.grace_time_ms, 30000)
        self.assertIsNone(round.hero_id)

    def test_rounds_ordered_by_number(self):
        """Rounds are ordered by round_number."""
        r3 = HeroDraftRound.objects.create(
            draft=self.draft,
            draft_team=self.draft_team,
            round_number=3,
            action_type="pick",
        )
        r1 = HeroDraftRound.objects.create(
            draft=self.draft,
            draft_team=self.draft_team,
            round_number=1,
            action_type="ban",
        )
        r2 = HeroDraftRound.objects.create(
            draft=self.draft,
            draft_team=self.draft_team,
            round_number=2,
            action_type="ban",
        )
        rounds = list(self.draft.rounds.all())
        self.assertEqual([r.round_number for r in rounds], [1, 2, 3])

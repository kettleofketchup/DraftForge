"""Tests for shuffle draft logic."""

from datetime import date
from unittest.mock import patch

from django.test import TestCase

from app.models import CustomUser, Draft, DraftRound, Team, Tournament


class GetTeamTotalMmrTest(TestCase):
    """Test get_team_total_mmr function."""

    def setUp(self):
        """Create test data."""
        self.captain = CustomUser.objects.create_user(
            username="captain1",
            password="test123",
            mmr=5000,
        )
        self.member1 = CustomUser.objects.create_user(
            username="member1",
            password="test123",
            mmr=4000,
        )
        self.member2 = CustomUser.objects.create_user(
            username="member2",
            password="test123",
            mmr=3500,
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        self.team = Team.objects.create(
            name="Test Team",
            captain=self.captain,
            tournament=self.tournament,
        )
        self.team.members.add(self.captain, self.member1, self.member2)

    def test_calculates_total_mmr(self):
        """Total MMR = captain + all members (excluding captain duplicate)."""
        from app.functions.shuffle_draft import get_team_total_mmr

        result = get_team_total_mmr(self.team)

        # 5000 (captain) + 4000 (member1) + 3500 (member2) = 12500
        self.assertEqual(result, 12500)

    def test_handles_null_mmr(self):
        """Members with null MMR contribute 0."""
        from app.functions.shuffle_draft import get_team_total_mmr

        self.member2.mmr = None
        self.member2.save()

        result = get_team_total_mmr(self.team)

        # 5000 + 4000 + 0 = 9000
        self.assertEqual(result, 9000)


class RollUntilWinnerTest(TestCase):
    """Test roll_until_winner function."""

    def setUp(self):
        """Create test teams."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played=date.today()
        )
        self.captain1 = CustomUser.objects.create_user(
            username="cap1", password="test", mmr=5000
        )
        self.captain2 = CustomUser.objects.create_user(
            username="cap2", password="test", mmr=5000
        )
        self.team1 = Team.objects.create(
            name="Team 1", captain=self.captain1, tournament=self.tournament
        )
        self.team2 = Team.objects.create(
            name="Team 2", captain=self.captain2, tournament=self.tournament
        )

    @patch("app.functions.shuffle_draft.random.randint")
    def test_returns_winner_on_first_roll(self, mock_randint):
        """First team wins if they roll higher."""
        from app.functions.shuffle_draft import roll_until_winner

        mock_randint.side_effect = [6, 3]  # Team1 rolls 6, Team2 rolls 3

        winner, roll_rounds = roll_until_winner([self.team1, self.team2])

        self.assertEqual(winner.pk, self.team1.pk)
        self.assertEqual(len(roll_rounds), 1)
        self.assertEqual(roll_rounds[0][0]["roll"], 6)
        self.assertEqual(roll_rounds[0][1]["roll"], 3)

    @patch("app.functions.shuffle_draft.random.randint")
    def test_rerolls_on_tie(self, mock_randint):
        """Re-rolls when teams tie."""
        from app.functions.shuffle_draft import roll_until_winner

        # First round: tie (4, 4), Second round: team2 wins (2, 5)
        mock_randint.side_effect = [4, 4, 2, 5]

        winner, roll_rounds = roll_until_winner([self.team1, self.team2])

        self.assertEqual(winner.pk, self.team2.pk)
        self.assertEqual(len(roll_rounds), 2)


class GetLowestMmrTeamTest(TestCase):
    """Test get_lowest_mmr_team function."""

    def setUp(self):
        """Create test teams with different MMRs."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played=date.today()
        )

        self.captain1 = CustomUser.objects.create_user(
            username="cap1", password="test", mmr=5000
        )
        self.captain2 = CustomUser.objects.create_user(
            username="cap2", password="test", mmr=4000
        )
        self.captain3 = CustomUser.objects.create_user(
            username="cap3", password="test", mmr=6000
        )

        self.team1 = Team.objects.create(
            name="Team 1", captain=self.captain1, tournament=self.tournament
        )
        self.team1.members.add(self.captain1)

        self.team2 = Team.objects.create(
            name="Team 2", captain=self.captain2, tournament=self.tournament
        )
        self.team2.members.add(self.captain2)

        self.team3 = Team.objects.create(
            name="Team 3", captain=self.captain3, tournament=self.tournament
        )
        self.team3.members.add(self.captain3)

    def test_returns_lowest_mmr_team(self):
        """Returns team with lowest total MMR."""
        from app.functions.shuffle_draft import get_lowest_mmr_team

        teams = [self.team1, self.team2, self.team3]
        winner, tie_data = get_lowest_mmr_team(teams)

        self.assertEqual(winner.pk, self.team2.pk)  # 4000 MMR
        self.assertIsNone(tie_data)

    @patch("app.functions.shuffle_draft.roll_until_winner")
    def test_handles_tie_with_roll(self, mock_roll):
        """Calls roll_until_winner when teams tie."""
        from app.functions.shuffle_draft import get_lowest_mmr_team

        # Make team1 and team2 have same MMR
        self.captain1.mmr = 4000
        self.captain1.save()

        mock_roll.return_value = (self.team1, [[{"team_id": self.team1.id, "roll": 5}]])

        teams = [self.team1, self.team2, self.team3]
        winner, tie_data = get_lowest_mmr_team(teams)

        self.assertEqual(winner.pk, self.team1.pk)
        self.assertIsNotNone(tie_data)
        self.assertEqual(len(tie_data["tied_teams"]), 2)
        mock_roll.assert_called_once()


class BuildShuffleRoundsTest(TestCase):
    """Test build_shuffle_rounds function."""

    def setUp(self):
        """Create tournament with 4 teams."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played=date.today()
        )

        # Create 4 captains with different MMRs
        self.captains = []
        for i, mmr in enumerate([5000, 4000, 6000, 4500]):
            captain = CustomUser.objects.create_user(
                username=f"cap{i}", password="test", mmr=mmr
            )
            self.captains.append(captain)

        # Create 4 teams
        self.teams = []
        for i, captain in enumerate(self.captains):
            team = Team.objects.create(
                name=f"Team {i}", captain=captain, tournament=self.tournament
            )
            team.members.add(captain)
            self.teams.append(team)

        # Create draft
        self.draft = Draft.objects.create(
            tournament=self.tournament, draft_style="shuffle"
        )

    def test_creates_all_rounds_upfront(self):
        """Creates num_teams * 4 rounds."""
        from app.functions.shuffle_draft import build_shuffle_rounds

        build_shuffle_rounds(self.draft)

        # 4 teams * 4 picks each = 16 rounds
        self.assertEqual(self.draft.draft_rounds.count(), 16)

    def test_first_round_has_captain_assigned(self):
        """First round captain is lowest MMR team."""
        from app.functions.shuffle_draft import build_shuffle_rounds

        build_shuffle_rounds(self.draft)

        first_round = self.draft.draft_rounds.order_by("pick_number").first()
        # Captain with 4000 MMR should pick first
        self.assertEqual(first_round.captain.pk, self.captains[1].pk)

    def test_remaining_rounds_have_null_captain(self):
        """Rounds 2-16 have null captain."""
        from app.functions.shuffle_draft import build_shuffle_rounds

        build_shuffle_rounds(self.draft)

        rounds = self.draft.draft_rounds.order_by("pick_number")[1:]
        for draft_round in rounds:
            self.assertIsNone(draft_round.captain)

    def test_pick_phases_assigned_correctly(self):
        """Pick phases are 1-4 based on round number."""
        from app.functions.shuffle_draft import build_shuffle_rounds

        build_shuffle_rounds(self.draft)

        rounds = list(self.draft.draft_rounds.order_by("pick_number"))
        # Rounds 1-4 = phase 1, 5-8 = phase 2, etc.
        self.assertEqual(rounds[0].pick_phase, 1)
        self.assertEqual(rounds[3].pick_phase, 1)
        self.assertEqual(rounds[4].pick_phase, 2)
        self.assertEqual(rounds[15].pick_phase, 4)


class AssignNextShuffleCaptainTest(TestCase):
    """Test assign_next_shuffle_captain function."""

    def setUp(self):
        """Create tournament with draft and make first pick."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played=date.today()
        )

        # Create 2 captains
        self.captain1 = CustomUser.objects.create_user(
            username="cap1", password="test", mmr=5000
        )
        self.captain2 = CustomUser.objects.create_user(
            username="cap2", password="test", mmr=4000
        )

        # Create player to be picked
        self.player = CustomUser.objects.create_user(
            username="player1", password="test", mmr=3000
        )

        # Create 2 teams
        self.team1 = Team.objects.create(
            name="Team 1", captain=self.captain1, tournament=self.tournament
        )
        self.team1.members.add(self.captain1)

        self.team2 = Team.objects.create(
            name="Team 2", captain=self.captain2, tournament=self.tournament
        )
        self.team2.members.add(self.captain2)

        # Add player to tournament users (needed for users_remaining property)
        self.tournament.users.add(self.player)

        # Create draft and build rounds
        self.draft = Draft.objects.create(
            tournament=self.tournament, draft_style="shuffle"
        )

        from app.functions.shuffle_draft import build_shuffle_rounds

        build_shuffle_rounds(self.draft)

    def test_assigns_captain_to_next_null_round(self):
        """Assigns captain to next round with null captain."""
        from app.functions.shuffle_draft import assign_next_shuffle_captain

        # First round should have captain2 (4000 MMR)
        first_round = self.draft.draft_rounds.order_by("pick_number").first()
        self.assertEqual(first_round.captain.pk, self.captain2.pk)

        # Simulate pick - add player to team2
        first_round.choice = self.player
        first_round.save()
        self.team2.members.add(self.player)

        # Now team2 has 7000 MMR, team1 has 5000 MMR
        # Team1 should pick next
        tie_data = assign_next_shuffle_captain(self.draft)

        second_round = self.draft.draft_rounds.order_by("pick_number")[1]
        self.assertEqual(second_round.captain.pk, self.captain1.pk)
        self.assertIsNone(tie_data)

    def test_returns_none_when_no_more_rounds(self):
        """Returns None when all rounds have captains."""
        from app.functions.shuffle_draft import assign_next_shuffle_captain

        # Assign captains to all rounds
        for draft_round in self.draft.draft_rounds.all():
            draft_round.captain = self.captain1
            draft_round.save()

        result = assign_next_shuffle_captain(self.draft)

        self.assertIsNone(result)

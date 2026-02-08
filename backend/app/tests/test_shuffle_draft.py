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


class DraftBuildRoundsIntegrationTest(TestCase):
    """Test Draft.build_rounds() integration with shuffle draft."""

    def setUp(self):
        """Create tournament with 4 teams."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played=date.today()
        )

        for i, mmr in enumerate([5000, 4000, 6000, 4500]):
            captain = CustomUser.objects.create_user(
                username=f"cap{i}", password="test", mmr=mmr
            )
            team = Team.objects.create(
                name=f"Team {i}", captain=captain, tournament=self.tournament
            )
            team.members.add(captain)

        self.draft = Draft.objects.create(
            tournament=self.tournament, draft_style="shuffle"
        )

    def test_build_rounds_delegates_to_shuffle_module(self):
        """Draft.build_rounds() uses shuffle module for shuffle style."""
        self.draft.build_rounds()

        # Should have 16 rounds
        self.assertEqual(self.draft.draft_rounds.count(), 16)

        # First round should have captain assigned
        first_round = self.draft.draft_rounds.order_by("pick_number").first()
        self.assertIsNotNone(first_round.captain)

        # Remaining rounds should have null captain
        remaining = self.draft.draft_rounds.order_by("pick_number")[1:]
        for draft_round in remaining:
            self.assertIsNone(draft_round.captain)


from rest_framework.test import APIClient


class PickPlayerForRoundShuffleTest(TestCase):
    """Test pick_player_for_round view with shuffle draft."""

    def setUp(self):
        """Create tournament, draft, and make API client."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played=date.today()
        )

        # Create staff user for API calls
        self.staff = CustomUser.objects.create_user(
            username="staff", password="test", is_staff=True
        )

        # Create captains and players
        self.captain1 = CustomUser.objects.create_user(
            username="cap1", password="test", mmr=5000
        )
        self.captain2 = CustomUser.objects.create_user(
            username="cap2", password="test", mmr=4000
        )
        self.player1 = CustomUser.objects.create_user(
            username="player1", password="test", mmr=3000
        )
        self.player2 = CustomUser.objects.create_user(
            username="player2", password="test", mmr=2000
        )

        # Create teams
        self.team1 = Team.objects.create(
            name="Team 1", captain=self.captain1, tournament=self.tournament
        )
        self.team1.members.add(self.captain1)
        self.team2 = Team.objects.create(
            name="Team 2", captain=self.captain2, tournament=self.tournament
        )
        self.team2.members.add(self.captain2)

        # Add players to tournament
        self.tournament.users.add(self.player1, self.player2)

        # Create draft
        self.draft = Draft.objects.create(
            tournament=self.tournament, draft_style="shuffle"
        )
        self.draft.build_rounds()

        self.client = APIClient()
        self.client.force_authenticate(user=self.staff)

    def test_assigns_next_captain_after_pick(self):
        """After pick, next round gets captain assigned."""
        first_round = self.draft.draft_rounds.order_by("pick_number").first()
        second_round = self.draft.draft_rounds.order_by("pick_number")[1]

        # Second round should have no captain yet
        self.assertIsNone(second_round.captain)

        # Make pick
        response = self.client.post(
            "/api/tournaments/pick_player",
            {"draft_round_pk": first_round.pk, "user_pk": self.player1.pk},
        )

        self.assertEqual(response.status_code, 201)

        # Refresh and check second round now has captain
        second_round.refresh_from_db()
        self.assertIsNotNone(second_round.captain)


class PickAuthorizationTest(TestCase):
    """Test pick authorization - only correct captain or staff can pick."""

    def setUp(self):
        """Create tournament, draft, and multiple captains."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played=date.today()
        )

        # Create two captains with different MMRs
        self.captain1 = CustomUser.objects.create_user(
            username="cap1", password="test", mmr=4000  # Lower MMR - picks first
        )
        self.captain2 = CustomUser.objects.create_user(
            username="cap2", password="test", mmr=5000  # Higher MMR
        )
        self.player1 = CustomUser.objects.create_user(
            username="player1", password="test", mmr=3000
        )

        # Create teams
        self.team1 = Team.objects.create(
            name="Team 1", captain=self.captain1, tournament=self.tournament
        )
        self.team1.members.add(self.captain1)
        self.team2 = Team.objects.create(
            name="Team 2", captain=self.captain2, tournament=self.tournament
        )
        self.team2.members.add(self.captain2)

        # Add player to tournament
        self.tournament.users.add(self.player1)

        # Create draft
        self.draft = Draft.objects.create(
            tournament=self.tournament, draft_style="shuffle"
        )
        self.draft.build_rounds()

        self.client = APIClient()

    def test_wrong_captain_returns_403(self):
        """Captain who is not assigned to current round gets 403."""
        first_round = self.draft.draft_rounds.order_by("pick_number").first()

        # captain1 (lower MMR) should be assigned first round
        self.assertEqual(first_round.captain, self.captain1)

        # Try to pick as captain2 (wrong captain)
        self.client.force_authenticate(user=self.captain2)
        response = self.client.post(
            "/api/tournaments/pick_player",
            {"draft_round_pk": first_round.pk, "user_pk": self.player1.pk},
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("captain for this round", response.data["error"])

    def test_correct_captain_can_pick(self):
        """Captain assigned to current round can make pick."""
        first_round = self.draft.draft_rounds.order_by("pick_number").first()

        # captain1 should be able to pick
        self.client.force_authenticate(user=self.captain1)
        response = self.client.post(
            "/api/tournaments/pick_player",
            {"draft_round_pk": first_round.pk, "user_pk": self.player1.pk},
        )

        self.assertEqual(response.status_code, 201)

    def test_staff_can_pick_for_any_round(self):
        """Staff can pick even if not the captain."""
        staff = CustomUser.objects.create_user(
            username="staff", password="test", is_staff=True
        )
        first_round = self.draft.draft_rounds.order_by("pick_number").first()

        self.client.force_authenticate(user=staff)
        response = self.client.post(
            "/api/tournaments/pick_player",
            {"draft_round_pk": first_round.pk, "user_pk": self.player1.pk},
        )

        self.assertEqual(response.status_code, 201)

    def test_non_captain_non_staff_returns_403(self):
        """Regular user who is not captain or staff gets 403."""
        regular_user = CustomUser.objects.create_user(
            username="regular", password="test", is_staff=False
        )
        first_round = self.draft.draft_rounds.order_by("pick_number").first()

        self.client.force_authenticate(user=regular_user)
        response = self.client.post(
            "/api/tournaments/pick_player",
            {"draft_round_pk": first_round.pk, "user_pk": self.player1.pk},
        )

        self.assertEqual(response.status_code, 403)


class FullTeamNotAssignedTest(TestCase):
    """Test that full teams (5 members) are not assigned as next picker."""

    def setUp(self):
        """Create tournament with 2 teams, one at max size."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played=date.today()
        )

        # Create captains - team2 has lower MMR
        self.captain1 = CustomUser.objects.create_user(
            username="cap1", password="test", mmr=5000
        )
        self.captain2 = CustomUser.objects.create_user(
            username="cap2", password="test", mmr=1000  # Much lower MMR
        )

        # Create teams
        self.team1 = Team.objects.create(
            name="Team 1", captain=self.captain1, tournament=self.tournament
        )
        self.team1.members.add(self.captain1)

        self.team2 = Team.objects.create(
            name="Team 2", captain=self.captain2, tournament=self.tournament
        )
        self.team2.members.add(self.captain2)

        # Add 4 more members to team2 to make it full (5 total)
        for i in range(4):
            member = CustomUser.objects.create_user(
                username=f"team2_member{i}", password="test", mmr=1000
            )
            self.team2.members.add(member)

        # Create draft
        self.draft = Draft.objects.create(
            tournament=self.tournament, draft_style="shuffle"
        )

    def test_full_team_not_assigned_as_next_picker(self):
        """Full team should not be assigned as next picker even with lowest MMR."""
        from app.functions.shuffle_draft import assign_next_shuffle_captain

        # Create a round without captain
        DraftRound.objects.create(
            draft=self.draft, captain=None, pick_number=1, pick_phase=1
        )

        # Team2 has lower MMR but is full (5 members)
        # Team1 should be assigned instead
        assign_next_shuffle_captain(self.draft)

        first_round = self.draft.draft_rounds.first()
        self.assertEqual(first_round.captain.pk, self.captain1.pk)

    def test_returns_none_when_all_teams_full(self):
        """Returns None when all teams have reached max size."""
        from app.functions.shuffle_draft import assign_next_shuffle_captain

        # Make team1 also full
        for i in range(4):
            member = CustomUser.objects.create_user(
                username=f"team1_member{i}", password="test", mmr=1000
            )
            self.team1.members.add(member)

        # Create a round without captain
        DraftRound.objects.create(
            draft=self.draft, captain=None, pick_number=1, pick_phase=1
        )

        result = assign_next_shuffle_captain(self.draft)

        self.assertIsNone(result)


class UndoClearsNextCaptainTest(TestCase):
    """Test that undo clears the next round's captain."""

    def setUp(self):
        """Create tournament with draft and make picks."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played=date.today()
        )

        # Create staff user for API calls
        self.staff = CustomUser.objects.create_user(
            username="staff", password="test", is_staff=True
        )

        # Create captains
        self.captain1 = CustomUser.objects.create_user(
            username="cap1", password="test", mmr=5000
        )
        self.captain2 = CustomUser.objects.create_user(
            username="cap2", password="test", mmr=4000
        )

        # Create players (need multiple so users_remaining exists after first pick)
        self.player1 = CustomUser.objects.create_user(
            username="player1", password="test", mmr=3000
        )
        self.player2 = CustomUser.objects.create_user(
            username="player2", password="test", mmr=2500
        )

        # Create teams
        self.team1 = Team.objects.create(
            name="Team 1", captain=self.captain1, tournament=self.tournament
        )
        self.team1.members.add(self.captain1)
        self.team2 = Team.objects.create(
            name="Team 2", captain=self.captain2, tournament=self.tournament
        )
        self.team2.members.add(self.captain2)

        # Add players to tournament
        self.tournament.users.add(self.player1, self.player2)

        # Create draft with shuffle style
        self.draft = Draft.objects.create(
            tournament=self.tournament, draft_style="shuffle"
        )
        self.draft.build_rounds()

        self.client = APIClient()
        self.client.force_authenticate(user=self.staff)

    def test_undo_clears_next_round_captain(self):
        """Undo should clear the next round's captain assignment."""
        first_round = self.draft.draft_rounds.order_by("pick_number").first()
        second_round = self.draft.draft_rounds.order_by("pick_number")[1]

        # Make a pick
        response = self.client.post(
            "/api/tournaments/pick_player",
            {"draft_round_pk": first_round.pk, "user_pk": self.player1.pk},
        )
        self.assertEqual(response.status_code, 201)

        # Verify second round now has captain
        second_round.refresh_from_db()
        self.assertIsNotNone(second_round.captain)

        # Undo the pick
        response = self.client.post(
            "/api/tournaments/undo-pick",
            {"draft_pk": self.draft.pk},
        )
        self.assertEqual(response.status_code, 200)

        # Second round should now have no captain
        second_round.refresh_from_db()
        self.assertIsNone(second_round.captain)

    def test_undo_clears_tie_data_on_next_round(self):
        """Undo should also clear tie resolution data on next round."""
        first_round = self.draft.draft_rounds.order_by("pick_number").first()
        second_round = self.draft.draft_rounds.order_by("pick_number")[1]

        # Manually set tie data on second round (simulating a tie resolution)
        second_round.captain = self.captain1
        second_round.was_tie = True
        second_round.tie_roll_data = {"test": "data"}
        second_round.save()

        # Make a pick on first round
        first_round.choice = self.player1
        first_round.save()
        self.team2.members.add(self.player1)

        # Undo the pick
        response = self.client.post(
            "/api/tournaments/undo-pick",
            {"draft_pk": self.draft.pk},
        )
        self.assertEqual(response.status_code, 200)

        # Second round should have tie data cleared
        second_round.refresh_from_db()
        self.assertIsNone(second_round.captain)
        self.assertFalse(second_round.was_tie)
        self.assertIsNone(second_round.tie_roll_data)


class DraftRestartTest(TestCase):
    """Test draft restart uses captain MMR only, not old picks."""

    def setUp(self):
        """Create tournament with 2 teams and completed picks."""
        self.admin = CustomUser.objects.create_user(
            username="admin", password="test", is_staff=True
        )
        # Captain 1 has lower MMR (4000) - should pick first
        self.captain1 = CustomUser.objects.create_user(
            username="cap1_low_mmr", password="test", mmr=4000
        )
        # Captain 2 has higher MMR (5000) - should pick second
        self.captain2 = CustomUser.objects.create_user(
            username="cap2_high_mmr", password="test", mmr=5000
        )
        # High MMR player that was picked by team1
        self.high_mmr_player = CustomUser.objects.create_user(
            username="high_mmr_player", password="test", mmr=6000
        )

        self.tournament = Tournament.objects.create(
            name="Restart Test Tournament", date_played=date.today()
        )
        self.tournament.users.add(self.captain1, self.captain2, self.high_mmr_player)
        # Note: captains property is derived from teams, not a direct field

        self.team1 = Team.objects.create(
            name="Team 1 (low cap)",
            captain=self.captain1,
            tournament=self.tournament,
        )
        self.team1.members.add(self.captain1)

        self.team2 = Team.objects.create(
            name="Team 2 (high cap)",
            captain=self.captain2,
            tournament=self.tournament,
        )
        self.team2.members.add(self.captain2)

        # Create draft with shuffle style
        self.draft = Draft.objects.create(
            tournament=self.tournament, draft_style="shuffle"
        )
        # Note: Draft.captains is a property derived from tournament.teams
        # users_remaining is also a property, not a ManyToMany field
        self.draft.build_rounds()

        self.client.force_login(self.admin)

    def test_restart_uses_captain_mmr_only(self):
        """
        After picks are made, restarting draft should calculate first captain
        based on captain MMR only, not team MMR including picks.

        Scenario:
        - Team1 captain: 4000 MMR (lower)
        - Team2 captain: 5000 MMR (higher)
        - Team1 picks high_mmr_player (6000 MMR)
        - Team1 total MMR becomes 10000, Team2 stays 5000

        Without fix: Team2 would pick first (lower total team MMR)
        With fix: Team1 should pick first (lower captain MMR)
        """
        # Verify initial first captain is team1 (lower captain MMR)
        first_round = self.draft.draft_rounds.order_by("pick_number").first()
        self.assertEqual(first_round.captain.pk, self.captain1.pk)

        # Make a pick - team1 picks high_mmr_player
        first_round.choice = self.high_mmr_player
        first_round.save()
        self.team1.members.add(self.high_mmr_player)

        # Now team1 has 4000 + 6000 = 10000 total MMR
        # team2 has 5000 total MMR

        # Restart the draft via generate_draft_rounds
        response = self.client.post(
            "/api/tournaments/init-draft",
            {"tournament_pk": self.tournament.pk},
        )
        self.assertEqual(response.status_code, 201)

        # Refresh draft from DB
        self.draft.refresh_from_db()

        # First captain should still be team1 (captain MMR 4000 < 5000)
        # NOT team2 (which would be the case if using total team MMR)
        first_round = self.draft.draft_rounds.order_by("pick_number").first()
        self.assertEqual(
            first_round.captain.pk,
            self.captain1.pk,
            "After restart, first captain should be based on captain MMR only, "
            f"not total team MMR. Expected cap1 (4000 MMR), got {first_round.captain.username}",
        )


class DraftRestartFuzzTest(TestCase):
    """Fuzz test draft restart across varying team counts, pick depths, and repeated restarts."""

    def _create_tournament(self, num_teams, players_per_team, mmr_base=3000):
        """Helper: create a tournament with N teams and M available players per team."""
        admin = CustomUser.objects.create_user(
            username="fuzz_admin", password="test", is_staff=True
        )
        tournament = Tournament.objects.create(
            name="Fuzz Tournament", date_played=date.today()
        )

        captains = []
        teams = []
        for i in range(num_teams):
            cap = CustomUser.objects.create_user(
                username=f"fuzz_cap{i}",
                password="test",
                mmr=mmr_base + i * 500,
            )
            captains.append(cap)
            team = Team.objects.create(
                name=f"Fuzz Team {i}", captain=cap, tournament=tournament
            )
            team.members.add(cap)
            teams.append(team)
            tournament.users.add(cap)

        players = []
        for i in range(num_teams * players_per_team):
            p = CustomUser.objects.create_user(
                username=f"fuzz_player{i}",
                password="test",
                mmr=2000 + i * 100,
            )
            players.append(p)
            tournament.users.add(p)

        draft = Draft.objects.create(tournament=tournament, draft_style="shuffle")
        draft.build_rounds()

        return admin, tournament, draft, captains, teams, players

    def _make_picks(self, draft, num_picks, players):
        """Helper: make N picks on the draft using available players."""
        from app.functions.shuffle_draft import assign_next_shuffle_captain

        rounds = list(draft.draft_rounds.order_by("pick_number"))
        picked = 0
        for i, rnd in enumerate(rounds):
            if picked >= num_picks:
                break
            if not rnd.captain:
                # Need captain assigned first
                assign_next_shuffle_captain(draft)
                rnd.refresh_from_db()
            if not rnd.captain:
                break
            # Pick the next available player
            remaining = list(draft.users_remaining)
            if not remaining:
                break
            rnd.pick_player(remaining[0])
            picked += 1
            # Assign next captain after pick
            if picked < num_picks:
                assign_next_shuffle_captain(draft)

        return picked

    def _restart_draft(self, admin, tournament):
        """Helper: restart draft via the API endpoint."""
        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.post(
            "/api/tournaments/init-draft",
            {"tournament_pk": tournament.pk},
        )
        return response

    def _assert_draft_invariants(self, draft, num_teams, msg=""):
        """Assert core invariants that must hold after every restart."""
        prefix = f"[{msg}] " if msg else ""

        # Refresh from DB
        draft.refresh_from_db()
        rounds = list(draft.draft_rounds.order_by("pick_number"))

        # 1. Correct number of rounds
        expected_rounds = num_teams * 4
        self.assertEqual(
            len(rounds),
            expected_rounds,
            f"{prefix}Expected {expected_rounds} rounds, got {len(rounds)}",
        )

        # 2. All choices cleared
        for rnd in rounds:
            self.assertIsNone(
                rnd.choice,
                f"{prefix}Round {rnd.pick_number} should have no choice after restart",
            )

        # 3. Pick numbers are sequential 1..N
        pick_numbers = [r.pick_number for r in rounds]
        self.assertEqual(
            pick_numbers,
            list(range(1, expected_rounds + 1)),
            f"{prefix}Pick numbers should be sequential",
        )

        # 4. First round has a captain assigned
        self.assertIsNotNone(
            rounds[0].captain,
            f"{prefix}First round must have a captain",
        )

        # 5. Remaining rounds have null captains (shuffle style)
        for rnd in rounds[1:]:
            self.assertIsNone(
                rnd.captain,
                f"{prefix}Round {rnd.pick_number} should have null captain",
            )

        # 6. First captain is the lowest-MMR captain
        from app.functions.shuffle_draft import get_team_total_mmr

        teams = list(draft.tournament.teams.all())
        mmrs = {t.captain.pk: get_team_total_mmr(t) for t in teams}
        lowest_pk = min(mmrs, key=mmrs.get)
        self.assertEqual(
            rounds[0].captain.pk,
            lowest_pk,
            f"{prefix}First captain should be lowest MMR captain",
        )

        # 7. Teams are captain-only (all non-captain members cleared)
        for team in teams:
            members = list(team.members.all())
            self.assertEqual(
                len(members),
                1,
                f"{prefix}Team '{team.name}' should only have captain, has {len(members)}",
            )
            self.assertEqual(
                members[0].pk,
                team.captain.pk,
                f"{prefix}Team '{team.name}' sole member should be captain",
            )

        # 8. latest_round points to the first round
        self.assertEqual(
            draft.latest_round,
            rounds[0].pk,
            f"{prefix}latest_round should point to first round",
        )

        # 9. Serialized draft_rounds are in pick_number order
        from app.serializers import DraftSerializer

        serialized = DraftSerializer(draft).data
        serialized_pick_numbers = [r["pick_number"] for r in serialized["draft_rounds"]]
        self.assertEqual(
            serialized_pick_numbers,
            list(range(1, expected_rounds + 1)),
            f"{prefix}Serialized rounds must be in pick_number order",
        )

    def test_restart_with_no_picks_made(self):
        """Restart immediately after init with 0 picks."""
        admin, tournament, draft, captains, teams, players = self._create_tournament(
            num_teams=3, players_per_team=4
        )

        response = self._restart_draft(admin, tournament)
        self.assertEqual(response.status_code, 201)
        self._assert_draft_invariants(draft, 3, "no picks")

    def test_restart_after_partial_picks(self):
        """Restart after making some picks but not finishing."""
        admin, tournament, draft, captains, teams, players = self._create_tournament(
            num_teams=3, players_per_team=4
        )

        picked = self._make_picks(draft, 4, players)
        self.assertGreater(picked, 0, "Should have made at least 1 pick")

        response = self._restart_draft(admin, tournament)
        self.assertEqual(response.status_code, 201)
        self._assert_draft_invariants(draft, 3, f"after {picked} picks")

    def test_restart_after_full_draft(self):
        """Restart after all rounds are picked."""
        admin, tournament, draft, captains, teams, players = self._create_tournament(
            num_teams=2, players_per_team=4
        )

        total_rounds = draft.draft_rounds.count()
        picked = self._make_picks(draft, total_rounds, players)
        self.assertEqual(picked, total_rounds, "Should have completed all picks")

        response = self._restart_draft(admin, tournament)
        self.assertEqual(response.status_code, 201)
        self._assert_draft_invariants(draft, 2, "full draft complete")

    def test_double_restart(self):
        """Restart twice in a row without any picks between."""
        admin, tournament, draft, captains, teams, players = self._create_tournament(
            num_teams=4, players_per_team=4
        )

        self._make_picks(draft, 3, players)

        response = self._restart_draft(admin, tournament)
        self.assertEqual(response.status_code, 201)
        self._assert_draft_invariants(draft, 4, "first restart")

        response = self._restart_draft(admin, tournament)
        self.assertEqual(response.status_code, 201)
        self._assert_draft_invariants(draft, 4, "second restart")

    def test_restart_pick_restart_cycle(self):
        """Restart, make picks, restart again — multiple cycles."""
        admin, tournament, draft, captains, teams, players = self._create_tournament(
            num_teams=2, players_per_team=6
        )

        for cycle in range(3):
            response = self._restart_draft(admin, tournament)
            self.assertEqual(response.status_code, 201)
            draft.refresh_from_db()
            self._assert_draft_invariants(draft, 2, f"cycle {cycle} restart")

            # Make a few picks
            self._make_picks(draft, 2, players)

    def test_restart_with_varying_team_sizes(self):
        """Restart works correctly for 2, 3, 4, and 5 teams."""
        for num_teams in [2, 3, 4, 5]:
            with self.subTest(num_teams=num_teams):
                # Clean up between subtests
                CustomUser.objects.all().delete()
                Tournament.objects.all().delete()

                admin, tournament, draft, captains, teams, players = (
                    self._create_tournament(num_teams=num_teams, players_per_team=4)
                )

                # Make some picks
                self._make_picks(draft, num_teams, players)

                response = self._restart_draft(admin, tournament)
                self.assertEqual(response.status_code, 201)
                self._assert_draft_invariants(draft, num_teams, f"{num_teams} teams")

    def test_restart_preserves_old_round_pks_do_not_leak(self):
        """Old DraftRound PKs should not exist after restart."""
        admin, tournament, draft, captains, teams, players = self._create_tournament(
            num_teams=2, players_per_team=4
        )

        old_pks = set(draft.draft_rounds.values_list("pk", flat=True))

        self._make_picks(draft, 3, players)

        response = self._restart_draft(admin, tournament)
        self.assertEqual(response.status_code, 201)

        new_pks = set(draft.draft_rounds.values_list("pk", flat=True))

        # Old PKs should all be gone (deleted and recreated)
        self.assertTrue(
            old_pks.isdisjoint(new_pks),
            f"Old round PKs {old_pks} should not overlap with new PKs {new_pks}",
        )

    def test_serialized_latest_round_matches_first_round_pk(self):
        """API response latest_round should match the PK of the first round."""
        admin, tournament, draft, captains, teams, players = self._create_tournament(
            num_teams=3, players_per_team=4
        )

        self._make_picks(draft, 5, players)

        response = self._restart_draft(admin, tournament)
        self.assertEqual(response.status_code, 201)

        data = response.data
        draft_data = data.get("draft")
        self.assertIsNotNone(draft_data, "Response should include draft")

        rounds = draft_data["draft_rounds"]
        self.assertGreater(len(rounds), 0, "Should have draft rounds")

        # latest_round should be the PK of the first round (pick_number=1)
        first_round_pk = rounds[0]["pk"]
        self.assertEqual(
            draft_data["latest_round"],
            first_round_pk,
            "latest_round should point to the first round after restart",
        )

    def test_restart_with_equal_captain_mmrs(self):
        """Restart when all captains have equal MMR (tie scenario)."""
        admin = CustomUser.objects.create_user(
            username="eq_admin", password="test", is_staff=True
        )
        tournament = Tournament.objects.create(
            name="Equal MMR Tournament", date_played=date.today()
        )

        captains = []
        for i in range(3):
            cap = CustomUser.objects.create_user(
                username=f"eq_cap{i}", password="test", mmr=5000
            )
            captains.append(cap)
            team = Team.objects.create(
                name=f"Eq Team {i}", captain=cap, tournament=tournament
            )
            team.members.add(cap)
            tournament.users.add(cap)

        for i in range(12):
            p = CustomUser.objects.create_user(
                username=f"eq_player{i}", password="test", mmr=3000
            )
            tournament.users.add(p)

        draft = Draft.objects.create(tournament=tournament, draft_style="shuffle")
        draft.build_rounds()

        self._make_picks(
            draft, 4, list(CustomUser.objects.filter(username__startswith="eq_player"))
        )

        response = self._restart_draft(admin, tournament)
        self.assertEqual(response.status_code, 201)

        draft.refresh_from_db()
        rounds = list(draft.draft_rounds.order_by("pick_number"))

        # All invariants should hold — first captain is determined by tie-break
        self.assertEqual(len(rounds), 12)
        self.assertIsNotNone(rounds[0].captain)
        for rnd in rounds:
            self.assertIsNone(rnd.choice)

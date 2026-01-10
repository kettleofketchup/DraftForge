"""Tests for bracket save and team placement functionality."""

from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser, Game, Team, Tournament


class SaveBracketTest(TestCase):
    """Test save_bracket endpoint."""

    def setUp(self):
        """Create test data."""
        self.admin = CustomUser.objects.create_superuser(
            username="admin",
            password="admin123",
            email="admin@test.com",
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        # Create 4 teams
        self.teams = []
        for i in range(4):
            captain = CustomUser.objects.create_user(
                username=f"captain{i}",
                password="test123",
                mmr=5000 - (i * 100),
            )
            team = Team.objects.create(
                name=f"Team {i+1}",
                captain=captain,
                tournament=self.tournament,
            )
            self.teams.append(team)

        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_save_bracket_creates_games(self):
        """Save bracket creates Game records for each match."""
        matches = [
            {
                "id": "w-1-0",
                "round": 1,
                "position": 0,
                "bracketType": "winners",
                "eliminationType": "double",
                "radiantTeam": {"pk": self.teams[0].pk},
                "direTeam": {"pk": self.teams[3].pk},
                "status": "pending",
                "nextMatchId": "w-2-0",
                "nextMatchSlot": "radiant",
                "loserNextMatchId": "l-1-0",
                "loserNextMatchSlot": "radiant",
            },
            {
                "id": "w-1-1",
                "round": 1,
                "position": 1,
                "bracketType": "winners",
                "eliminationType": "double",
                "radiantTeam": {"pk": self.teams[1].pk},
                "direTeam": {"pk": self.teams[2].pk},
                "status": "pending",
                "nextMatchId": "w-2-0",
                "nextMatchSlot": "dire",
                "loserNextMatchId": "l-1-0",
                "loserNextMatchSlot": "dire",
            },
            {
                "id": "w-2-0",
                "round": 2,
                "position": 0,
                "bracketType": "winners",
                "eliminationType": "double",
                "status": "pending",
                "nextMatchId": "gf-1-0",
                "nextMatchSlot": "radiant",
                "loserNextMatchId": "l-2-0",
                "loserNextMatchSlot": "dire",
            },
            {
                "id": "l-1-0",
                "round": 1,
                "position": 0,
                "bracketType": "losers",
                "eliminationType": "double",
                "status": "pending",
                "nextMatchId": "l-2-0",
                "nextMatchSlot": "radiant",
            },
            {
                "id": "l-2-0",
                "round": 2,
                "position": 0,
                "bracketType": "losers",
                "eliminationType": "double",
                "status": "pending",
                "nextMatchId": "gf-1-0",
                "nextMatchSlot": "dire",
            },
            {
                "id": "gf-1-0",
                "round": 1,
                "position": 0,
                "bracketType": "grand_finals",
                "eliminationType": "double",
                "status": "pending",
            },
        ]

        response = self.client.post(
            f"/api/bracket/tournaments/{self.tournament.pk}/save/",
            {"matches": matches},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Game.objects.filter(tournament=self.tournament).count(), 6)

    def test_save_bracket_wires_next_game_relationships(self):
        """Save bracket correctly sets next_game foreign keys."""
        matches = [
            {
                "id": "w-1-0",
                "round": 1,
                "position": 0,
                "bracketType": "winners",
                "eliminationType": "double",
                "status": "pending",
                "nextMatchId": "w-2-0",
                "nextMatchSlot": "radiant",
            },
            {
                "id": "w-2-0",
                "round": 2,
                "position": 0,
                "bracketType": "winners",
                "eliminationType": "double",
                "status": "pending",
            },
        ]

        self.client.post(
            f"/api/bracket/tournaments/{self.tournament.pk}/save/",
            {"matches": matches},
            format="json",
        )

        game_w1 = Game.objects.get(
            tournament=self.tournament, bracket_type="winners", round=1, position=0
        )
        game_w2 = Game.objects.get(
            tournament=self.tournament, bracket_type="winners", round=2, position=0
        )

        self.assertEqual(game_w1.next_game, game_w2)
        self.assertEqual(game_w1.next_game_slot, "radiant")

    def test_save_bracket_clears_existing_bracket_games(self):
        """Save bracket deletes existing bracket games before creating new ones."""
        # Create an existing game
        Game.objects.create(
            tournament=self.tournament,
            round=1,
            position=0,
            bracket_type="winners",
        )
        self.assertEqual(Game.objects.filter(tournament=self.tournament).count(), 1)

        # Save new bracket
        matches = [
            {
                "id": "w-1-0",
                "round": 1,
                "position": 0,
                "bracketType": "winners",
                "eliminationType": "double",
                "status": "pending",
            },
            {
                "id": "w-1-1",
                "round": 1,
                "position": 1,
                "bracketType": "winners",
                "eliminationType": "double",
                "status": "pending",
            },
        ]

        self.client.post(
            f"/api/bracket/tournaments/{self.tournament.pk}/save/",
            {"matches": matches},
            format="json",
        )

        # Should have 2 games (old one deleted, 2 new created)
        self.assertEqual(Game.objects.filter(tournament=self.tournament).count(), 2)

    def test_save_bracket_returns_games_with_pks(self):
        """Save bracket returns games with database PKs."""
        matches = [
            {
                "id": "w-1-0",
                "round": 1,
                "position": 0,
                "bracketType": "winners",
                "eliminationType": "double",
                "status": "pending",
            },
        ]

        response = self.client.post(
            f"/api/bracket/tournaments/{self.tournament.pk}/save/",
            {"matches": matches},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("matches", response.data)
        self.assertEqual(len(response.data["matches"]), 1)
        self.assertIn("pk", response.data["matches"][0])

    def test_save_bracket_requires_admin(self):
        """Save bracket requires admin permission."""
        regular_user = CustomUser.objects.create_user(
            username="regular",
            password="test123",
        )
        self.client.force_authenticate(user=regular_user)

        response = self.client.post(
            f"/api/bracket/tournaments/{self.tournament.pk}/save/",
            {"matches": []},
            format="json",
        )

        self.assertEqual(response.status_code, 403)


class CalculatePlacementTest(TestCase):
    """Test placement calculation logic."""

    def test_grand_finals_loser_gets_2nd(self):
        """Loser of grand finals gets 2nd place."""
        from app.views.bracket import calculate_placement

        tournament = Tournament.objects.create(name="Test", date_played=date.today())
        game = Game.objects.create(
            tournament=tournament,
            bracket_type="grand_finals",
            round=1,
            position=0,
        )

        placement = calculate_placement(game)
        self.assertEqual(placement, 2)

    def test_losers_finals_loser_gets_3rd(self):
        """Loser of losers finals gets 3rd place."""
        from app.views.bracket import calculate_placement

        tournament = Tournament.objects.create(name="Test", date_played=date.today())
        # Create losers bracket with 2 rounds (finals is round 2)
        Game.objects.create(
            tournament=tournament,
            bracket_type="losers",
            round=1,
            position=0,
        )
        losers_finals = Game.objects.create(
            tournament=tournament,
            bracket_type="losers",
            round=2,
            position=0,
        )

        placement = calculate_placement(losers_finals)
        self.assertEqual(placement, 3)

    def test_losers_semi_loser_gets_4th(self):
        """Loser of losers semi gets 4th place."""
        from app.views.bracket import calculate_placement

        tournament = Tournament.objects.create(name="Test", date_played=date.today())
        # Create losers bracket with 3 rounds
        losers_semi = Game.objects.create(
            tournament=tournament,
            bracket_type="losers",
            round=1,
            position=0,
        )
        Game.objects.create(
            tournament=tournament,
            bracket_type="losers",
            round=2,
            position=0,
        )
        Game.objects.create(
            tournament=tournament,
            bracket_type="losers",
            round=3,
            position=0,
        )

        placement = calculate_placement(losers_semi)
        self.assertEqual(placement, 4)

    def test_winners_bracket_elimination_returns_none(self):
        """Winners bracket games don't set placement (loser goes to losers)."""
        from app.views.bracket import calculate_placement

        tournament = Tournament.objects.create(name="Test", date_played=date.today())
        game = Game.objects.create(
            tournament=tournament,
            bracket_type="winners",
            round=1,
            position=0,
        )

        placement = calculate_placement(game)
        self.assertIsNone(placement)


class AdvanceWinnerPlacementTest(TestCase):
    """Test advance_winner sets placement correctly."""

    def setUp(self):
        """Create test data."""
        self.admin = CustomUser.objects.create_superuser(
            username="admin",
            password="admin123",
            email="admin@test.com",
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        self.captain1 = CustomUser.objects.create_user(username="cap1", password="test")
        self.captain2 = CustomUser.objects.create_user(username="cap2", password="test")
        self.team1 = Team.objects.create(
            name="Team 1",
            captain=self.captain1,
            tournament=self.tournament,
        )
        self.team2 = Team.objects.create(
            name="Team 2",
            captain=self.captain2,
            tournament=self.tournament,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_advance_winner_sets_loser_placement_when_eliminated(self):
        """When loser has no loser_next_game, their placement is set."""
        # Losers finals - no loser path, loser gets 3rd
        losers_finals = Game.objects.create(
            tournament=self.tournament,
            bracket_type="losers",
            round=1,  # Only losers round = finals
            position=0,
            radiant_team=self.team1,
            dire_team=self.team2,
        )

        response = self.client.post(
            f"/api/bracket/games/{losers_finals.pk}/advance-winner/",
            {"winner": "radiant"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.team2.refresh_from_db()
        self.assertEqual(self.team2.placement, 3)

    def test_advance_winner_sets_winner_placement_in_grand_finals(self):
        """Grand finals winner gets 1st place."""
        grand_finals = Game.objects.create(
            tournament=self.tournament,
            bracket_type="grand_finals",
            round=1,
            position=0,
            radiant_team=self.team1,
            dire_team=self.team2,
        )

        response = self.client.post(
            f"/api/bracket/games/{grand_finals.pk}/advance-winner/",
            {"winner": "radiant"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.team1.refresh_from_db()
        self.team2.refresh_from_db()
        self.assertEqual(self.team1.placement, 1)
        self.assertEqual(self.team2.placement, 2)

    def test_advance_winner_no_placement_when_loser_has_path(self):
        """When loser has loser_next_game, no placement is set."""
        losers_game = Game.objects.create(
            tournament=self.tournament,
            bracket_type="losers",
            round=2,
            position=0,
        )
        winners_game = Game.objects.create(
            tournament=self.tournament,
            bracket_type="winners",
            round=1,
            position=0,
            radiant_team=self.team1,
            dire_team=self.team2,
            loser_next_game=losers_game,
            loser_next_game_slot="radiant",
            elimination_type="double",
        )

        response = self.client.post(
            f"/api/bracket/games/{winners_game.pk}/advance-winner/",
            {"winner": "radiant"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.team2.refresh_from_db()
        self.assertIsNone(self.team2.placement)


class ManualPlacementOverrideTest(TestCase):
    """Test manual placement override endpoint."""

    def setUp(self):
        """Create test data."""
        self.admin = CustomUser.objects.create_superuser(
            username="admin",
            password="admin123",
            email="admin@test.com",
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        self.captain = CustomUser.objects.create_user(username="cap", password="test")
        self.team = Team.objects.create(
            name="Team 1",
            captain=self.captain,
            tournament=self.tournament,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_set_placement_success(self):
        """Admin can set team placement manually."""
        response = self.client.patch(
            f"/api/bracket/tournaments/{self.tournament.pk}/teams/{self.team.pk}/placement/",
            {"placement": 3},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.team.refresh_from_db()
        self.assertEqual(self.team.placement, 3)

    def test_clear_placement(self):
        """Admin can clear placement by setting to null."""
        self.team.placement = 2
        self.team.save()

        response = self.client.patch(
            f"/api/bracket/tournaments/{self.tournament.pk}/teams/{self.team.pk}/placement/",
            {"placement": None},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.team.refresh_from_db()
        self.assertIsNone(self.team.placement)

    def test_invalid_placement_rejected(self):
        """Invalid placement values are rejected."""
        response = self.client.patch(
            f"/api/bracket/tournaments/{self.tournament.pk}/teams/{self.team.pk}/placement/",
            {"placement": 0},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_requires_admin(self):
        """Regular users cannot set placement."""
        regular_user = CustomUser.objects.create_user(
            username="regular",
            password="test123",
        )
        self.client.force_authenticate(user=regular_user)

        response = self.client.patch(
            f"/api/bracket/tournaments/{self.tournament.pk}/teams/{self.team.pk}/placement/",
            {"placement": 1},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_team_must_belong_to_tournament(self):
        """Cannot set placement for team in different tournament."""
        other_tournament = Tournament.objects.create(
            name="Other Tournament",
            date_played=date.today(),
        )
        other_team = Team.objects.create(
            name="Other Team",
            tournament=other_tournament,
        )

        response = self.client.patch(
            f"/api/bracket/tournaments/{self.tournament.pk}/teams/{other_team.pk}/placement/",
            {"placement": 1},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

"""Tests for bracket save and team placement functionality."""

from datetime import date

from django.test import TestCase
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import (
    CustomUser,
    Game,
    Team,
    TeamLog,
    TeamLogAction,
    TeamLogVia,
    Tournament,
)
from tournament.services.team_management import live_conflicts, replace_captain
from tournament.tests.test_team_management import TeamManagementFixture, eliminate
from tournament.views.bracket import calculate_placement


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

    def test_set_placement_writes_team_log_with_reason(self) -> None:
        response = self.client.patch(
            f"/api/bracket/tournaments/{self.tournament.pk}/teams/{self.team.pk}/placement/",
            {"placement": 4, "reason": "  lost the lower final  "},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        row = TeamLog.objects.get(team=self.team)
        self.assertEqual(row.action, TeamLogAction.SET_PLACEMENT)
        self.assertEqual(row.actor, self.admin)
        self.assertEqual(row.via, TeamLogVia.WEB)
        self.assertEqual(row.reason, "lost the lower final")
        self.assertEqual(
            row.details,
            {"before": {"placement": None}, "after": {"placement": 4}},
        )

    def test_unchanged_placement_writes_no_team_log(self) -> None:
        self.team.placement = 2
        self.team.save()

        response = self.client.patch(
            f"/api/bracket/tournaments/{self.tournament.pk}/teams/{self.team.pk}/placement/",
            {"placement": 2, "reason": "same"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(TeamLog.objects.filter(team=self.team).exists())

    def test_non_text_reason_rejected(self) -> None:
        response = self.client.patch(
            f"/api/bracket/tournaments/{self.tournament.pk}/teams/{self.team.pk}/placement/",
            {"placement": 3, "reason": 5},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_reason")
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


class UnsetWinnerTest(TestCase):
    """Test advance_winner with winner=null to unset winner."""

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

    def test_advance_winner_unset_clears_winner(self):
        """Test that advance_winner with winner=null clears the winner."""
        # Create a completed game with team1 as winner
        game = Game.objects.create(
            tournament=self.tournament,
            bracket_type="losers",
            round=1,
            position=0,
            radiant_team=self.team1,
            dire_team=self.team2,
            winning_team=self.team1,
            status="completed",
        )
        # Loser (team2) got placement from previous advance
        self.team2.placement = 3
        self.team2.save()

        # Call advance_winner with None to unset
        response = self.client.post(
            f"/api/bracket/games/{game.pk}/advance-winner/",
            {"winner": None},
            format="json",
        )

        # Assert success
        self.assertEqual(response.status_code, 200)

        # Refresh from DB
        game.refresh_from_db()
        self.team2.refresh_from_db()

        # Winner should be cleared
        self.assertIsNone(game.winning_team)
        # Status must be a valid Game.status choice ("scheduled" is not one)
        self.assertEqual(game.status, "pending")
        # Loser's placement should be cleared
        self.assertIsNone(self.team2.placement)

    def test_advance_winner_unset_when_no_previous_winner(self):
        """Test that advance_winner with winner=null works when no winner set."""
        # Create a game with no winner
        game = Game.objects.create(
            tournament=self.tournament,
            bracket_type="winners",
            round=1,
            position=0,
            radiant_team=self.team1,
            dire_team=self.team2,
            status="pending",
        )

        # Call advance_winner with None
        response = self.client.post(
            f"/api/bracket/games/{game.pk}/advance-winner/",
            {"winner": None},
            format="json",
        )

        # Should still succeed
        self.assertEqual(response.status_code, 200)

        # Refresh from DB
        game.refresh_from_db()

        # Winner should remain None
        self.assertIsNone(game.winning_team)
        self.assertEqual(game.status, "pending")


class AdvanceWinnerPersistenceTest(TestCase):
    """Issue #466: a winner set from the match modal persists both paths."""

    def setUp(self) -> None:
        self.admin = CustomUser.objects.create_superuser(
            username="admin",
            password="admin123",
            email="admin@test.com",
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        self.teams: list[Team] = []
        for i in range(3):
            captain = CustomUser.objects.create_user(
                username=f"cap{i}", password="test"
            )
            self.teams.append(
                Team.objects.create(
                    name=f"Team {i + 1}", captain=captain, tournament=self.tournament
                )
            )
        self.winners_r2 = Game.objects.create(
            tournament=self.tournament, bracket_type="winners", round=2, position=0
        )
        self.losers_r2 = Game.objects.create(
            tournament=self.tournament,
            bracket_type="losers",
            round=2,
            position=0,
            radiant_team=self.teams[2],
        )
        self.winners_r1 = Game.objects.create(
            tournament=self.tournament,
            bracket_type="winners",
            round=1,
            position=0,
            radiant_team=self.teams[0],
            dire_team=self.teams[1],
            next_game=self.winners_r2,
            next_game_slot="radiant",
            loser_next_game=self.losers_r2,
            loser_next_game_slot="dire",
            elimination_type="double",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def _advance(self, game: Game, winner: str | None) -> Response:
        return self.client.post(
            f"/api/bracket/games/{game.pk}/advance-winner/",
            {"winner": winner},
            format="json",
        )

    def _bracket_by_pk(self) -> dict[int, dict]:
        response = self.client.get(f"/api/bracket/tournaments/{self.tournament.pk}/")
        self.assertEqual(response.status_code, 200)
        return {m["pk"]: m for m in response.data["matches"]}

    def test_winner_and_loser_advancement_survive_reload(self) -> None:
        response = self._advance(self.winners_r1, "radiant")
        self.assertEqual(response.status_code, 200)

        matches = self._bracket_by_pk()
        source = matches[self.winners_r1.pk]
        self.assertEqual(source["status"], "completed")
        self.assertEqual(source["winning_team"]["pk"], self.teams[0].pk)
        self.assertEqual(
            matches[self.winners_r2.pk]["radiant_team"]["pk"], self.teams[0].pk
        )
        loser_game = matches[self.losers_r2.pk]
        self.assertEqual(loser_game["dire_team"]["pk"], self.teams[1].pk)
        self.assertEqual(loser_game["radiant_team"]["pk"], self.teams[2].pk)

    def test_unset_clears_downstream_slots_and_resets_to_pending(self) -> None:
        self._advance(self.winners_r1, "radiant")

        response = self._advance(self.winners_r1, None)
        self.assertEqual(response.status_code, 200)

        matches = self._bracket_by_pk()
        source = matches[self.winners_r1.pk]
        self.assertEqual(source["status"], "pending")
        self.assertIsNone(source["winning_team"])
        self.assertIsNone(matches[self.winners_r2.pk]["radiant_team"])
        self.assertIsNone(matches[self.losers_r2.pk]["dire_team"])
        self.assertEqual(
            matches[self.losers_r2.pk]["radiant_team"]["pk"], self.teams[2].pk
        )

    def test_unset_keeps_downstream_slot_holding_another_team(self) -> None:
        self._advance(self.winners_r1, "radiant")
        self.winners_r2.refresh_from_db()
        self.winners_r2.radiant_team = self.teams[2]
        self.winners_r2.save()

        self._advance(self.winners_r1, None)

        self.winners_r2.refresh_from_db()
        self.assertEqual(self.winners_r2.radiant_team_id, self.teams[2].pk)

    def test_unset_rejected_when_downstream_match_completed(self) -> None:
        self._advance(self.winners_r1, "radiant")
        self._advance(self.losers_r2, "dire")

        response = self._advance(self.winners_r1, None)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "downstream_match_completed")
        self.winners_r1.refresh_from_db()
        self.assertEqual(self.winners_r1.winning_team_id, self.teams[0].pk)

    def test_changing_winner_replaces_both_advanced_teams(self) -> None:
        self._advance(self.winners_r1, "radiant")
        self._advance(self.winners_r1, None)

        self._advance(self.winners_r1, "dire")

        self.winners_r2.refresh_from_db()
        self.losers_r2.refresh_from_db()
        self.assertEqual(self.winners_r2.radiant_team_id, self.teams[1].pk)
        self.assertEqual(self.losers_r2.dire_team_id, self.teams[0].pk)

    def test_unset_grand_finals_clears_both_placements(self) -> None:
        grand_finals = Game.objects.create(
            tournament=self.tournament,
            bracket_type="grand_finals",
            round=1,
            position=0,
            radiant_team=self.teams[0],
            dire_team=self.teams[1],
        )
        self._advance(grand_finals, "radiant")

        self._advance(grand_finals, None)

        self.teams[0].refresh_from_db()
        self.teams[1].refresh_from_db()
        self.assertIsNone(self.teams[0].placement)
        self.assertIsNone(self.teams[1].placement)


class PlacementClearGuardTests(TeamManagementFixture, TestCase):
    """A placement clear that would put a player on two live teams is refused."""

    def setUp(self) -> None:
        super().setUp()
        self.admin = CustomUser.objects.create_superuser(
            username="guard_admin", password="admin123", email="guard@test.com"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.downstream = Game.objects.create(
            tournament=self.tournament, bracket_type="losers", round=2, position=0
        )
        self.losers_game = Game.objects.create(
            tournament=self.tournament,
            bracket_type="losers",
            round=1,
            position=0,
            radiant_team=self.team,
            dire_team=self.other,
            next_game=self.downstream,
            next_game_slot="radiant",
            elimination_type="double",
        )

    def _advance(self, game: Game, winner: str | None) -> Response:
        return self.client.post(
            f"/api/bracket/games/{game.pk}/advance-winner/",
            {"winner": winner},
            format="json",
        )

    def _placement(self, team: Team, placement: int | None) -> Response:
        return self.client.patch(
            f"/api/bracket/tournaments/{self.tournament.pk}/teams/{team.pk}/placement/",
            {"placement": placement},
            format="json",
        )

    def _take_over(self, team: Team, user: CustomUser) -> None:
        replace_captain(team, user, actor=self.actor, via=TeamLogVia.WEB, reason="r")

    def _assert_conflict(
        self, response: Response, team: Team, users: list[CustomUser]
    ) -> None:
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["code"], "roster_conflict")
        self.assertEqual(response.data["details"]["team_id"], team.pk)
        self.assertEqual(
            response.data["details"]["user_ids"], sorted(u.pk for u in users)
        )
        for user in users:
            self.assertIn(user.username, response.data["error"])

    def test_unset_losers_game_after_takeover_409_and_no_side_effects(self) -> None:
        self.assertEqual(self._advance(self.losers_game, "radiant").status_code, 200)
        eliminated = self.refresh(self.other)
        self.assertEqual(eliminated.placement, 4)
        self._take_over(self.team, self.o1)

        response = self._advance(self.losers_game, None)

        self._assert_conflict(response, self.other, [self.o1])
        self.assertIn(self.team.name, response.data["error"])
        self.assertEqual(self.refresh(self.other).placement, 4)
        self.downstream.refresh_from_db()
        self.assertEqual(self.downstream.radiant_team_id, self.team.pk)
        self.losers_game.refresh_from_db()
        self.assertEqual(self.losers_game.status, "completed")
        self.assertEqual(self.losers_game.winning_team_id, self.team.pk)

    def test_set_placement_null_after_takeover_409(self) -> None:
        eliminate(self.other, 4)
        self._take_over(self.team, self.o1)

        response = self._placement(self.other, None)

        self._assert_conflict(response, self.other, [self.o1])
        self.assertEqual(self.refresh(self.other).placement, 4)

    def test_set_placement_other_number_still_ok(self) -> None:
        eliminate(self.other, 4)
        self._take_over(self.team, self.o1)

        response = self._placement(self.other, 3)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.refresh(self.other).placement, 3)

    def test_no_overlap_unset_and_clear_still_work(self) -> None:
        self._advance(self.losers_game, "radiant")
        self.assertEqual(self.refresh(self.other).placement, 4)

        response = self._advance(self.losers_game, None)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(self.refresh(self.other).placement)
        self.downstream.refresh_from_db()
        self.assertIsNone(self.downstream.radiant_team_id)

        eliminate(self.other, 5)
        response = self._placement(self.other, None)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(self.refresh(self.other).placement)

    def test_grand_final_unset_checks_both_teams(self) -> None:
        grand_finals = Game.objects.create(
            tournament=self.tournament,
            bracket_type="grand_finals",
            round=1,
            position=0,
            radiant_team=self.team,
            dire_team=self.other,
        )
        self.assertEqual(self._advance(grand_finals, "radiant").status_code, 200)
        self.assertEqual(self.refresh(self.team).placement, 1)
        self.assertEqual(self.refresh(self.other).placement, 2)
        t1 = self.make_user("guard_t1")
        self.tournament.users.add(t1)
        third = Team.objects.create(
            tournament=self.tournament, name="Third", captain=t1
        )
        third.members.add(t1)
        self._take_over(third, self.m1)

        response = self._advance(grand_finals, None)

        self._assert_conflict(response, self.team, [self.m1])
        self.assertEqual(self.refresh(self.team).placement, 1)
        self.assertEqual(self.refresh(self.other).placement, 2)
        grand_finals.refresh_from_db()
        self.assertEqual(grand_finals.status, "completed")

    def test_grand_final_unset_catches_player_on_both_finalists(self) -> None:
        eliminate(self.team, 1)
        eliminate(self.other, 2)
        self.team.members.add(self.o1)
        grand_finals = Game.objects.create(
            tournament=self.tournament,
            bracket_type="grand_finals",
            round=1,
            position=0,
            radiant_team=self.team,
            dire_team=self.other,
            winning_team=self.team,
            status="completed",
        )

        response = self._advance(grand_finals, None)

        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["details"]["user_ids"], [self.o1.pk])
        self.assertEqual(self.refresh(self.team).placement, 1)
        self.assertEqual(self.refresh(self.other).placement, 2)

    def test_live_conflicts_ignores_left_members(self) -> None:
        eliminate(self.other, 4)
        self.team.left_members.add(self.o1)
        self.assertEqual(live_conflicts(self.refresh(self.other)), [])

        u = self.make_user("guard_left")
        self.other.left_members.add(u)
        self.team.members.add(u)
        self.assertEqual(live_conflicts(self.refresh(self.other)), [])

    def test_live_conflicts_counts_dropins(self) -> None:
        eliminate(self.other, 4)
        self.team.dropin_members.add(self.o1)
        self.assertEqual(live_conflicts(self.refresh(self.other)), [self.o1])

"""Tournament moves to `past` when its bracket final is decided (#419)."""

from datetime import date
from typing import Any
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from app.models import CustomUser, Game, Team, Tournament
from steam.functions.game_linking import _link_game_to_match
from steam.models import Match


class TournamentCompletionTestBase(TestCase):
    def setUp(self) -> None:
        self.admin = CustomUser.objects.create_superuser(
            username="admin", password="admin123", email="admin@test.com"
        )
        self.tournament = Tournament.objects.create(
            name="Completion Tournament",
            date_played=date.today(),
            state="in_progress",
        )
        self.team1 = Team.objects.create(
            name="Team 1",
            captain=CustomUser.objects.create_user(username="cap1", password="x"),
            tournament=self.tournament,
        )
        self.team2 = Team.objects.create(
            name="Team 2",
            captain=CustomUser.objects.create_user(username="cap2", password="x"),
            tournament=self.tournament,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def make_game(self, **kwargs: Any) -> Game:
        defaults: dict[str, Any] = {
            "tournament": self.tournament,
            "round": 1,
            "position": 0,
            "radiant_team": self.team1,
            "dire_team": self.team2,
        }
        defaults.update(kwargs)
        return Game.objects.create(**defaults)

    def advance(self, game: Game, winner: str | None) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"/api/bracket/games/{game.pk}/advance-winner/",
                {"winner": winner},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.content)

    def state(self) -> str:
        return Tournament.objects.get(pk=self.tournament.pk).state


class AdvanceWinnerCompletionTest(TournamentCompletionTestBase):
    def test_grand_finals_winner_marks_tournament_past(self) -> None:
        final = self.make_game(bracket_type="grand_finals")

        with capture_logs() as logs:
            self.advance(final, "radiant")

        self.assertEqual(self.state(), "past")
        events = [e for e in logs if e["event"] == "tournament_state_changed"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["system"], "tournament")
        self.assertEqual(events[0]["subsystem"], "completion")
        self.assertEqual(events[0]["tournament_id"], self.tournament.pk)
        self.assertEqual(events[0]["from_state"], "in_progress")
        self.assertEqual(events[0]["to_state"], "past")
        self.assertEqual(events[0]["final_game_id"], final.pk)

    def test_future_tournament_also_moves_to_past(self) -> None:
        Tournament.objects.filter(pk=self.tournament.pk).update(state="future")
        final = self.make_game(bracket_type="grand_finals")

        self.advance(final, "dire")

        self.assertEqual(self.state(), "past")

    def test_non_final_winner_leaves_tournament_in_progress(self) -> None:
        final = self.make_game(bracket_type="grand_finals", radiant_team=None)
        semi = self.make_game(
            bracket_type="winners", next_game=final, next_game_slot="radiant"
        )

        self.advance(semi, "radiant")

        self.assertEqual(self.state(), "in_progress")

    def test_redeciding_final_is_idempotent(self) -> None:
        final = self.make_game(bracket_type="grand_finals")
        self.advance(final, "radiant")

        with capture_logs() as logs:
            self.advance(final, "dire")

        self.assertEqual(self.state(), "past")
        self.assertFalse([e for e in logs if e["event"] == "tournament_state_changed"])

    def test_unsetting_final_winner_reopens_tournament(self) -> None:
        final = self.make_game(bracket_type="grand_finals")
        self.advance(final, "radiant")

        with capture_logs() as logs:
            self.advance(final, None)

        self.assertEqual(self.state(), "in_progress")
        events = [e for e in logs if e["event"] == "tournament_state_changed"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["from_state"], "past")
        self.assertEqual(events[0]["to_state"], "in_progress")
        self.assertEqual(events[0]["reason"], "final_result_cleared")

    def test_unsetting_non_final_winner_never_moves_past_backwards(self) -> None:
        final = self.make_game(bracket_type="grand_finals", radiant_team=None)
        semi = self.make_game(
            bracket_type="winners", next_game=final, next_game_slot="radiant"
        )
        self.advance(semi, "radiant")
        Tournament.objects.filter(pk=self.tournament.pk).update(state="past")

        self.advance(semi, None)

        self.assertEqual(self.state(), "past")

    def test_unsetting_undecided_final_keeps_manual_past(self) -> None:
        final = self.make_game(bracket_type="grand_finals")
        Tournament.objects.filter(pk=self.tournament.pk).update(state="past")

        self.advance(final, None)

        self.assertEqual(self.state(), "past")


class BracketShapeCompletionTest(TournamentCompletionTestBase):
    def test_single_elimination_terminal_game_marks_past(self) -> None:
        final = self.make_game(
            bracket_type="winners", round=2, elimination_type="single"
        )
        semi = self.make_game(
            bracket_type="winners",
            elimination_type="single",
            next_game=final,
            next_game_slot="radiant",
        )
        self.advance(semi, "radiant")
        self.assertEqual(self.state(), "in_progress")

        self.advance(final, "radiant")

        self.assertEqual(self.state(), "past")

    def test_swiss_games_never_mark_past(self) -> None:
        game = self.make_game(bracket_type="swiss", elimination_type="swiss")

        self.advance(game, "radiant")

        self.assertEqual(self.state(), "in_progress")

    def test_double_elim_winners_final_does_not_mark_past(self) -> None:
        self.make_game(bracket_type="grand_finals", radiant_team=None)
        winners_final = self.make_game(bracket_type="winners", round=2)

        self.advance(winners_final, "radiant")

        self.assertEqual(self.state(), "in_progress")


class SaveBracketCompletionTest(TournamentCompletionTestBase):
    def save(self, gf_winner: str | None) -> None:
        matches = [
            {
                "id": "w-1-0",
                "round": 1,
                "position": 0,
                "bracketType": "winners",
                "eliminationType": "double",
                "radiantTeam": {"pk": self.team1.pk},
                "direTeam": {"pk": self.team2.pk},
                "status": "completed",
                "winner": "radiant",
                "nextMatchId": "gf-1-0",
                "nextMatchSlot": "radiant",
            },
            {
                "id": "gf-1-0",
                "round": 1,
                "position": 0,
                "bracketType": "grand_finals",
                "eliminationType": "double",
                "radiantTeam": {"pk": self.team1.pk},
                "direTeam": {"pk": self.team2.pk},
                "status": "completed" if gf_winner else "pending",
                "winner": gf_winner,
            },
        ]
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"/api/bracket/tournaments/{self.tournament.pk}/save/",
                {"matches": matches},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.content)

    def test_saving_bracket_with_decided_final_marks_past(self) -> None:
        self.save(gf_winner=None)
        self.assertEqual(self.state(), "in_progress")

        self.save(gf_winner="dire")

        self.assertEqual(self.state(), "past")

    def test_saving_bracket_that_clears_final_reopens(self) -> None:
        self.save(gf_winner="dire")
        self.assertEqual(self.state(), "past")

        self.save(gf_winner=None)

        self.assertEqual(self.state(), "in_progress")


class SteamLinkCompletionTest(TournamentCompletionTestBase):
    def test_linking_final_to_match_marks_past(self) -> None:
        final = self.make_game(bracket_type="grand_finals")
        match = Match.objects.create(
            match_id=8100000001,
            radiant_win=True,
            duration=1800,
            start_time=1700000000,
            game_mode=2,
            lobby_type=1,
        )

        with (
            mock.patch(
                "steam.functions.game_linking._determine_winner_from_match",
                return_value=self.team1,
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            _link_game_to_match(final, match)

        self.assertEqual(self.state(), "past")

    def test_unlinking_final_match_reopens(self) -> None:
        final = self.make_game(
            bracket_type="grand_finals",
            winning_team=self.team1,
            status="completed",
            gameid=8100000002,
        )
        Tournament.objects.filter(pk=self.tournament.pk).update(state="past")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(f"/api/steam/games/{final.pk}/unlink-match/")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.state(), "in_progress")

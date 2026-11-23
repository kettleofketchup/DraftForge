"""Issue #843: every result-entry path keeps Team.placement in step with the bracket."""

from datetime import date
from typing import Any
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser
from steam.functions.game_linking import _link_game_to_match
from steam.models import Match
from tournament.models import Game, Team, Tournament


class PlacementTestBase(TestCase):
    team_count = 4

    def setUp(self) -> None:
        self.admin = CustomUser.objects.create_superuser(
            username="admin", password="admin123", email="admin@test.com"
        )
        self.tournament = Tournament.objects.create(
            name="Placement Tournament", date_played=date.today(), state="in_progress"
        )
        self.teams: list[Team] = [
            Team.objects.create(
                name=f"Team {i}",
                captain=CustomUser.objects.create_user(
                    username=f"cap{i}", password="x"
                ),
                tournament=self.tournament,
            )
            for i in range(self.team_count)
        ]
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def advance(self, game: Game, winner: str | None) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"/api/bracket/games/{game.pk}/advance-winner/",
                {"winner": winner},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.content)

    def save_bracket(self, matches: list[dict[str, Any]]) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"/api/bracket/tournaments/{self.tournament.pk}/save/",
                {"matches": matches},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.content)

    def placements(self) -> list[int | None]:
        return [Team.objects.get(pk=t.pk).placement for t in self.teams]

    def set_placement(self, team: Team, placement: int | None) -> None:
        Team.objects.filter(pk=team.pk).update(placement=placement)


class SingleEliminationBracket(PlacementTestBase):
    """4 teams: two semis (round 1) feed one final (round 2)."""

    def setUp(self) -> None:
        super().setUp()
        t = self.teams
        self.final = Game.objects.create(
            tournament=self.tournament,
            bracket_type="winners",
            elimination_type="single",
            round=2,
            position=0,
        )
        self.semi1 = Game.objects.create(
            tournament=self.tournament,
            bracket_type="winners",
            elimination_type="single",
            round=1,
            position=0,
            radiant_team=t[0],
            dire_team=t[1],
            next_game=self.final,
            next_game_slot="radiant",
        )
        self.semi2 = Game.objects.create(
            tournament=self.tournament,
            bracket_type="winners",
            elimination_type="single",
            round=1,
            position=1,
            radiant_team=t[2],
            dire_team=t[3],
            next_game=self.final,
            next_game_slot="dire",
        )

    def refresh_final(self) -> Game:
        return Game.objects.get(pk=self.final.pk)


class SingleEliminationAdvanceWinnerTest(SingleEliminationBracket):
    def test_semi_loser_gets_third(self) -> None:
        self.advance(self.semi1, "radiant")

        self.assertEqual(self.placements(), [None, 3, None, None])

    def test_full_bracket_places_every_team(self) -> None:
        self.advance(self.semi1, "radiant")
        self.advance(self.semi2, "dire")
        self.advance(self.refresh_final(), "dire")

        self.assertEqual(self.placements(), [2, 3, 3, 1])

    def test_changing_a_result_moves_the_placement(self) -> None:
        self.advance(self.semi1, "radiant")

        self.advance(self.semi1, "dire")

        self.assertEqual(self.placements(), [3, None, None, None])

    def test_unsetting_a_result_clears_the_placement(self) -> None:
        self.advance(self.semi1, "radiant")

        self.advance(self.semi1, None)

        self.assertEqual(self.placements(), [None, None, None, None])

    def test_unsetting_the_final_clears_first_and_second(self) -> None:
        self.advance(self.semi1, "radiant")
        self.advance(self.semi2, "radiant")
        self.advance(self.refresh_final(), "radiant")

        self.advance(self.refresh_final(), None)

        self.assertEqual(self.placements(), [None, 3, None, 3])

    def test_manual_placement_of_an_unaffected_team_survives(self) -> None:
        self.advance(self.semi1, "radiant")
        self.advance(self.semi2, "radiant")
        self.set_placement(self.teams[3], 4)

        self.advance(self.refresh_final(), "radiant")

        self.assertEqual(self.placements(), [1, 3, 2, 4])

    def test_missing_placement_from_an_earlier_result_is_filled(self) -> None:
        Game.objects.filter(pk=self.semi1.pk).update(
            winning_team=self.teams[0], status="completed"
        )
        Game.objects.filter(pk=self.final.pk).update(radiant_team=self.teams[0])

        self.advance(self.semi2, "radiant")

        self.assertEqual(self.placements(), [None, 3, None, 3])


class SingleEliminationEightTeamTest(PlacementTestBase):
    team_count = 8

    def test_quarter_final_loser_gets_fifth(self) -> None:
        semi = Game.objects.create(
            tournament=self.tournament,
            bracket_type="winners",
            elimination_type="single",
            round=2,
            position=0,
        )
        Game.objects.create(
            tournament=self.tournament,
            bracket_type="winners",
            elimination_type="single",
            round=3,
            position=0,
        )
        quarter = Game.objects.create(
            tournament=self.tournament,
            bracket_type="winners",
            elimination_type="single",
            round=1,
            position=0,
            radiant_team=self.teams[0],
            dire_team=self.teams[1],
            next_game=semi,
            next_game_slot="radiant",
        )

        self.advance(quarter, "radiant")

        self.assertEqual(self.placements()[:2], [None, 5])


def single_elim_matches(
    teams: list[Team],
    semi1: str | None = None,
    semi2: str | None = None,
    final: str | None = None,
) -> list[dict[str, Any]]:
    def winner_of(slot: str | None, radiant: Team, dire: Team) -> Team | None:
        return {"radiant": radiant, "dire": dire}.get(slot or "")

    s1 = winner_of(semi1, teams[0], teams[1])
    s2 = winner_of(semi2, teams[2], teams[3])

    def match(
        mid: str,
        rnd: int,
        pos: int,
        radiant: Team | None,
        dire: Team | None,
        winner: str | None,
        **links: Any,
    ) -> dict[str, Any]:
        return {
            "id": mid,
            "round": rnd,
            "position": pos,
            "bracketType": "winners",
            "eliminationType": "single",
            "radiantTeam": {"pk": radiant.pk} if radiant else None,
            "direTeam": {"pk": dire.pk} if dire else None,
            "status": "completed" if winner else "pending",
            "winner": winner,
            **links,
        }

    return [
        match(
            "w-1-0",
            1,
            0,
            teams[0],
            teams[1],
            semi1,
            nextMatchId="w-2-0",
            nextMatchSlot="radiant",
        ),
        match(
            "w-1-1",
            1,
            1,
            teams[2],
            teams[3],
            semi2,
            nextMatchId="w-2-0",
            nextMatchSlot="dire",
        ),
        match("w-2-0", 2, 0, s1, s2, final),
    ]


class SingleEliminationSaveBracketTest(PlacementTestBase):
    def test_saved_results_set_placements(self) -> None:
        self.save_bracket(single_elim_matches(self.teams, "radiant", "dire", "radiant"))

        self.assertEqual(self.placements(), [1, 3, 3, 2])

    def test_saving_a_cleared_result_clears_its_placement(self) -> None:
        self.save_bracket(single_elim_matches(self.teams, "radiant", "dire"))
        self.assertEqual(self.placements(), [None, 3, 3, None])

        self.save_bracket(single_elim_matches(self.teams, "radiant"))

        self.assertEqual(self.placements(), [None, 3, None, None])


def double_elim_matches(
    teams: list[Team], results: dict[str, str]
) -> list[dict[str, Any]]:
    """The 4-team double-elimination preset with ``results`` (match id -> slot)."""
    t0, t1, t2, t3 = teams
    layout: list[dict[str, Any]] = [
        {
            "id": "w-1-0",
            "bracketType": "winners",
            "round": 1,
            "position": 0,
            "eliminationType": "double",
            "nextMatchId": "w-2-0",
            "nextMatchSlot": "radiant",
            "loserNextMatchId": "l-1-0",
            "loserNextMatchSlot": "radiant",
        },
        {
            "id": "w-1-1",
            "bracketType": "winners",
            "round": 1,
            "position": 1,
            "eliminationType": "double",
            "nextMatchId": "w-2-0",
            "nextMatchSlot": "dire",
            "loserNextMatchId": "l-1-0",
            "loserNextMatchSlot": "dire",
        },
        {
            "id": "w-2-0",
            "bracketType": "winners",
            "round": 2,
            "position": 0,
            "eliminationType": "double",
            "nextMatchId": "gf-1-0",
            "nextMatchSlot": "radiant",
            "loserNextMatchId": "l-2-0",
            "loserNextMatchSlot": "radiant",
        },
        {
            "id": "l-1-0",
            "bracketType": "losers",
            "round": 1,
            "position": 0,
            "eliminationType": "single",
            "nextMatchId": "l-2-0",
            "nextMatchSlot": "dire",
        },
        {
            "id": "l-2-0",
            "bracketType": "losers",
            "round": 2,
            "position": 0,
            "eliminationType": "single",
            "nextMatchId": "gf-1-0",
            "nextMatchSlot": "dire",
        },
        {
            "id": "gf-1-0",
            "bracketType": "grand_finals",
            "round": 1,
            "position": 0,
            "eliminationType": "single",
        },
    ]
    slots: dict[str, dict[str, Team | None]] = {
        m["id"]: {"radiant": None, "dire": None} for m in layout
    }
    slots["w-1-0"] = {"radiant": t0, "dire": t3}
    slots["w-1-1"] = {"radiant": t1, "dire": t2}
    for m in layout:
        winner = results.get(m["id"])
        here = slots[m["id"]]
        m["radiantTeam"] = {"pk": here["radiant"].pk} if here["radiant"] else None
        m["direTeam"] = {"pk": here["dire"].pk} if here["dire"] else None
        m["winner"] = winner
        m["status"] = "completed" if winner else "pending"
        if not winner:
            continue
        loser_slot = "dire" if winner == "radiant" else "radiant"
        if m.get("nextMatchId"):
            slots[m["nextMatchId"]][m["nextMatchSlot"]] = here[winner]
        if m.get("loserNextMatchId"):
            slots[m["loserNextMatchId"]][m["loserNextMatchSlot"]] = here[loser_slot]
    return layout


class DoubleEliminationSaveBracketTest(PlacementTestBase):
    def test_saved_losers_round_result_places_the_loser(self) -> None:
        self.save_bracket(
            double_elim_matches(
                self.teams, {"w-1-0": "radiant", "w-1-1": "radiant", "l-1-0": "radiant"}
            )
        )

        # l-1-0 is Team 3 (radiant) vs Team 2 (dire); Team 2 is out.
        self.assertEqual(self.placements(), [None, None, 4, None])

    def test_saved_full_bracket_matches_advance_winner_placements(self) -> None:
        self.save_bracket(
            double_elim_matches(
                self.teams,
                {
                    "w-1-0": "radiant",
                    "w-1-1": "radiant",
                    "w-2-0": "radiant",
                    "l-1-0": "radiant",
                    "l-2-0": "radiant",
                    "gf-1-0": "dire",
                },
            )
        )

        self.assertEqual(self.placements(), [2, 1, 4, 3])

    def test_saving_a_cleared_result_clears_its_placement(self) -> None:
        results = {"w-1-0": "radiant", "w-1-1": "radiant", "l-1-0": "radiant"}
        self.save_bracket(double_elim_matches(self.teams, results))

        del results["l-1-0"]
        self.save_bracket(double_elim_matches(self.teams, results))

        self.assertEqual(self.placements(), [None, None, None, None])


class SteamLinkPlacementTest(SingleEliminationBracket):
    def link(self, game: Game, winner: Team, match_id: int) -> None:
        match = Match.objects.create(
            match_id=match_id,
            radiant_win=True,
            duration=1800,
            start_time=1700000000,
            game_mode=2,
            lobby_type=1,
        )
        with (
            mock.patch(
                "steam.functions.game_linking._determine_winner_from_match",
                return_value=winner,
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            _link_game_to_match(game, match)

    def test_auto_linked_result_places_the_loser(self) -> None:
        self.link(self.semi1, self.teams[0], 8430000001)

        self.assertEqual(self.placements(), [None, 3, None, None])

    def test_unlinking_the_match_clears_the_placement(self) -> None:
        self.link(self.semi1, self.teams[0], 8430000002)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(
                f"/api/steam/games/{self.semi1.pk}/unlink-match/"
            )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.placements(), [None, None, None, None])


class SwissPlacementTest(PlacementTestBase):
    def test_swiss_results_leave_placement_alone(self) -> None:
        self.set_placement(self.teams[1], 7)
        game = Game.objects.create(
            tournament=self.tournament,
            bracket_type="swiss",
            elimination_type="swiss",
            round=1,
            position=0,
            radiant_team=self.teams[0],
            dire_team=self.teams[1],
        )

        self.advance(game, "radiant")

        self.assertEqual(self.placements(), [None, 7, None, None])

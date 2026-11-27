"""Tests for refusing a bracket Save built from a stale copy (issue #963)."""

from typing import Any

from django.test import TestCase
from rest_framework.response import Response

from app.models import CustomUser
from tournament.models import Team, Tournament
from tournament.tests import test_bracket


class SaveBracketStaleVersionTest(TestCase):
    """Issue #963: a Save built from an older bracket must not undo newer results."""

    setUp = test_bracket.AdvanceWinnerPersistenceTest.setUp
    _advance = test_bracket.AdvanceWinnerPersistenceTest._advance

    def _version(self) -> str:
        response = self.client.get(f"/api/bracket/tournaments/{self.tournament.pk}/")
        self.assertEqual(response.status_code, 200)
        version = response.data["version"]
        self.assertIsInstance(version, str)
        return version

    def _payload(self, winner: str | None = None) -> list[dict[str, Any]]:
        return [
            {
                "id": "w-1-0",
                "round": 1,
                "position": 0,
                "bracketType": "winners",
                "eliminationType": "double",
                "radiantTeam": {"pk": self.teams[0].pk},
                "direTeam": {"pk": self.teams[1].pk},
                "winner": winner,
                "status": "completed" if winner else "pending",
                "nextMatchId": "w-2-0",
                "nextMatchSlot": "radiant",
                "loserNextMatchId": "l-2-0",
                "loserNextMatchSlot": "dire",
            },
            {
                "id": "w-2-0",
                "round": 2,
                "position": 0,
                "bracketType": "winners",
                "eliminationType": "double",
                "radiantTeam": {"pk": self.teams[0].pk} if winner else None,
                "status": "pending",
            },
            {
                "id": "l-2-0",
                "round": 2,
                "position": 0,
                "bracketType": "losers",
                "eliminationType": "double",
                "radiantTeam": {"pk": self.teams[2].pk},
                "direTeam": {"pk": self.teams[1].pk} if winner else None,
                "status": "pending",
            },
        ]

    def _save(self, matches: list[dict[str, Any]], version: str | None) -> Response:
        return self.client.post(
            f"/api/bracket/tournaments/{self.tournament.pk}/save/",
            {"matches": matches, "version": version},
            format="json",
        )

    def test_stale_save_is_refused_and_keeps_newer_winner(self) -> None:
        loaded = self._version()
        self.assertEqual(self._advance(self.winners_r1, "radiant").status_code, 200)

        response = self._save(self._payload(), loaded)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "bracket_stale")
        self.winners_r1.refresh_from_db()
        self.assertEqual(self.winners_r1.winning_team_id, self.teams[0].pk)
        self.assertEqual(self.winners_r1.status, "completed")

    def test_save_from_current_version_succeeds_and_returns_new_version(self) -> None:
        response = self._save(self._payload("radiant"), self._version())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["version"], self._version())
        self.winners_r1.refresh_from_db()
        self.assertEqual(self.winners_r1.winning_team_id, self.teams[0].pk)

    def test_second_save_from_same_version_is_refused(self) -> None:
        loaded = self._version()
        self.assertEqual(self._save(self._payload("radiant"), loaded).status_code, 200)

        response = self._save(self._payload(), loaded)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "bracket_stale")
        self.winners_r1.refresh_from_db()
        self.assertEqual(self.winners_r1.winning_team_id, self.teams[0].pk)

    def test_version_ignores_lobby_state(self) -> None:
        before = self._version()
        self.winners_r1.lobbies.create(external_ref="ref", state="in_game")

        self.assertEqual(self._version(), before)

    def test_foreign_team_is_refused_even_with_current_version(self) -> None:
        other = Tournament.objects.create(
            name="Other", date_played=self.tournament.date_played
        )
        foreign = Team.objects.create(
            name="Foreign",
            captain=CustomUser.objects.create_user(username="foreign", password="test"),
            tournament=other,
        )
        loaded = self._version()
        matches = self._payload()
        matches[0]["radiantTeam"] = {"pk": foreign.pk}

        response = self._save(matches, loaded)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "team_not_in_tournament")
        self.assertEqual(self._version(), loaded)

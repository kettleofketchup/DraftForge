from typing import Any

from django.test import RequestFactory, TestCase
from rest_framework.request import Request
from rest_framework.test import APIClient

from app.models import CustomUser, League
from steam.constants import LEAGUE_ID
from steam.models import LeaguePlayerStats
from steam.tests.league_summary_fixtures import make_player
from steam.views import LeaderboardView

URL = "/api/steam/leaderboard/"


class LeaderboardViewTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        League.objects.create(name="Leaderboard League", steam_league_id=LEAGUE_ID)
        self._seq = 0

    def _row(self, win_rate: float, games_played: int = 10) -> CustomUser:
        self._seq += 1
        user = make_player(f"lb_user_{self._seq}", 76561198000300000 + self._seq)
        LeaguePlayerStats.objects.create(
            user=user,
            league_id=LEAGUE_ID,
            games_played=games_played,
            win_rate=win_rate,
        )
        return user

    def _results(self, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        response = self.client.get(URL, params or {})
        self.assertEqual(response.status_code, 200)
        return response.json()["results"]

    def _ordering(self, params: dict[str, str]) -> tuple[str, ...]:
        request = Request(RequestFactory().get(URL, params))
        return tuple(LeaderboardView(request=request).get_queryset().query.order_by)

    def test_default_request_200_sorted_by_win_rate(self) -> None:
        for rate in (0.4, 0.8, 0.6):
            self._row(rate)
        rates = [r["win_rate"] for r in self._results()]
        self.assertEqual(rates, [0.8, 0.6, 0.4])

    def test_league_mmr_sort_key_falls_back_to_win_rate(self) -> None:
        for rate in (0.4, 0.8, 0.6):
            self._row(rate)
        rates = [r["win_rate"] for r in self._results({"sort_by": "league_mmr"})]
        self.assertEqual(rates, [0.8, 0.6, 0.4])

    def test_unknown_sort_key_falls_back(self) -> None:
        for rate in (0.4, 0.8, 0.6):
            self._row(rate)
        rates = [r["win_rate"] for r in self._results({"sort_by": "bogus"})]
        self.assertEqual(rates, [0.8, 0.6, 0.4])

    def _assert_ties_stable(self, order: str) -> None:
        users = [self._row(0.5) for _ in range(3)]
        page1 = self._results({"order": order, "page_size": 2, "page": 1})
        page2 = self._results({"order": order, "page_size": 2, "page": 2})
        ids = [r["user_id"] for r in page1 + page2]
        self.assertEqual(ids, [u.pk for u in users])

    def test_ties_stable_across_pages_desc(self) -> None:
        self._assert_ties_stable("desc")

    def test_ties_stable_across_pages_asc(self) -> None:
        self._assert_ties_stable("asc")

    def test_secondary_sort_by_games(self) -> None:
        few = self._row(0.5, games_played=6)
        many = self._row(0.5, games_played=20)
        for order in ("desc", "asc"):
            with self.subTest(order=order):
                ids = [r["user_id"] for r in self._results({"order": order})]
                self.assertEqual(ids, [many.pk, few.pk])

    def test_games_played_sort_drops_games_tiebreak(self) -> None:
        users = [self._row(rate, games_played=8) for rate in (0.2, 0.9, 0.5)]
        ids = [r["user_id"] for r in self._results({"sort_by": "games_played"})]
        self.assertEqual(ids, [u.pk for u in users])

    def test_ordering_tuple(self) -> None:
        self.assertEqual(self._ordering({}), ("-win_rate", "-games_played", "pk"))
        self.assertEqual(
            self._ordering({"order": "asc"}), ("win_rate", "-games_played", "pk")
        )
        self.assertEqual(
            self._ordering({"sort_by": "games_played"}), ("-games_played", "pk")
        )

from django.db import connection, reset_queries
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from app.models import League
from steam.tests.league_summary_fixtures import make_player, record_series
from tests.cache import flush_run_cache

STEAM_LEAGUE = 90011
PLAYER_KEYS = {
    "rank",
    "top_percent",
    "games",
    "wins",
    "losses",
    "win_rate",
    "bucket",
    "recent",
    "streak",
}


def summaries_url(league_pk: int) -> str:
    return f"/api/steam/leagues/{league_pk}/player-summaries/"


class LeaguePlayerSummariesViewTests(TestCase):
    def setUp(self) -> None:
        flush_run_cache()
        self.client = APIClient()
        self.league = League.objects.create(
            name="Summary League", steam_league_id=STEAM_LEAGUE
        )

    def _add_players(self, start: int, count: int) -> None:
        for i in range(start, start + count):
            user = make_player(f"summary_user_{i}", 76561198000100000 + i)
            record_series(
                user, "WWLWW", league_id=STEAM_LEAGUE, first_match_id=10_000 + i * 10
            )

    def test_unknown_league_404(self) -> None:
        response = self.client.get(summaries_url(999999))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "League not found"})

    def test_league_without_steam_id_empty(self) -> None:
        league = League.objects.create(name="No Steam", steam_league_id=None)
        response = self.client.get(summaries_url(league.pk))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["league_pk"], league.pk)
        self.assertIsNone(body["steam_league_id"])
        self.assertEqual(body["population"], 0)
        self.assertEqual(body["players"], {})
        buckets = body["distribution"]["buckets"]
        self.assertEqual(len(buckets), 10)
        self.assertTrue(all(b["count"] == 0 for b in buckets))

    def test_payload_shape(self) -> None:
        user = make_player("shape_user", 76561198000100999)
        record_series(user, "WWLWW", league_id=STEAM_LEAGUE, first_match_id=20_000)
        response = self.client.get(summaries_url(self.league.pk))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            set(body),
            {
                "league_pk",
                "steam_league_id",
                "min_games",
                "population",
                "players",
                "distribution",
            },
        )
        self.assertEqual(body["league_pk"], self.league.pk)
        self.assertEqual(body["steam_league_id"], STEAM_LEAGUE)
        self.assertEqual(body["population"], 1)
        player = body["players"][str(user.pk)]
        self.assertEqual(set(player), PLAYER_KEYS)
        self.assertEqual(player["rank"], 1)
        self.assertEqual(player["games"], 5)
        self.assertEqual(body["distribution"]["bucket_size"], 10)

    def test_query_count_constant(self) -> None:
        self._add_players(0, 5)
        flush_run_cache()
        reset_queries()
        with CaptureQueriesContext(connection) as small:
            self.assertEqual(
                self.client.get(summaries_url(self.league.pk)).status_code, 200
            )
        small_count = len(small.captured_queries)
        self.assertEqual(small_count, 2)
        self._add_players(5, 45)
        flush_run_cache()
        reset_queries()
        with self.assertNumQueries(small_count):
            response = self.client.get(summaries_url(self.league.pk))
        self.assertEqual(response.json()["population"], 50)

    def test_anonymous_get_200(self) -> None:
        response = APIClient().get(summaries_url(self.league.pk))
        self.assertEqual(response.status_code, 200)


class LeaguePlayerSummariesViewCacheTests(TransactionTestCase):
    def setUp(self) -> None:
        flush_run_cache()
        self.client = APIClient()
        self.league = League.objects.create(
            name="Cached Summary League", steam_league_id=STEAM_LEAGUE
        )
        user = make_player("cached_view_user", 76561198000101000)
        record_series(user, "WWLWW", league_id=STEAM_LEAGUE, first_match_id=30_000)
        flush_run_cache()

    def test_cold_then_warm_query_counts(self) -> None:
        reset_queries()
        with self.assertNumQueries(2):
            first = self.client.get(summaries_url(self.league.pk))
        reset_queries()
        with CaptureQueriesContext(connection) as warm:
            second = self.client.get(summaries_url(self.league.pk))
        self.assertLessEqual(len(warm.captured_queries), 1)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json(), second.json())

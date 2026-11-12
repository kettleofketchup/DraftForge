from django.http import HttpResponse
from django.test import TestCase
from rest_framework.test import APIClient

from app.models import League
from steam.constants import LEAGUE_ID
from steam.models import LeaguePlayerStats
from steam.tests.league_summary_fixtures import make_player

MAPPED_STEAM_LEAGUE = 90001


class LeagueStatsViewTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.user = make_player("league_stats_user", 76561198000200001)
        self.league = League.objects.create(
            name="Mapped League", steam_league_id=MAPPED_STEAM_LEAGUE
        )
        LeaguePlayerStats.objects.create(
            user=self.user, league_id=LEAGUE_ID, games_played=3, wins=2, losses=1
        )
        LeaguePlayerStats.objects.create(
            user=self.user,
            league_id=MAPPED_STEAM_LEAGUE,
            games_played=7,
            wins=4,
            losses=3,
        )

    def _get(self, query: str = "") -> HttpResponse:
        return self.client.get(f"/api/steam/league-stats/{self.user.pk}/{query}")

    def test_league_pk_maps_to_steam_id(self) -> None:
        response = self._get(f"?league={self.league.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["league_id"], MAPPED_STEAM_LEAGUE)
        self.assertEqual(response.json()["games_played"], 7)

    def test_league_beats_league_id(self) -> None:
        response = self._get(f"?league={self.league.pk}&league_id={LEAGUE_ID}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["league_id"], MAPPED_STEAM_LEAGUE)

    def test_default_league_id_still_works(self) -> None:
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["league_id"], LEAGUE_ID)

    def test_legacy_league_id_param(self) -> None:
        response = self._get(f"?league_id={LEAGUE_ID}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["league_id"], LEAGUE_ID)

    def test_league_not_int_400(self) -> None:
        response = self._get("?league=abc")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Invalid league"})

    def test_league_id_not_int_400(self) -> None:
        response = self._get("?league_id=abc")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Invalid league_id"})

    def test_league_abc_with_valid_league_id_400(self) -> None:
        response = self._get(f"?league=abc&league_id={LEAGUE_ID}")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Invalid league"})

    def test_league_empty_string_400(self) -> None:
        response = self._get("?league=")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Invalid league"})

    def test_league_without_steam_id_404(self) -> None:
        league = League.objects.create(name="No Steam", steam_league_id=None)
        response = self._get(f"?league={league.pk}")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "League not found"})

    def test_unknown_league_404(self) -> None:
        response = self._get("?league=999999")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "League not found"})

    def test_missing_stats_404_unchanged(self) -> None:
        league = League.objects.create(name="Empty", steam_league_id=90002)
        response = self._get(f"?league={league.pk}")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(), {"error": "No league stats found for this user"}
        )

    def test_anonymous_get_200(self) -> None:
        self.client.logout()
        response = self._get()
        self.assertEqual(response.status_code, 200)

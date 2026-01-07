from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from app.models import CustomUser, PositionsModel
from steam.constants import LEAGUE_ID
from steam.models import LeaguePlayerStats


class TestLeaderboardAPI(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.positions = PositionsModel.objects.create()

        # Create test users with stats
        self.users = []
        for i in range(5):
            user = CustomUser.objects.create_user(
                username=f"player{i}",
                password="testpass",
                mmr=3000 + i * 200,
                league_mmr=3000 + i * 200 + (i * 50),
                positions=self.positions,
            )
            self.users.append(user)
            LeaguePlayerStats.objects.create(
                user=user,
                league_id=LEAGUE_ID,
                games_played=10 + i,
                wins=5 + i,
                losses=5,
                win_rate=(5 + i) / (10 + i),
                avg_kills=8 + i,
                avg_deaths=5,
                avg_assists=10,
                avg_gpm=450 + i * 20,
                avg_xpm=500 + i * 20,
                mmr_adjustment=i * 50,
            )

    def test_leaderboard_returns_sorted_by_league_mmr(self):
        response = self.client.get(reverse("leaderboard"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        self.assertEqual(len(results), 5)
        # Should be sorted by league_mmr descending
        mmrs = [r["league_mmr"] for r in results]
        self.assertEqual(mmrs, sorted(mmrs, reverse=True))

    def test_leaderboard_pagination(self):
        response = self.client.get(reverse("leaderboard"), {"page_size": 2})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertIsNotNone(response.data["next"])

    def test_leaderboard_sort_by_win_rate(self):
        response = self.client.get(
            reverse("leaderboard"),
            {"sort_by": "win_rate", "order": "desc"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        win_rates = [r["win_rate"] for r in results]
        self.assertEqual(win_rates, sorted(win_rates, reverse=True))

    def test_league_stats_returns_user_stats(self):
        user = self.users[0]
        response = self.client.get(reverse("league-stats", kwargs={"user_id": user.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], user.username)
        self.assertEqual(response.data["games_played"], 10)

    def test_league_stats_404_for_unknown_user(self):
        response = self.client.get(reverse("league-stats", kwargs={"user_id": 99999}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_my_league_stats_requires_auth(self):
        response = self.client.get(reverse("my-league-stats"))
        # DRF returns 403 Forbidden for unauthenticated requests
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_my_league_stats_returns_authenticated_user_stats(self):
        user = self.users[0]
        self.client.force_authenticate(user=user)
        response = self.client.get(reverse("my-league-stats"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], user.username)

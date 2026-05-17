from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from app.models import CustomUser
from steam.models import Match, PlayerMatchStats

TOKEN = "test-internal-token"
HEADERS = {"HTTP_X_INTERNAL_TOKEN": TOKEN}


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class SteamSyncStateEndpointTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/internal/steam/sync-state/12345/"

    def test_get_creates_state_if_missing(self):
        resp = self.client.get(self.url, **HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["league_id"], 12345)
        self.assertFalse(data["is_syncing"])
        self.assertIsNone(data["last_match_id"])
        self.assertEqual(data["failed_match_ids"], [])

    def test_get_returns_existing_state(self):
        from steam.models import LeagueSyncState

        LeagueSyncState.objects.create(
            league_id=12345,
            is_syncing=True,
            last_match_id=99999,
            failed_match_ids=[111, 222],
        )
        resp = self.client.get(self.url, **HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["league_id"], 12345)
        self.assertTrue(data["is_syncing"])
        self.assertEqual(data["last_match_id"], 99999)
        self.assertEqual(data["failed_match_ids"], [111, 222])

    def test_patch_updates_allowed_fields(self):
        from steam.models import LeagueSyncState

        LeagueSyncState.objects.create(league_id=12345)
        resp = self.client.patch(
            self.url,
            {
                "is_syncing": True,
                "last_match_id": 77777,
                "failed_match_ids": [333],
            },
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        state = LeagueSyncState.objects.get(league_id=12345)
        self.assertTrue(state.is_syncing)
        self.assertEqual(state.last_match_id, 77777)
        self.assertEqual(state.failed_match_ids, [333])
        self.assertIsNotNone(state.last_sync_at)

    def test_patch_ignores_unknown_fields(self):
        from steam.models import LeagueSyncState

        LeagueSyncState.objects.create(league_id=12345)
        resp = self.client.patch(
            self.url,
            {"league_id": 99999, "is_syncing": True},
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        state = LeagueSyncState.objects.get(league_id=12345)
        # league_id should NOT have changed
        self.assertEqual(state.league_id, 12345)
        self.assertTrue(state.is_syncing)

    def test_rejects_unauthenticated_requests(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)

    def test_rejects_wrong_token(self):
        resp = self.client.get(
            self.url, HTTP_X_INTERNAL_TOKEN="wrong-token"
        )
        self.assertEqual(resp.status_code, 403)


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class StoreMatchEndpointTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/internal/steam/store-match/"

    def _match_payload(self, match_id=7000000001, players=None):
        """Build a minimal match payload matching Steam API structure."""
        if players is None:
            players = [
                {
                    "account_id": 12345,
                    "player_slot": 0,
                    "hero_id": 1,
                    "kills": 10,
                    "deaths": 2,
                    "assists": 15,
                    "gold_per_min": 500,
                    "xp_per_min": 600,
                    "last_hits": 200,
                    "denies": 10,
                    "hero_damage": 25000,
                    "tower_damage": 3000,
                    "hero_healing": 0,
                }
            ]
        return {
            "match_id": match_id,
            "radiant_win": True,
            "duration": 2400,
            "start_time": 1700000000,
            "game_mode": 22,
            "lobby_type": 1,
            "league_id": 12345,
            "players": players,
        }

    def test_creates_match_and_players(self):
        from app.models import CustomUser
        from steam.models import Match, PlayerMatchStats

        # Create a user with matching steamid (32-bit 12345 -> 64-bit)
        steam_id_64 = 12345 + 76561197960265728
        user = CustomUser.objects.create_user(
            username="testplayer", password="pass", steamid=steam_id_64
        )

        resp = self.client.post(
            self.url, self._match_payload(), format="json", **HEADERS
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["match_id"], 7000000001)
        self.assertTrue(data["created"])
        self.assertEqual(data["players_stored"], 1)
        self.assertEqual(data["players_linked"], 1)

        # Verify Match created
        match = Match.objects.get(match_id=7000000001)
        self.assertTrue(match.radiant_win)
        self.assertEqual(match.duration, 2400)

        # Verify PlayerMatchStats created and user linked
        stats = PlayerMatchStats.objects.get(match=match, steam_id=steam_id_64)
        self.assertEqual(stats.kills, 10)
        self.assertEqual(stats.user, user)

    def test_updates_existing_match(self):
        from steam.models import Match, PlayerMatchStats

        # First POST creates
        self.client.post(self.url, self._match_payload(), format="json", **HEADERS)
        self.assertEqual(Match.objects.count(), 1)
        self.assertEqual(PlayerMatchStats.objects.count(), 1)

        # Second POST with same match_id updates (no duplicate)
        payload = self._match_payload()
        payload["duration"] = 3000
        resp = self.client.post(self.url, payload, format="json", **HEADERS)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertFalse(data["created"])

        self.assertEqual(Match.objects.count(), 1)
        self.assertEqual(PlayerMatchStats.objects.count(), 1)
        match = Match.objects.get(match_id=7000000001)
        self.assertEqual(match.duration, 3000)

    def test_skips_players_without_account_id(self):
        from steam.models import PlayerMatchStats

        players = [
            {
                "player_slot": 0,
                "hero_id": 1,
                "kills": 0,
                "deaths": 0,
                "assists": 0,
                "gold_per_min": 0,
                "xp_per_min": 0,
                "last_hits": 0,
                "denies": 0,
                "hero_damage": 0,
                "tower_damage": 0,
                "hero_healing": 0,
            }
        ]
        resp = self.client.post(
            self.url, self._match_payload(players=players), format="json", **HEADERS
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["players_stored"], 0)
        self.assertEqual(PlayerMatchStats.objects.count(), 0)

    def test_rejects_missing_match_id(self):
        payload = self._match_payload()
        del payload["match_id"]
        resp = self.client.post(self.url, payload, format="json", **HEADERS)
        self.assertEqual(resp.status_code, 400)


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class UpdateLeagueStatsEndpointTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            username="statsplayer", steamid=76561198000000001
        )
        # Create a match with player stats linked to user
        match = Match.objects.create(
            match_id=9000000001,
            radiant_win=True,
            duration=2000,
            start_time=1713600000,
            game_mode=2,
            lobby_type=1,
            league_id=17929,
        )
        PlayerMatchStats.objects.create(
            match=match,
            steam_id=76561198000000001,
            user=self.user,
            player_slot=0,
            hero_id=1,
            kills=5,
            deaths=2,
            assists=10,
            gold_per_min=400,
            xp_per_min=500,
            last_hits=150,
            denies=5,
            hero_damage=15000,
            tower_damage=2000,
            hero_healing=0,
        )

    def test_updates_stats(self):
        resp = self.client.post(
            "/api/internal/steam/update-league-stats/17929/",
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["updated_count"], 1)
        # Verify stats were created
        from steam.models import LeaguePlayerStats

        stats = LeaguePlayerStats.objects.get(user=self.user, league_id=17929)
        self.assertEqual(stats.games_played, 1)
        self.assertEqual(stats.wins, 1)

    def test_no_stats_returns_zero(self):
        resp = self.client.post(
            "/api/internal/steam/update-league-stats/99999/",
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["updated_count"], 0)


@override_settings(INTERNAL_SERVICE_TOKEN=TOKEN)
class RecalculateMmrEndpointTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            username="mmrplayer", steamid=76561198000000002
        )

    def test_recalculates_mmr(self):
        resp = self.client.post(
            f"/api/internal/steam/recalculate-mmr/{self.user.pk}/",
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["user_id"], self.user.pk)

    def test_user_not_found(self):
        resp = self.client.post(
            "/api/internal/steam/recalculate-mmr/99999/",
            format="json",
            **HEADERS,
        )
        self.assertEqual(resp.status_code, 404)

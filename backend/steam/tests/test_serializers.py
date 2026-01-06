from django.test import TestCase

from app.models import CustomUser
from steam.constants import LEAGUE_ID
from steam.models import Match, PlayerMatchStats
from steam.serializers import (
    AutoLinkRequestSerializer,
    AutoLinkResultSerializer,
    FindMatchesByPlayersSerializer,
    MatchDetailSerializer,
    PlayerMatchStatsSerializer,
    RelinkUsersSerializer,
    RetryFailedRequestSerializer,
    SyncLeagueRequestSerializer,
    SyncResultSerializer,
    SyncStatusSerializer,
)


class PlayerMatchStatsSerializerTest(TestCase):
    def test_serializes_player_with_username(self):
        user = CustomUser.objects.create(username="TestPlayer")
        match = Match.objects.create(
            match_id=12345,
            radiant_win=True,
            duration=1800,
            start_time=1704067200,
            game_mode=22,
            lobby_type=7,
        )
        stats = PlayerMatchStats.objects.create(
            match=match,
            steam_id=76561198000000001,
            user=user,
            player_slot=0,
            hero_id=1,
            kills=10,
            deaths=2,
            assists=15,
            gold_per_min=600,
            xp_per_min=700,
            last_hits=200,
            denies=10,
            hero_damage=25000,
            tower_damage=3000,
            hero_healing=500,
        )
        serializer = PlayerMatchStatsSerializer(stats)
        data = serializer.data
        self.assertEqual(data["username"], "TestPlayer")
        self.assertEqual(data["hero_id"], 1)
        self.assertEqual(data["kills"], 10)


class MatchDetailSerializerTest(TestCase):
    def test_serializes_match_with_players(self):
        match = Match.objects.create(
            match_id=12345,
            radiant_win=True,
            duration=1800,
            start_time=1704067200,
            game_mode=22,
            lobby_type=7,
        )
        PlayerMatchStats.objects.create(
            match=match,
            steam_id=76561198000000001,
            player_slot=0,
            hero_id=1,
            kills=10,
            deaths=2,
            assists=15,
            gold_per_min=600,
            xp_per_min=700,
            last_hits=200,
            denies=10,
            hero_damage=25000,
            tower_damage=3000,
            hero_healing=500,
        )
        serializer = MatchDetailSerializer(match)
        data = serializer.data
        self.assertEqual(data["match_id"], 12345)
        self.assertTrue(data["radiant_win"])
        self.assertEqual(len(data["players"]), 1)


class SyncLeagueRequestSerializerTest(TestCase):
    def test_valid_with_defaults(self):
        """Test serializer with no data uses defaults."""
        serializer = SyncLeagueRequestSerializer(data={})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["league_id"], LEAGUE_ID)
        self.assertFalse(serializer.validated_data["full_sync"])

    def test_valid_with_custom_values(self):
        """Test serializer with custom values."""
        serializer = SyncLeagueRequestSerializer(
            data={"league_id": 12345, "full_sync": True}
        )
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["league_id"], 12345)
        self.assertTrue(serializer.validated_data["full_sync"])


class FindMatchesByPlayersSerializerTest(TestCase):
    def test_valid_with_steam_ids(self):
        """Test serializer with valid steam IDs."""
        serializer = FindMatchesByPlayersSerializer(
            data={"steam_ids": [76561198000000001, 76561198000000002]}
        )
        self.assertTrue(serializer.is_valid())
        self.assertEqual(len(serializer.validated_data["steam_ids"]), 2)
        self.assertTrue(serializer.validated_data["require_all"])

    def test_invalid_empty_steam_ids(self):
        """Test serializer requires at least one steam ID."""
        serializer = FindMatchesByPlayersSerializer(data={"steam_ids": []})
        self.assertFalse(serializer.is_valid())
        self.assertIn("steam_ids", serializer.errors)

    def test_valid_with_optional_fields(self):
        """Test serializer with optional fields."""
        serializer = FindMatchesByPlayersSerializer(
            data={
                "steam_ids": [76561198000000001],
                "require_all": False,
                "league_id": 17929,
            }
        )
        self.assertTrue(serializer.is_valid())
        self.assertFalse(serializer.validated_data["require_all"])
        self.assertEqual(serializer.validated_data["league_id"], 17929)


class RelinkUsersSerializerTest(TestCase):
    def test_valid_with_empty_list(self):
        """Test serializer with empty match_ids (relink all)."""
        serializer = RelinkUsersSerializer(data={})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["match_ids"], [])

    def test_valid_with_match_ids(self):
        """Test serializer with specific match IDs."""
        serializer = RelinkUsersSerializer(data={"match_ids": [123, 456, 789]})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(len(serializer.validated_data["match_ids"]), 3)


class AutoLinkRequestSerializerTest(TestCase):
    def test_valid_with_tournament_id(self):
        """Test serializer with tournament ID."""
        serializer = AutoLinkRequestSerializer(data={"tournament_id": 1})
        self.assertTrue(serializer.is_valid())

    def test_invalid_without_tournament_id(self):
        """Test serializer requires tournament ID."""
        serializer = AutoLinkRequestSerializer(data={})
        self.assertFalse(serializer.is_valid())
        self.assertIn("tournament_id", serializer.errors)


class RetryFailedRequestSerializerTest(TestCase):
    def test_valid_with_defaults(self):
        """Test serializer with no data uses defaults."""
        serializer = RetryFailedRequestSerializer(data={})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["league_id"], LEAGUE_ID)

    def test_valid_with_custom_league_id(self):
        """Test serializer with custom league ID."""
        serializer = RetryFailedRequestSerializer(data={"league_id": 99999})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["league_id"], 99999)


class ResponseSerializersTest(TestCase):
    def test_sync_result_serializer(self):
        """Test SyncResultSerializer."""
        data = {"synced_count": 10, "failed_count": 2, "new_last_match_id": 888001}
        serializer = SyncResultSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_sync_result_serializer_with_null_match_id(self):
        """Test SyncResultSerializer with null last match ID."""
        data = {"synced_count": 0, "failed_count": 0, "new_last_match_id": None}
        serializer = SyncResultSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_auto_link_result_serializer(self):
        """Test AutoLinkResultSerializer."""
        data = {"auto_linked_count": 5, "suggestions_created_count": 3}
        serializer = AutoLinkResultSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_sync_status_serializer(self):
        """Test SyncStatusSerializer."""
        data = {
            "league_id": 17929,
            "last_sync_at": None,
            "last_match_id": None,
            "failed_match_count": 0,
            "is_syncing": False,
        }
        serializer = SyncStatusSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_sync_status_serializer_with_values(self):
        """Test SyncStatusSerializer with actual values."""
        data = {
            "league_id": 17929,
            "last_sync_at": "2024-01-15T10:30:00Z",
            "last_match_id": 888001,
            "failed_match_count": 5,
            "is_syncing": True,
        }
        serializer = SyncStatusSerializer(data=data)
        self.assertTrue(serializer.is_valid())

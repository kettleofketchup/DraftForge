from django.test import TestCase

from app.models import CustomUser, Game, Team, Tournament
from steam.models import GameMatchSuggestion, LeagueSyncState, Match, PlayerMatchStats


class PlayerMatchStatsUserLinkTest(TestCase):
    def setUp(self):
        self.match = Match.objects.create(
            match_id=7000000001,
            radiant_win=True,
            duration=2400,
            start_time=1704067200,
            game_mode=22,
            lobby_type=1,
        )

    def test_player_stats_without_user(self):
        stats = PlayerMatchStats.objects.create(
            match=self.match,
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
            tower_damage=5000,
            hero_healing=0,
        )
        self.assertIsNone(stats.user)

    def test_player_stats_with_user(self):
        user = CustomUser.objects.create_user(
            username="testplayer",
            password="testpass123",
            steamid=76561198000000001,
        )
        stats = PlayerMatchStats.objects.create(
            match=self.match,
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
            tower_damage=5000,
            hero_healing=0,
            user=user,
        )
        self.assertEqual(stats.user, user)
        self.assertEqual(stats.user.steamid, stats.steam_id)


class LeagueSyncStateModelTest(TestCase):
    def test_create_sync_state(self):
        state = LeagueSyncState.objects.create(
            league_id=17929,
            last_match_id=123456789,
            is_syncing=False,
        )
        self.assertEqual(state.league_id, 17929)
        self.assertEqual(state.last_match_id, 123456789)
        self.assertEqual(state.failed_match_ids, [])
        self.assertFalse(state.is_syncing)
        self.assertIsNone(state.last_sync_at)

    def test_unique_league_id(self):
        LeagueSyncState.objects.create(league_id=17929)
        with self.assertRaises(Exception):
            LeagueSyncState.objects.create(league_id=17929)


class MatchLeagueIdTest(TestCase):
    def test_match_with_league_id(self):
        match = Match.objects.create(
            match_id=7000000002,
            radiant_win=True,
            duration=2400,
            start_time=1704067200,
            game_mode=22,
            lobby_type=1,
            league_id=17929,
        )
        self.assertEqual(match.league_id, 17929)

    def test_match_without_league_id(self):
        match = Match.objects.create(
            match_id=7000000003,
            radiant_win=False,
            duration=1800,
            start_time=1704067200,
            game_mode=22,
            lobby_type=1,
        )
        self.assertIsNone(match.league_id)

    def test_filter_by_league(self):
        Match.objects.create(
            match_id=7000000004,
            radiant_win=True,
            duration=2400,
            start_time=1704067200,
            game_mode=22,
            lobby_type=1,
            league_id=17929,
        )
        Match.objects.create(
            match_id=7000000005,
            radiant_win=True,
            duration=2400,
            start_time=1704067200,
            game_mode=22,
            lobby_type=1,
            league_id=12345,
        )
        Match.objects.create(
            match_id=7000000006,
            radiant_win=True,
            duration=2400,
            start_time=1704067200,
            game_mode=22,
            lobby_type=1,
        )
        league_matches = Match.objects.filter(league_id=17929)
        self.assertEqual(league_matches.count(), 1)


class GameMatchSuggestionModelTest(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played="2026-01-04",
        )
        self.team1 = Team.objects.create(name="Team A", tournament=self.tournament)
        self.team2 = Team.objects.create(name="Team B", tournament=self.tournament)
        self.game = Game.objects.create(
            tournament=self.tournament,
            round=1,
            radiant_team=self.team1,
            dire_team=self.team2,
        )
        self.match = Match.objects.create(
            match_id=7000000010,
            radiant_win=True,
            duration=2400,
            start_time=1704067200,
            game_mode=22,
            lobby_type=1,
            league_id=17929,
        )

    def test_create_suggestion(self):
        suggestion = GameMatchSuggestion.objects.create(
            game=self.game,
            match=self.match,
            tournament=self.tournament,
            confidence_score=0.85,
            player_overlap=8,
        )
        self.assertEqual(suggestion.confidence_score, 0.85)
        self.assertEqual(suggestion.player_overlap, 8)
        self.assertFalse(suggestion.auto_linked)

    def test_unique_game_match_pair(self):
        GameMatchSuggestion.objects.create(
            game=self.game,
            match=self.match,
            tournament=self.tournament,
            confidence_score=0.85,
            player_overlap=8,
        )
        with self.assertRaises(Exception):
            GameMatchSuggestion.objects.create(
                game=self.game,
                match=self.match,
                tournament=self.tournament,
                confidence_score=0.90,
                player_overlap=9,
            )

    def test_suggestions_by_tournament(self):
        GameMatchSuggestion.objects.create(
            game=self.game,
            match=self.match,
            tournament=self.tournament,
            confidence_score=0.85,
            player_overlap=8,
        )
        suggestions = GameMatchSuggestion.objects.filter(tournament=self.tournament)
        self.assertEqual(suggestions.count(), 1)

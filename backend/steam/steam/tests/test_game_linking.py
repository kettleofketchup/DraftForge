from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, Game, Team, Tournament
from steam.functions.game_linking import (
    _get_game_player_steam_ids,
    auto_link_matches_for_tournament,
    check_match_for_games,
    confirm_suggestion,
    dismiss_suggestion,
    get_suggestions_for_game,
    get_suggestions_for_tournament,
)
from steam.models import GameMatchSuggestion, Match, PlayerMatchStats


class CheckMatchForGamesTest(TestCase):
    def setUp(self):
        # Create users with steamids
        self.users = []
        for i in range(10):
            user = CustomUser.objects.create_user(
                username=f"player{i}", steamid=76561198000000001 + i
            )
            self.users.append(user)

        # Create tournament with date
        today = date.today()
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played=today
        )

        # Create teams
        self.team1 = Team.objects.create(
            name="Team Radiant", tournament=self.tournament
        )
        self.team1.members.add(*self.users[:5])

        self.team2 = Team.objects.create(name="Team Dire", tournament=self.tournament)
        self.team2.members.add(*self.users[5:])

        # Create game (unlinked)
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
            round=1,
        )

        # Create match with all 10 players
        self.match = Match.objects.create(
            match_id=888001,
            radiant_win=True,
            duration=2400,
            start_time=int(timezone.now().timestamp()),
            game_mode=22,
            lobby_type=1,
            league_id=17929,
        )
        for i, user in enumerate(self.users):
            PlayerMatchStats.objects.create(
                match=self.match,
                steam_id=user.steamid,
                hero_id=i + 1,
                kills=5,
                deaths=2,
                assists=10,
                gold_per_min=500,
                xp_per_min=600,
                last_hits=200,
                denies=20,
                hero_damage=15000,
                tower_damage=3000,
                hero_healing=1000,
                player_slot=i,
            )

    def test_check_match_auto_links_perfect_match(self):
        """Test auto-linking when all 10 players match."""
        check_match_for_games(self.match)

        self.game.refresh_from_db()
        self.assertEqual(self.game.gameid, 888001)

        suggestion = GameMatchSuggestion.objects.get(game=self.game, match=self.match)
        self.assertTrue(suggestion.auto_linked)
        self.assertEqual(suggestion.confidence_score, 1.0)
        self.assertEqual(suggestion.player_overlap, 10)

    def test_check_match_creates_suggestion_for_partial(self):
        """Test creating suggestion for partial player overlap."""
        # Remove some players from match (keep only first 5)
        PlayerMatchStats.objects.filter(
            match=self.match, steam_id__in=[user.steamid for user in self.users[5:]]
        ).delete()

        check_match_for_games(self.match)

        self.game.refresh_from_db()
        self.assertIsNone(self.game.gameid)  # Not auto-linked

        suggestion = GameMatchSuggestion.objects.get(game=self.game, match=self.match)
        self.assertFalse(suggestion.auto_linked)
        self.assertEqual(suggestion.player_overlap, 5)
        self.assertEqual(suggestion.confidence_score, 0.5)

    def test_check_match_ignores_outside_tournament_dates(self):
        """Test match outside tournament dates is ignored."""
        # Set match time to before tournament (30 days ago)
        self.match.start_time = int((timezone.now() - timedelta(days=30)).timestamp())
        self.match.save()

        check_match_for_games(self.match)

        self.assertEqual(GameMatchSuggestion.objects.count(), 0)

    def test_check_match_ignores_already_linked_games(self):
        """Test already linked games are skipped."""
        self.game.gameid = 777001
        self.game.save()

        check_match_for_games(self.match)

        # No new suggestion created
        self.assertEqual(
            GameMatchSuggestion.objects.filter(match=self.match).count(), 0
        )

    def test_check_match_no_overlap_no_suggestion(self):
        """Test no suggestion created when no player overlap."""
        # Replace all players with different steam_ids
        PlayerMatchStats.objects.filter(match=self.match).delete()
        for i in range(10):
            PlayerMatchStats.objects.create(
                match=self.match,
                steam_id=99999999900 + i,  # Different steam_ids
                hero_id=i + 1,
                kills=5,
                deaths=2,
                assists=10,
                gold_per_min=500,
                xp_per_min=600,
                last_hits=200,
                denies=20,
                hero_damage=15000,
                tower_damage=3000,
                hero_healing=1000,
                player_slot=i,
            )

        check_match_for_games(self.match)

        self.assertEqual(GameMatchSuggestion.objects.count(), 0)

    def test_check_match_skips_existing_suggestion(self):
        """Test that existing suggestions are not duplicated."""
        # Create existing suggestion
        GameMatchSuggestion.objects.create(
            game=self.game,
            match=self.match,
            tournament=self.tournament,
            confidence_score=0.5,
            player_overlap=5,
        )

        check_match_for_games(self.match)

        # Should still be only 1 suggestion
        self.assertEqual(
            GameMatchSuggestion.objects.filter(
                game=self.game, match=self.match
            ).count(),
            1,
        )


class GetGamePlayerSteamIdsTest(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played=date.today()
        )

        # Create users with steamids
        self.users = []
        for i in range(10):
            user = CustomUser.objects.create_user(
                username=f"player{i}", steamid=76561198000000001 + i
            )
            self.users.append(user)

        self.team1 = Team.objects.create(
            name="Team Radiant", tournament=self.tournament
        )
        self.team1.members.add(*self.users[:5])

        self.team2 = Team.objects.create(name="Team Dire", tournament=self.tournament)
        self.team2.members.add(*self.users[5:])

        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
            round=1,
        )

    def test_get_game_player_steam_ids_returns_all_players(self):
        """Test that all team members' steam_ids are returned."""
        steam_ids = _get_game_player_steam_ids(self.game)

        self.assertEqual(len(steam_ids), 10)
        for user in self.users:
            self.assertIn(user.steamid, steam_ids)

    def test_get_game_player_steam_ids_excludes_null_steamids(self):
        """Test that users without steamids are excluded."""
        # Create user without steamid and add to team
        user_no_steam = CustomUser.objects.create_user(
            username="no_steam_user", steamid=None
        )
        self.team1.members.add(user_no_steam)

        steam_ids = _get_game_player_steam_ids(self.game)

        # Should still be 10 (only users with steamids)
        self.assertEqual(len(steam_ids), 10)

    def test_get_game_player_steam_ids_handles_null_teams(self):
        """Test handling of games with null teams."""
        game_no_teams = Game.objects.create(
            tournament=self.tournament, radiant_team=None, dire_team=None, round=1
        )

        steam_ids = _get_game_player_steam_ids(game_no_teams)

        self.assertEqual(len(steam_ids), 0)


class GetSuggestionsTest(TestCase):
    def setUp(self):
        # Create minimal tournament structure
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played=date.today()
        )

        self.team1 = Team.objects.create(name="Team 1", tournament=self.tournament)
        self.team2 = Team.objects.create(name="Team 2", tournament=self.tournament)

        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
            round=1,
        )

        self.match1 = Match.objects.create(
            match_id=777001,
            radiant_win=True,
            duration=2400,
            start_time=1700000000,
            game_mode=22,
            lobby_type=1,
            league_id=17929,
        )
        self.match2 = Match.objects.create(
            match_id=777002,
            radiant_win=False,
            duration=2500,
            start_time=1700001000,
            game_mode=22,
            lobby_type=1,
            league_id=17929,
        )

        # Create suggestions with different confidence
        self.suggestion1 = GameMatchSuggestion.objects.create(
            game=self.game,
            match=self.match1,
            tournament=self.tournament,
            confidence_score=0.8,
            player_overlap=8,
        )
        self.suggestion2 = GameMatchSuggestion.objects.create(
            game=self.game,
            match=self.match2,
            tournament=self.tournament,
            confidence_score=0.5,
            player_overlap=5,
        )

    def test_get_suggestions_for_tournament(self):
        """Test retrieving suggestions by tournament."""
        suggestions = get_suggestions_for_tournament(self.tournament.id)

        self.assertEqual(suggestions.count(), 2)
        # Should be ordered by confidence descending
        self.assertEqual(suggestions[0].confidence_score, 0.8)
        self.assertEqual(suggestions[1].confidence_score, 0.5)

    def test_get_suggestions_for_tournament_empty(self):
        """Test retrieving suggestions for tournament with none."""
        other_tournament = Tournament.objects.create(
            name="Other Tournament", date_played=date.today()
        )

        suggestions = get_suggestions_for_tournament(other_tournament.id)

        self.assertEqual(suggestions.count(), 0)

    def test_get_suggestions_for_game(self):
        """Test retrieving suggestions by game."""
        suggestions = get_suggestions_for_game(self.game.id)

        self.assertEqual(suggestions.count(), 2)
        self.assertEqual(suggestions[0].match.match_id, 777001)

    def test_get_suggestions_for_game_empty(self):
        """Test retrieving suggestions for game with none."""
        other_game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
            round=2,
        )

        suggestions = get_suggestions_for_game(other_game.id)

        self.assertEqual(suggestions.count(), 0)


class ConfirmDismissSuggestionTest(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(
            name="Test Tournament", date_played=date.today()
        )

        self.team1 = Team.objects.create(name="Team 1", tournament=self.tournament)
        self.team2 = Team.objects.create(name="Team 2", tournament=self.tournament)

        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
            round=1,
        )
        self.match = Match.objects.create(
            match_id=666001,
            radiant_win=True,
            duration=2400,
            start_time=1700000000,
            game_mode=22,
            lobby_type=1,
            league_id=17929,
        )
        self.suggestion = GameMatchSuggestion.objects.create(
            game=self.game,
            match=self.match,
            tournament=self.tournament,
            confidence_score=0.7,
            player_overlap=7,
        )

    def test_confirm_suggestion_links_game(self):
        """Test confirming suggestion links game to match."""
        result = confirm_suggestion(self.suggestion.id)

        self.assertTrue(result)

        self.game.refresh_from_db()
        self.assertEqual(self.game.gameid, 666001)

        self.suggestion.refresh_from_db()
        self.assertTrue(self.suggestion.auto_linked)

    def test_confirm_suggestion_not_found(self):
        """Test confirming non-existent suggestion."""
        result = confirm_suggestion(99999)
        self.assertFalse(result)

    def test_confirm_suggestion_already_linked(self):
        """Test confirming suggestion for already linked game."""
        self.game.gameid = 555001
        self.game.save()

        result = confirm_suggestion(self.suggestion.id)
        self.assertFalse(result)

    def test_dismiss_suggestion(self):
        """Test dismissing suggestion deletes it."""
        result = dismiss_suggestion(self.suggestion.id)

        self.assertTrue(result)
        self.assertFalse(
            GameMatchSuggestion.objects.filter(id=self.suggestion.id).exists()
        )

    def test_dismiss_suggestion_not_found(self):
        """Test dismissing non-existent suggestion."""
        result = dismiss_suggestion(99999)
        self.assertFalse(result)


class AutoLinkMatchesForTournamentTest(TestCase):
    def setUp(self):
        # Create users with steamids
        self.users = []
        for i in range(10):
            user = CustomUser.objects.create_user(
                username=f"auto_player{i}",
                steamid=76561198000000101 + i,
            )
            self.users.append(user)

        # Create tournament with date
        today = date.today()
        self.tournament = Tournament.objects.create(
            name="Auto Link Tournament", date_played=today
        )

        # Create teams
        self.team1 = Team.objects.create(name="Auto Team 1", tournament=self.tournament)
        self.team1.members.add(*self.users[:5])

        self.team2 = Team.objects.create(name="Auto Team 2", tournament=self.tournament)
        self.team2.members.add(*self.users[5:])

        # Create multiple unlinked games
        self.game1 = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
            round=1,
        )
        self.game2 = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
            round=2,
        )

        # Create match with all 10 players (for game1)
        self.match1 = Match.objects.create(
            match_id=999101,
            radiant_win=True,
            duration=2400,
            start_time=int(timezone.now().timestamp()),
            game_mode=22,
            lobby_type=1,
            league_id=17929,
        )
        for i, user in enumerate(self.users):
            PlayerMatchStats.objects.create(
                match=self.match1,
                steam_id=user.steamid,
                hero_id=i + 1,
                kills=5,
                deaths=2,
                assists=10,
                gold_per_min=500,
                xp_per_min=600,
                last_hits=200,
                denies=20,
                hero_damage=15000,
                tower_damage=3000,
                hero_healing=1000,
                player_slot=i,
            )

        # Create match with partial overlap (for game2 suggestions)
        self.match2 = Match.objects.create(
            match_id=999102,
            radiant_win=False,
            duration=2500,
            start_time=int(timezone.now().timestamp()),
            game_mode=22,
            lobby_type=1,
            league_id=17929,
        )
        # Only add first 5 players
        for i, user in enumerate(self.users[:5]):
            PlayerMatchStats.objects.create(
                match=self.match2,
                steam_id=user.steamid,
                hero_id=i + 1,
                kills=3,
                deaths=4,
                assists=8,
                gold_per_min=400,
                xp_per_min=500,
                last_hits=150,
                denies=15,
                hero_damage=12000,
                tower_damage=2000,
                hero_healing=800,
                player_slot=i,
            )

    def test_auto_link_perfect_match(self):
        """Test auto-linking when all 10 players match."""
        # Delete game2 so we only have one unlinked game
        self.game2.delete()

        result = auto_link_matches_for_tournament(self.tournament.id)

        self.assertEqual(result["auto_linked_count"], 1)

        self.game1.refresh_from_db()
        self.assertEqual(self.game1.gameid, 999101)

    def test_creates_suggestions_for_partial_match(self):
        """Test creating suggestions for partial player overlap."""
        # Delete match1 (the perfect match) so only partial matches exist
        self.match1.delete()

        result = auto_link_matches_for_tournament(self.tournament.id)

        # Should have suggestions for partial matches (match2 has 5/10 players)
        self.assertGreater(result["suggestions_created_count"], 0)

        # Verify that a suggestion was created with 50% confidence
        suggestion = GameMatchSuggestion.objects.filter(
            game=self.game1, match=self.match2
        ).first()
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.confidence_score, 0.5)
        self.assertFalse(suggestion.auto_linked)

    def test_tournament_not_found(self):
        """Test with non-existent tournament."""
        result = auto_link_matches_for_tournament(99999)

        self.assertEqual(result["auto_linked_count"], 0)
        self.assertEqual(result["suggestions_created_count"], 0)

    def test_skips_already_linked_games(self):
        """Test that already linked games are skipped."""
        self.game1.gameid = 888001
        self.game1.save()

        result = auto_link_matches_for_tournament(self.tournament.id)

        # game1 should not be re-linked
        self.game1.refresh_from_db()
        self.assertEqual(self.game1.gameid, 888001)

    def test_skips_existing_suggestions(self):
        """Test that existing suggestions are not duplicated."""
        # Create existing suggestion
        GameMatchSuggestion.objects.create(
            game=self.game2,
            match=self.match2,
            tournament=self.tournament,
            confidence_score=0.5,
            player_overlap=5,
        )

        result = auto_link_matches_for_tournament(self.tournament.id)

        # Should not create duplicate
        self.assertEqual(
            GameMatchSuggestion.objects.filter(
                game=self.game2, match=self.match2
            ).count(),
            1,
        )

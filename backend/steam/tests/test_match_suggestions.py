from datetime import date

from django.test import TestCase

from app.models import CustomUser, Game, League, Team, Tournament
from steam.models import Match, PlayerMatchStats, SuggestionTier
from steam.services.match_suggestions import (
    calculate_suggestion_tier,
    get_match_suggestions_for_game,
    get_team_steam_ids,
)


class CalculateSuggestionTierTest(TestCase):
    def setUp(self):
        # Create tournament
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date(2024, 1, 15),
        )

        # Create users with steam IDs
        self.users = []
        for i in range(10):
            user = CustomUser.objects.create(
                username=f"player{i}",
                discordId=str(100000000000000000 + i),
                steamid=76561197960265728 + i,
            )
            self.users.append(user)

        # Create two teams
        self.team1 = Team.objects.create(
            tournament=self.tournament,
            name="Team 1",
            captain=self.users[0],
        )
        self.team1.members.set(self.users[0:5])

        self.team2 = Team.objects.create(
            tournament=self.tournament,
            name="Team 2",
            captain=self.users[5],
        )
        self.team2.members.set(self.users[5:10])

        # Create a game
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
        )

        # Create a match
        self.match = Match.objects.create(
            match_id=9000000001,
            radiant_win=True,
            duration=2400,
            start_time=1704567890,
            game_mode=22,
            lobby_type=1,
            league_id=17929,
        )

    def _get_tier_params(self):
        """Helper to get pre-computed parameters for calculate_suggestion_tier."""
        radiant_steam_ids = get_team_steam_ids(self.team1)
        dire_steam_ids = get_team_steam_ids(self.team2)
        all_team_steam_ids = radiant_steam_ids | dire_steam_ids
        radiant_captain_id = (
            self.team1.captain.steamid
            if self.team1.captain and self.team1.captain.steamid
            else None
        )
        dire_captain_id = (
            self.team2.captain.steamid
            if self.team2.captain and self.team2.captain.steamid
            else None
        )
        return all_team_steam_ids, radiant_captain_id, dire_captain_id

    def test_all_players_tier(self):
        """When all 10 players match, tier is ALL_PLAYERS."""
        # Add all 10 players to match
        for i, user in enumerate(self.users):
            PlayerMatchStats.objects.create(
                match=self.match,
                steam_id=user.steamid,
                user=user,
                player_slot=i,
                hero_id=1,
                kills=0,
                deaths=0,
                assists=0,
                gold_per_min=0,
                xp_per_min=0,
                last_hits=0,
                denies=0,
                hero_damage=0,
                tower_damage=0,
                hero_healing=0,
            )

        all_team_steam_ids, radiant_captain_id, dire_captain_id = (
            self._get_tier_params()
        )
        tier = calculate_suggestion_tier(
            self.match, all_team_steam_ids, radiant_captain_id, dire_captain_id
        )
        self.assertEqual(tier, SuggestionTier.ALL_PLAYERS)

    def test_captains_plus_tier(self):
        """When both captains + some players match, tier is CAPTAINS_PLUS."""
        # Add both captains + 2 more players (4 total)
        for user in [self.users[0], self.users[5], self.users[1], self.users[6]]:
            PlayerMatchStats.objects.create(
                match=self.match,
                steam_id=user.steamid,
                user=user,
                player_slot=0,
                hero_id=1,
                kills=0,
                deaths=0,
                assists=0,
                gold_per_min=0,
                xp_per_min=0,
                last_hits=0,
                denies=0,
                hero_damage=0,
                tower_damage=0,
                hero_healing=0,
            )

        all_team_steam_ids, radiant_captain_id, dire_captain_id = (
            self._get_tier_params()
        )
        tier = calculate_suggestion_tier(
            self.match, all_team_steam_ids, radiant_captain_id, dire_captain_id
        )
        self.assertEqual(tier, SuggestionTier.CAPTAINS_PLUS)

    def test_captains_only_tier(self):
        """When only both captains match, tier is CAPTAINS_ONLY."""
        # Add only both captains
        for user in [self.users[0], self.users[5]]:
            PlayerMatchStats.objects.create(
                match=self.match,
                steam_id=user.steamid,
                user=user,
                player_slot=0,
                hero_id=1,
                kills=0,
                deaths=0,
                assists=0,
                gold_per_min=0,
                xp_per_min=0,
                last_hits=0,
                denies=0,
                hero_damage=0,
                tower_damage=0,
                hero_healing=0,
            )

        all_team_steam_ids, radiant_captain_id, dire_captain_id = (
            self._get_tier_params()
        )
        tier = calculate_suggestion_tier(
            self.match, all_team_steam_ids, radiant_captain_id, dire_captain_id
        )
        self.assertEqual(tier, SuggestionTier.CAPTAINS_ONLY)

    def test_partial_tier(self):
        """When captains don't both match, tier is PARTIAL."""
        # Add only one captain + some other players
        for user in [self.users[0], self.users[1], self.users[2]]:
            PlayerMatchStats.objects.create(
                match=self.match,
                steam_id=user.steamid,
                user=user,
                player_slot=0,
                hero_id=1,
                kills=0,
                deaths=0,
                assists=0,
                gold_per_min=0,
                xp_per_min=0,
                last_hits=0,
                denies=0,
                hero_damage=0,
                tower_damage=0,
                hero_healing=0,
            )

        all_team_steam_ids, radiant_captain_id, dire_captain_id = (
            self._get_tier_params()
        )
        tier = calculate_suggestion_tier(
            self.match, all_team_steam_ids, radiant_captain_id, dire_captain_id
        )
        self.assertEqual(tier, SuggestionTier.PARTIAL)


class TournamentLinkedSteamLeagueIdTest(TestCase):
    """Tournament.linked_steam_league_id resolves through the League FK."""

    def test_returns_league_steam_id(self):
        league = League.objects.create(name="L", steam_league_id=19571)
        tournament = Tournament.objects.create(
            name="T",
            date_played=date(2024, 1, 15),
            league=league,
        )
        self.assertEqual(tournament.linked_steam_league_id, 19571)

    def test_legacy_tournament_field_is_ignored(self):
        # Tournament.steam_league_id is the legacy field slated for removal;
        # the property reads only from the parent League.
        league = League.objects.create(name="L", steam_league_id=19571)
        tournament = Tournament.objects.create(
            name="T",
            date_played=date(2024, 1, 15),
            league=league,
            steam_league_id=99999,
        )
        self.assertEqual(tournament.linked_steam_league_id, 19571)

    def test_returns_none_when_league_steam_id_unset(self):
        league = League.objects.create(name="L", steam_league_id=None)
        tournament = Tournament.objects.create(
            name="T",
            date_played=date(2024, 1, 15),
            league=league,
        )
        self.assertIsNone(tournament.linked_steam_league_id)

    def test_returns_none_when_no_parent_league(self):
        tournament = Tournament.objects.create(
            name="T",
            date_played=date(2024, 1, 15),
        )
        self.assertIsNone(tournament.linked_steam_league_id)


class GetMatchSuggestionsFallbackTest(TestCase):
    """get_match_suggestions_for_game finds matches via League.steam_league_id
    even when Tournament.steam_league_id is null — regression for the case
    where a tournament inherits its league from the parent."""

    def setUp(self):
        self.league = League.objects.create(name="DTX", steam_league_id=19571)
        # Tournament with NO own steam_league_id — should fall back to the league
        self.tournament = Tournament.objects.create(
            name="DTX Turbo Tourney",
            date_played=date(2024, 1, 15),
            league=self.league,
            steam_league_id=None,
        )
        self.radiant_captain = CustomUser.objects.create(
            username="rcap",
            discordId="100000000000000001",
            steamid=76561198000000001,
        )
        self.dire_captain = CustomUser.objects.create(
            username="dcap",
            discordId="100000000000000002",
            steamid=76561198000000002,
        )
        self.team1 = Team.objects.create(
            tournament=self.tournament, name="R", captain=self.radiant_captain
        )
        self.team1.members.set([self.radiant_captain])
        self.team2 = Team.objects.create(
            tournament=self.tournament, name="D", captain=self.dire_captain
        )
        self.team2.members.set([self.dire_captain])
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
        )

    def _create_match(self, match_id, league_id):
        return Match.objects.create(
            match_id=match_id,
            radiant_win=True,
            duration=2000,
            start_time=1704567890,
            game_mode=22,
            lobby_type=1,
            league_id=league_id,
        )

    def test_finds_matches_via_parent_league_steam_id(self):
        self._create_match(match_id=1, league_id=19571)  # matches via fallback
        self._create_match(match_id=2, league_id=12345)  # different league, skipped

        suggestions = get_match_suggestions_for_game(self.game)

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["match_id"], 1)

    def test_returns_empty_when_neither_field_set(self):
        self.tournament.league = None
        self.tournament.save()
        self._create_match(match_id=1, league_id=19571)

        suggestions = get_match_suggestions_for_game(self.game)
        self.assertEqual(suggestions, [])

    def test_legacy_tournament_field_does_not_override_league(self):
        # The legacy Tournament.steam_league_id field is ignored — only the
        # parent League's id matters.
        self.tournament.steam_league_id = 88888
        self.tournament.save()
        self._create_match(match_id=1, league_id=19571)  # via league — used
        self._create_match(match_id=2, league_id=88888)  # legacy field — ignored

        suggestions = get_match_suggestions_for_game(self.game)
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["match_id"], 1)

    def test_query_count_is_bounded_by_match_count(self):
        """Regression guard for the prefetch — query count must NOT scale
        with match count. Before the prefetch fix, every helper issued a
        fresh `PlayerMatchStats.objects.filter(match=match)` query per
        match (~5 queries × N matches). The bug is back if this test
        fails on a higher fanout.
        """
        # Create 10 matches with 10 players each — 100 PlayerMatchStats rows
        for match_id in range(1, 11):
            match = self._create_match(match_id=match_id, league_id=19571)
            for slot in range(10):
                PlayerMatchStats.objects.create(
                    match=match,
                    steam_id=76561198000000100 + slot,
                    player_slot=slot,
                    hero_id=1,
                    kills=0, deaths=0, assists=0,
                    gold_per_min=0, xp_per_min=0,
                    last_hits=0, denies=0,
                    hero_damage=0, tower_damage=0, hero_healing=0,
                )

        # Bypass cacheops so we measure DB hits, not Redis hits.
        from django.db import connection, reset_queries
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            suggestions = get_match_suggestions_for_game(self.game)

        # 10 matches × 5 helpers without prefetch ≈ 50+ queries. With prefetch,
        # it's a small constant (game/team/captain lookups + matches + players).
        # 20 is a generous ceiling that catches the regression while tolerating
        # incidental query churn.
        self.assertEqual(len(suggestions), 10)
        self.assertLess(
            len(ctx.captured_queries),
            20,
            f"Too many queries ({len(ctx.captured_queries)}); prefetch likely bypassed.",
        )

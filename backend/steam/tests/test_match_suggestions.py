from datetime import date

from django.test import TestCase

from app.models import CustomUser, Game, Team, Tournament
from steam.models import Match, PlayerMatchStats, SuggestionTier
from steam.services.match_suggestions import (
    calculate_suggestion_tier,
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

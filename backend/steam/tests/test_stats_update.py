from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from app.models import CustomUser
from steam.functions.mmr_calculation import calculate_mmr_adjustment
from steam.functions.stats_update import (
    player_won,
    update_all_league_stats_for_league,
    update_player_league_stats,
)
from steam.models import LeaguePlayerStats, Match, PlayerMatchStats


class TestStatsUpdate(TestCase):
    def setUp(self) -> None:
        # mmr lives on OrgUser and positions on DotaUserProfile;
        # update_player_league_stats reads neither.
        self.user = CustomUser.objects.create_user(
            username="testplayer",
            password="testpass",
            steamid=76561198000000001,
        )
        self.league_id = 12345

    def test_update_player_league_stats_creates_new(self):
        """Should create LeaguePlayerStats if doesn't exist."""
        match = Match.objects.create(
            match_id=1001,
            radiant_win=True,
            duration=2400,
            start_time=1704067200,
            game_mode=22,
            lobby_type=1,
            league_id=self.league_id,
        )
        PlayerMatchStats.objects.create(
            match=match,
            steam_id=76561198000000001,
            user=self.user,
            player_slot=0,  # Radiant
            hero_id=1,
            kills=10,
            deaths=3,
            assists=15,
            gold_per_min=550,
            xp_per_min=600,
            last_hits=200,
            denies=10,
            hero_damage=25000,
            tower_damage=3000,
            hero_healing=0,
        )

        update_player_league_stats(self.user, self.league_id)

        stats = LeaguePlayerStats.objects.get(user=self.user, league_id=self.league_id)
        self.assertEqual(stats.games_played, 1)
        self.assertEqual(stats.wins, 1)
        self.assertEqual(stats.losses, 0)
        self.assertEqual(stats.total_kills, 10)
        self.assertEqual(stats.avg_kills, 10.0)

    def test_update_player_league_stats_accumulates(self):
        """Should accumulate stats from multiple matches."""
        for i, (radiant_win, player_slot) in enumerate([(True, 0), (False, 0)]):
            match = Match.objects.create(
                match_id=1001 + i,
                radiant_win=radiant_win,
                duration=2400,
                start_time=1704067200 + i * 3600,
                game_mode=22,
                lobby_type=1,
                league_id=self.league_id,
            )
            PlayerMatchStats.objects.create(
                match=match,
                steam_id=76561198000000001,
                user=self.user,
                player_slot=player_slot,
                hero_id=1,
                kills=10,
                deaths=5,
                assists=10,
                gold_per_min=500,
                xp_per_min=550,
                last_hits=180,
                denies=8,
                hero_damage=20000,
                tower_damage=2000,
                hero_healing=0,
            )

        update_player_league_stats(self.user, self.league_id)

        stats = LeaguePlayerStats.objects.get(user=self.user, league_id=self.league_id)
        self.assertEqual(stats.games_played, 2)
        self.assertEqual(stats.wins, 1)
        self.assertEqual(stats.losses, 1)
        self.assertEqual(stats.win_rate, 0.5)
        self.assertEqual(stats.total_kills, 20)
        self.assertEqual(stats.avg_kills, 10.0)


def _add_matches(
    user: CustomUser,
    league_id: int,
    first_match_id: int,
    results: list[bool],
    kills: int,
    deaths: int,
    assists: int,
    gpm: int,
) -> None:
    for i, won in enumerate(results):
        match = Match.objects.create(
            match_id=first_match_id + i,
            radiant_win=won,
            duration=2400,
            start_time=1704067200 + i * 3600,
            game_mode=22,
            lobby_type=1,
            league_id=league_id,
        )
        PlayerMatchStats.objects.create(
            match=match,
            steam_id=user.steamid,
            user=user,
            player_slot=0,
            hero_id=1,
            kills=kills,
            deaths=deaths,
            assists=assists,
            gold_per_min=gpm,
            xp_per_min=500,
            last_hits=150,
            denies=5,
            hero_damage=15000,
            tower_damage=1000,
            hero_healing=0,
        )


@override_settings(LEAGUE_MMR_MIN_GAMES=5)
class LeagueAdjustmentUsesCurrentAveragesTests(TestCase):
    league_id = 54321

    def _user(self, n: int) -> CustomUser:
        return CustomUser.objects.create_user(
            username=f"adj{n}", password="x", steamid=76561198100000000 + n
        )

    def test_solo_player_is_compared_with_own_current_averages(self) -> None:
        user = self._user(1)
        _add_matches(user, self.league_id, 5000, [True, False] * 3, 10, 2, 10, 700)

        stats = update_player_league_stats(user, self.league_id)

        assert stats is not None
        self.assertEqual(stats.mmr_adjustment, 0)
        stored = LeaguePlayerStats.objects.get(user=user, league_id=self.league_id)
        self.assertEqual(stored.mmr_adjustment, 0)
        self.assertEqual(stored.avg_gpm, 700.0)

    def _run_bulk(self, order: list[int]) -> dict[int, int]:
        LeaguePlayerStats.objects.filter(league_id=self.league_id).delete()
        with patch("steam.functions.stats_update.league_user_ids", return_value=order):
            update_all_league_stats_for_league(self.league_id)
        return dict(
            LeaguePlayerStats.objects.filter(league_id=self.league_id).values_list(
                "user_id", "mmr_adjustment"
            )
        )

    def test_bulk_update_does_not_depend_on_order(self) -> None:
        strong, mid, weak = self._user(1), self._user(2), self._user(3)
        _add_matches(strong, self.league_id, 6000, [True] * 5 + [False], 12, 2, 10, 650)
        _add_matches(mid, self.league_id, 6100, [True, False] * 3, 6, 5, 8, 450)
        _add_matches(weak, self.league_id, 6200, [False] * 5 + [True], 2, 8, 4, 300)
        ids = [strong.pk, mid.pk, weak.pk]

        forward = self._run_bulk(ids)
        backward = self._run_bulk(list(reversed(ids)))

        self.assertEqual(forward, backward)
        for row in LeaguePlayerStats.objects.filter(league_id=self.league_id):
            self.assertEqual(row.mmr_adjustment, calculate_mmr_adjustment(row))


class PlayerWonTests(SimpleTestCase):
    def test_radiant_slot_wins_when_radiant_wins(self) -> None:
        self.assertIs(player_won(0, True), True)
        self.assertIs(player_won(127, True), True)

    def test_radiant_slot_loses_when_dire_wins(self) -> None:
        self.assertIs(player_won(4, False), False)

    def test_dire_slot_wins_when_dire_wins(self) -> None:
        self.assertIs(player_won(128, False), True)
        self.assertIs(player_won(132, False), True)

    def test_dire_slot_loses_when_radiant_wins(self) -> None:
        self.assertIs(player_won(128, True), False)

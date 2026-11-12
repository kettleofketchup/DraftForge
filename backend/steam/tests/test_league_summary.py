from django.conf import settings
from django.test import TestCase, override_settings

from app.models import CustomUser
from steam.functions.league_summary import (
    LeagueSummary,
    compute_league_summary,
    empty_league_summary,
    top_percent,
)
from steam.tests.league_summary_fixtures import make_player, record_game, record_series

LEAGUE = 90001
OTHER_LEAGUE = 90002
T0 = 1_700_000_000


class ComputeLeagueSummaryTests(TestCase):
    def setUp(self) -> None:
        self.next_steamid = 76561198100000000

    def player(self, username: str) -> CustomUser:
        self.next_steamid += 1
        return make_player(username, self.next_steamid)

    def summary(self, min_games: int = 5) -> LeagueSummary:
        return compute_league_summary(LEAGUE, min_games)

    def test_order_ties_broken_by_match_id(self) -> None:
        user = self.player("a")
        record_game(user, league_id=LEAGUE, match_id=11, start_time=T0, won=False)
        record_game(user, league_id=LEAGUE, match_id=10, start_time=T0, won=True)
        self.assertEqual(self.summary()["players"][str(user.pk)]["recent"], ["W", "L"])

    def test_streak_zero_games_absent(self) -> None:
        user = self.player("a")
        other = self.player("b")
        record_series(other, "W", league_id=LEAGUE, first_match_id=100)
        self.assertNotIn(str(user.pk), self.summary()["players"])

    def test_streak_all_wins(self) -> None:
        user = self.player("a")
        record_series(user, "WWWW", league_id=LEAGUE, first_match_id=100)
        self.assertEqual(
            self.summary()["players"][str(user.pk)]["streak"],
            {"result": "W", "count": 4},
        )

    def test_streak_alternating(self) -> None:
        user = self.player("a")
        record_series(user, "WLWL", league_id=LEAGUE, first_match_id=100)
        self.assertEqual(
            self.summary()["players"][str(user.pk)]["streak"],
            {"result": "L", "count": 1},
        )

    def test_streak_trailing_l3(self) -> None:
        user = self.player("a")
        record_series(user, "WWLLL", league_id=LEAGUE, first_match_id=100)
        self.assertEqual(
            self.summary()["players"][str(user.pk)]["streak"],
            {"result": "L", "count": 3},
        )

    def test_recent_capped_at_10_streak_not_capped(self) -> None:
        user = self.player("a")
        record_series(user, "W" * 12, league_id=LEAGUE, first_match_id=100)
        player = self.summary()["players"][str(user.pk)]
        self.assertEqual(len(player["recent"]), 10)
        self.assertEqual(player["streak"], {"result": "W", "count": 12})

    def test_recent_is_last_ten_oldest_first(self) -> None:
        user = self.player("a")
        record_series(user, "LLWWWWWWWWWL", league_id=LEAGUE, first_match_id=100)
        self.assertEqual(
            self.summary()["players"][str(user.pk)]["recent"],
            list("WWWWWWWWWL"),
        )

    def test_counts_and_win_rate(self) -> None:
        user = self.player("a")
        record_series(user, "WWLWWWLLLW", league_id=LEAGUE, first_match_id=100)
        player = self.summary()["players"][str(user.pk)]
        self.assertEqual(player["games"], 10)
        self.assertEqual(player["wins"], 6)
        self.assertEqual(player["losses"], 4)
        self.assertEqual(player["win_rate"], 0.6)

    def test_rank_ties_split_by_games(self) -> None:
        a = self.player("a")
        b = self.player("b")
        record_series(a, "WWWLL", league_id=LEAGUE, first_match_id=100)
        record_series(b, "WWWWWWLLLL", league_id=LEAGUE, first_match_id=200)
        players = self.summary()["players"]
        self.assertEqual(players[str(b.pk)]["rank"], 1)
        self.assertEqual(players[str(a.pk)]["rank"], 2)

    def test_equal_rate_and_games_share_rank(self) -> None:
        a = self.player("a")
        b = self.player("b")
        c = self.player("c")
        record_series(a, "WWWLL", league_id=LEAGUE, first_match_id=100)
        record_series(b, "WWWLL", league_id=LEAGUE, first_match_id=200)
        record_series(c, "WWLLL", league_id=LEAGUE, first_match_id=300)
        summary = self.summary()
        players = summary["players"]
        self.assertEqual(players[str(a.pk)]["rank"], 1)
        self.assertEqual(players[str(b.pk)]["rank"], 1)
        self.assertEqual(players[str(c.pk)]["rank"], 3)
        self.assertEqual(summary["population"], 3)
        self.assertEqual(players[str(c.pk)]["top_percent"], 100)

    def test_top_percent_integer_ceil(self) -> None:
        self.assertEqual(top_percent(12, 84), 15)
        self.assertEqual(top_percent(7, 100), 7)
        self.assertEqual(top_percent(11, 20), 55)
        self.assertEqual(top_percent(7, 50), 14)

    def test_min_games_boundary(self) -> None:
        four = self.player("four")
        five = self.player("five")
        record_series(four, "WWWW", league_id=LEAGUE, first_match_id=100)
        record_series(five, "WWWWW", league_id=LEAGUE, first_match_id=200)
        summary = self.summary()
        unranked = summary["players"][str(four.pk)]
        self.assertIsNone(unranked["rank"])
        self.assertIsNone(unranked["top_percent"])
        self.assertIsNone(unranked["bucket"])
        self.assertEqual(unranked["games"], 4)
        self.assertEqual(summary["players"][str(five.pk)]["rank"], 1)
        self.assertEqual(summary["population"], 1)
        self.assertEqual(summary["min_games"], 5)

        with override_settings(LEAGUE_MMR_MIN_GAMES=3):
            lowered = compute_league_summary(LEAGUE, settings.LEAGUE_MMR_MIN_GAMES)
        self.assertEqual(lowered["min_games"], 3)
        self.assertEqual(lowered["population"], 2)
        self.assertIsNotNone(lowered["players"][str(four.pk)]["rank"])

    def test_bucket_edges(self) -> None:
        zero = self.player("zero")
        half = self.player("half")
        full = self.player("full")
        record_series(zero, "LLLLL", league_id=LEAGUE, first_match_id=100)
        record_series(half, "WWWWWLLLLL", league_id=LEAGUE, first_match_id=200)
        record_series(full, "WWWWW", league_id=LEAGUE, first_match_id=300)
        summary = self.summary()
        players = summary["players"]
        self.assertEqual(players[str(zero.pk)]["bucket"], 0)
        self.assertEqual(players[str(half.pk)]["bucket"], 5)
        self.assertEqual(players[str(full.pk)]["bucket"], 9)
        distribution = summary["distribution"]
        self.assertEqual(distribution["bucket_size"], 10)
        self.assertEqual(
            [b["count"] for b in distribution["buckets"]],
            [1, 0, 0, 0, 0, 1, 0, 0, 0, 1],
        )
        self.assertEqual(
            [(b["min"], b["max"]) for b in distribution["buckets"]],
            [(i * 10, (i + 1) * 10) for i in range(10)],
        )

    def test_duplicate_rows_agreeing_count_once(self) -> None:
        user = self.player("a")
        record_game(user, league_id=LEAGUE, match_id=100, start_time=T0, won=True)
        record_game(
            user,
            league_id=LEAGUE,
            match_id=100,
            start_time=T0,
            won=True,
            steam_id=user.steamid + 1,
        )
        player = self.summary()["players"][str(user.pk)]
        self.assertEqual(player["games"], 1)
        self.assertEqual(player["wins"], 1)

    def test_duplicate_rows_conflict_resolved_by_steamid(self) -> None:
        user = self.player("a")
        record_game(
            user,
            league_id=LEAGUE,
            match_id=100,
            start_time=T0,
            won=True,
            steam_id=user.steamid + 1,
        )
        record_game(user, league_id=LEAGUE, match_id=100, start_time=T0, won=False)
        player = self.summary()["players"][str(user.pk)]
        self.assertEqual(player["games"], 1)
        self.assertEqual(player["losses"], 1)
        self.assertEqual(player["recent"], ["L"])

    def test_duplicate_rows_conflict_unresolved_skipped(self) -> None:
        linked = self.player("linked")
        unlinked = make_player("nosteam", None)
        record_game(
            linked,
            league_id=LEAGUE,
            match_id=100,
            start_time=T0,
            won=True,
            steam_id=76561198999000001,
        )
        record_game(
            linked,
            league_id=LEAGUE,
            match_id=100,
            start_time=T0,
            won=False,
            steam_id=76561198999000002,
        )
        record_game(
            unlinked,
            league_id=LEAGUE,
            match_id=200,
            start_time=T0,
            won=True,
            steam_id=76561198999000003,
        )
        record_game(
            unlinked,
            league_id=LEAGUE,
            match_id=200,
            start_time=T0,
            won=False,
            steam_id=76561198999000004,
        )
        summary = self.summary(min_games=1)
        self.assertNotIn(str(linked.pk), summary["players"])
        self.assertNotIn(str(unlinked.pk), summary["players"])
        self.assertEqual(summary["population"], 0)

    def test_unlinked_and_other_league_excluded(self) -> None:
        user = self.player("a")
        record_series(user, "WW", league_id=LEAGUE, first_match_id=100)
        record_series(user, "LLL", league_id=OTHER_LEAGUE, first_match_id=200)
        record_game(
            None,
            league_id=LEAGUE,
            match_id=100,
            start_time=T0,
            won=False,
            steam_id=76561198999000009,
        )
        summary = self.summary()
        self.assertEqual(list(summary["players"]), [str(user.pk)])
        self.assertEqual(summary["players"][str(user.pk)]["games"], 2)
        self.assertEqual(summary["players"][str(user.pk)]["wins"], 2)

    def test_unknown_league_returns_empty(self) -> None:
        self.assertEqual(compute_league_summary(99999, 5), empty_league_summary(5))
        empty = empty_league_summary(5)
        self.assertEqual(empty["population"], 0)
        self.assertEqual(empty["players"], {})
        self.assertEqual(
            [b["count"] for b in empty["distribution"]["buckets"]], [0] * 10
        )

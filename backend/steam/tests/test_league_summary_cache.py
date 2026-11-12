from django.test import TransactionTestCase

from steam.functions.league_summary import get_league_summary
from steam.models import Match
from steam.tests.league_summary_fixtures import make_player, record_game, record_series
from tests.cache import flush_run_cache

LEAGUE = 90001


class GetLeagueSummaryCacheTests(TransactionTestCase):
    def setUp(self) -> None:
        flush_run_cache()
        self.user = make_player("cache_user", 76561198000000101)
        record_series(self.user, "WWLWW", league_id=LEAGUE, first_match_id=500)

    def test_second_call_is_cache_hit(self) -> None:
        first = get_league_summary(LEAGUE, 5)
        with self.assertNumQueries(0):
            second = get_league_summary(LEAGUE, 5)
        self.assertEqual(first, second)
        self.assertEqual(second["players"][str(self.user.pk)]["games"], 5)

    def test_min_games_is_part_of_key(self) -> None:
        get_league_summary(LEAGUE, 5)
        with self.assertNumQueries(1):
            summary = get_league_summary(LEAGUE, 3)
        self.assertEqual(summary["min_games"], 3)

    def test_new_match_ingest_invalidates(self) -> None:
        before = get_league_summary(LEAGUE, 5)["players"][str(self.user.pk)]["games"]
        record_game(
            self.user,
            league_id=LEAGUE,
            match_id=600,
            start_time=1_800_000_000,
            won=True,
        )
        after = get_league_summary(LEAGUE, 5)["players"][str(self.user.pk)]
        self.assertEqual(after["games"], before + 1)
        self.assertEqual(after["recent"][-1], "W")

    def test_pms_only_write_on_existing_match_invalidates(self) -> None:
        other = make_player("cache_other", 76561198000000102)
        self.assertNotIn(str(other.pk), get_league_summary(LEAGUE, 5)["players"])
        matches_before = Match.objects.count()
        record_game(other, league_id=LEAGUE, match_id=500, start_time=0, won=False)
        self.assertEqual(Match.objects.count(), matches_before)
        after = get_league_summary(LEAGUE, 5)
        self.assertEqual(after["players"][str(other.pk)]["recent"], ["L"])

    def test_pms_relink_invalidates(self) -> None:
        other = make_player("cache_relink", 76561198000000103)
        orphan = record_game(
            None,
            league_id=LEAGUE,
            match_id=501,
            start_time=0,
            won=True,
            steam_id=other.steamid,
        )
        before = get_league_summary(LEAGUE, 5)
        self.assertNotIn(str(other.pk), before["players"])
        orphan.user = other
        orphan.save()
        after = get_league_summary(LEAGUE, 5)
        self.assertEqual(after["players"][str(other.pk)]["games"], 1)

    def test_match_only_edit_flips_result(self) -> None:
        before = get_league_summary(LEAGUE, 5)["players"][str(self.user.pk)]
        self.assertEqual(before["recent"][-1], "W")
        match = Match.objects.get(match_id=504)
        match.radiant_win = not match.radiant_win
        match.save()
        after = get_league_summary(LEAGUE, 5)["players"][str(self.user.pk)]
        self.assertEqual(after["recent"][-1], "L")
        self.assertEqual(after["wins"], before["wins"] - 1)

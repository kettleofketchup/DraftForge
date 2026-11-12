from unittest import mock

from django.db.models import Count
from django.test import TestCase

from app.models import Draft, League, Organization, Team, TeamDraftState, Tournament
from steam.functions.league_summary import compute_league_summary
from steam.functions.stats_update import player_won
from steam.models import Match
from tests.data.league_stats import (
    SHOWCASE_MATCH_ID_BASE,
    SHOWCASE_MATCH_ID_MAX,
    SHOWCASE_TOURNAMENT_PK,
)
from tests.populate.league_stats import (
    populate_league_stats_data,
    populate_league_stats_showcase,
)

SHOWCASE_STEAM_LEAGUE_ID = 17939
STRIP_STEAM_LEAGUE_ID = 17938
MIN_GAMES = 5


@mock.patch("tests.populate.league_stats.flush_redis_cache")
class LeagueStatsShowcasePopulateTest(TestCase):
    def test_showcase_league_has_a_realistic_spread(self, _flush: mock.Mock) -> None:
        populate_league_stats_showcase()

        league = League.objects.get(pk=21)
        self.assertEqual(league.steam_league_id, SHOWCASE_STEAM_LEAGUE_ID)
        self.assertEqual(league.organization_id, Organization.objects.get(pk=21).pk)

        summary = compute_league_summary(SHOWCASE_STEAM_LEAGUE_ID, MIN_GAMES)
        players = summary["players"]
        ranked = [p for p in players.values() if p["rank"] is not None]
        unranked_games = sorted(
            p["games"] for p in players.values() if p["rank"] is None
        )

        self.assertGreaterEqual(summary["population"], 40)
        self.assertEqual(unranked_games, [1, 2, 4])
        self.assertLess(min(p["win_rate"] for p in ranked), 0.4)
        self.assertGreater(max(p["win_rate"] for p in ranked), 0.6)
        non_empty = [b for b in summary["distribution"]["buckets"] if b["count"] > 0]
        self.assertGreaterEqual(len(non_empty), 6)

        tournament = Tournament.objects.get(pk=SHOWCASE_TOURNAMENT_PK)
        idle = tournament.users.exclude(pk__in=[int(uid) for uid in players])
        self.assertEqual(idle.count(), 3)

    def test_matches_are_five_a_side_with_consistent_winners(
        self, _flush: mock.Mock
    ) -> None:
        populate_league_stats_showcase()

        matches = Match.objects.filter(league_id=SHOWCASE_STEAM_LEAGUE_ID)
        self.assertGreater(matches.count(), 0)
        self.assertFalse(
            matches.exclude(
                match_id__gt=SHOWCASE_MATCH_ID_BASE, match_id__lte=SHOWCASE_MATCH_ID_MAX
            ).exists()
        )
        sizes = set(matches.annotate(n=Count("players")).values_list("n", flat=True))
        self.assertEqual(sizes, {10})

        for match in matches.prefetch_related("players")[:20]:
            rows = list(match.players.all())
            winners = [
                row for row in rows if player_won(row.player_slot, match.radiant_win)
            ]
            self.assertEqual(len(winners), 5)
            self.assertEqual(len({row.player_slot < 128 for row in winners}), 1)

    def test_showcase_draft_is_untimed_and_open(self, _flush: mock.Mock) -> None:
        populate_league_stats_showcase()

        tournament = Tournament.objects.get(pk=SHOWCASE_TOURNAMENT_PK)
        self.assertEqual(tournament.league_id, 21)
        self.assertEqual(Team.objects.filter(tournament=tournament).count(), 8)
        draft = Draft.objects.get(tournament=tournament)
        self.assertEqual(draft.state, TeamDraftState.DRAFTING)
        self.assertFalse(tournament.get_draft_options(fresh=True).timer_enabled)
        self.assertFalse(draft.draft_rounds.filter(choice__isnull=False).exists())

    def test_showcase_is_deterministic_and_leaves_strip_stats_alone(
        self, _flush: mock.Mock
    ) -> None:
        populate_league_stats_data()
        populate_league_stats_showcase()
        first = compute_league_summary(SHOWCASE_STEAM_LEAGUE_ID, MIN_GAMES)

        populate_league_stats_showcase(force=True)
        self.assertEqual(
            compute_league_summary(SHOWCASE_STEAM_LEAGUE_ID, MIN_GAMES), first
        )
        populate_league_stats_showcase()
        self.assertEqual(
            compute_league_summary(SHOWCASE_STEAM_LEAGUE_ID, MIN_GAMES), first
        )

        self.assertEqual(
            compute_league_summary(STRIP_STEAM_LEAGUE_ID, MIN_GAMES)["population"], 7
        )

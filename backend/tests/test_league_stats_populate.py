from unittest import mock

from django.test import TestCase

from app.models import Draft, League, Organization, Team, Tournament
from league.models import LeagueUser
from steam.functions.league_summary import compute_league_summary
from steam.models import LeaguePlayerStats, Match, PlayerMatchStats
from tests.populate.league_stats import populate_league_stats_data

STEAM_LEAGUE_ID = 17938
EXPECTED_RANKS: dict[str, int] = {
    "7000": 1,
    "7001": 2,
    "7002": 3,
    "7003": 3,
    "7004": 5,
    "7005": 6,
    "7008": 7,
}
EXPECTED_LEAGUE_MMR: dict[int, int] = {
    7000: 4200,
    7001: 3900,
    7002: 3500,
    7003: 3400,
    7004: 0,
    7005: 0,
    7006: 0,
    7007: 0,
    7008: 0,
    7009: 0,
}


@mock.patch("tests.populate.league_stats.flush_redis_cache")
class LeagueStatsPopulateTest(TestCase):
    def _counts(self) -> tuple[int, int, int, int, int]:
        return (
            Match.objects.filter(league_id=STEAM_LEAGUE_ID).count(),
            PlayerMatchStats.objects.filter(match__league_id=STEAM_LEAGUE_ID).count(),
            LeaguePlayerStats.objects.filter(league_id=STEAM_LEAGUE_ID).count(),
            Tournament.objects.filter(pk=250).count(),
            LeagueUser.objects.filter(league_id=20).count(),
        )

    def test_populate_creates_expected_league_stats(self, _flush: mock.Mock) -> None:
        populate_league_stats_data()

        org = Organization.objects.get(pk=20)
        league = League.objects.get(pk=20)
        self.assertEqual(league.steam_league_id, STEAM_LEAGUE_ID)
        self.assertEqual(league.organization_id, org.pk)

        summary = compute_league_summary(STEAM_LEAGUE_ID, 5)
        players = summary["players"]
        self.assertEqual(summary["population"], 7)
        self.assertEqual(
            {uid: p["rank"] for uid, p in players.items() if p["rank"] is not None},
            EXPECTED_RANKS,
        )
        self.assertEqual(players["7000"]["top_percent"], 15)
        self.assertEqual(players["7001"]["streak"], {"result": "W", "count": 4})
        self.assertEqual(players["7004"]["streak"], {"result": "L", "count": 3})
        self.assertEqual(players["7006"]["games"], 3)
        self.assertIsNone(players["7006"]["rank"])
        self.assertNotIn("7007", players)
        self.assertNotIn("7009", players)

        self.assertEqual(
            LeaguePlayerStats.objects.filter(league_id=STEAM_LEAGUE_ID).count(), 8
        )
        self.assertEqual(
            dict(
                LeagueUser.objects.filter(league=league).values_list("user_id", "mmr")
            ),
            EXPECTED_LEAGUE_MMR,
        )

        tournament = Tournament.objects.get(pk=250)
        self.assertEqual(tournament.league_id, 20)
        self.assertEqual(tournament.state, "in_progress")
        self.assertEqual(
            set(tournament.users.values_list("pk", flat=True)), set(range(7000, 7010))
        )

        draft = Draft.objects.get(tournament_id=250)
        self.assertEqual(draft.draft_style, "snake")
        self.assertGreater(draft.draft_rounds.count(), 0)
        self.assertFalse(draft.draft_rounds.filter(choice__isnull=False).exists())

        teams = Team.objects.filter(tournament=tournament)
        self.assertEqual(
            sorted(teams.values_list("captain_id", flat=True)), [7008, 7009]
        )
        member_pks = set(teams.values_list("members__pk", flat=True))
        self.assertEqual(member_pks, {7008, 7009})
        available = set(range(7000, 7010)) - member_pks
        self.assertEqual(available, set(range(7000, 7008)))

    def test_populate_is_idempotent(self, _flush: mock.Mock) -> None:
        populate_league_stats_data()
        first = self._counts()
        populate_league_stats_data(force=True)
        self.assertEqual(self._counts(), first)
        populate_league_stats_data()
        self.assertEqual(self._counts(), first)
        self.assertEqual(compute_league_summary(STEAM_LEAGUE_ID, 5)["population"], 7)

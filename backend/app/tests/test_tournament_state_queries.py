"""The tournament response serializes the team draft at a fixed query cost.

The tournament response embeds the draft state; it must cost the same number
of queries for a 4-team and an 8-team draft, serialize byte-identically to the
unprefetched (lazy) serialization, and, like the draft state, ignore a warm,
stale cache.
"""

from collections.abc import Callable
from unittest.mock import patch

from cacheops.conf import settings as cacheops_settings
from django.test import TestCase, TransactionTestCase

from app.functions.tournament import _serialize_tournament
from app.models import Tournament
from app.serializers import TournamentSerializer
from app.tournament_state import tournament_state_queryset
from draft.services.team_state import build_draft_state
from draft.tests.team_fixtures import (
    TimedDraftFixture,
    count_queries,
    dumps,
    legacy_users_dict,
    mid_draft_fixture,
    rename_team,
)

# Upper bound at the time of writing; the 4 == 8 team equality is the real pin.
TOURNAMENT_RESPONSE_QUERIES: int = 23


class TournamentResponseOutputTests(TestCase):
    """The prefetched tournament response is byte-identical to the lazy one."""

    def setUp(self) -> None:
        self.fx = mid_draft_fixture(4, "out")

    def test_tournament_response_matches_lazy_serialization(self) -> None:
        tournament = Tournament.objects.nocache().get(pk=self.fx.tournament.pk)
        lazy = TournamentSerializer(tournament).data
        lazy["_users"] = legacy_users_dict(tournament)
        fresh = Tournament.objects.nocache().get(pk=self.fx.tournament.pk)
        self.assertEqual(dumps(_serialize_tournament(fresh)), dumps(lazy))

    def test_tournament_response_reuses_prefetched_draft_options(self) -> None:
        with patch.object(
            Tournament, "get_draft_options", autospec=True
        ) as get_draft_options:
            data = _serialize_tournament(self.fx.tournament)
        get_draft_options.assert_not_called()
        self.assertEqual(
            data["draft_options"]["grace_time_ms"], self.fx.options.grace_time_ms
        )

    def test_fresh_context_ignores_options_not_loaded_fresh(self) -> None:
        tournament = tournament_state_queryset(fresh=False).get(
            pk=self.fx.tournament.pk
        )
        with patch.object(
            Tournament,
            "get_draft_options",
            autospec=True,
            return_value=self.fx.options,
        ) as get_draft_options:
            TournamentSerializer(tournament, context={"fresh": True}).data
        get_draft_options.assert_called_once_with(tournament, fresh=True)


class TournamentResponseQueryCountTests(TestCase):
    """The tournament response's query count does not grow with teams."""

    def setUp(self) -> None:
        self.small = mid_draft_fixture(4, "q4")
        self.large = mid_draft_fixture(8, "q8")

    def count(self, fn: Callable[[], object]) -> int:
        return count_queries(fn)

    def test_tournament_response_is_constant(self) -> None:
        counts = [
            self.count(
                lambda t=fx.tournament: _serialize_tournament(
                    Tournament.objects.nocache().get(pk=t.pk)
                )
            )
            for fx in (self.small, self.large)
        ]
        self.assertEqual(counts[0], counts[1])
        self.assertLessEqual(counts[0], TOURNAMENT_RESPONSE_QUERIES)


class TournamentResponseFreshTests(TransactionTestCase):
    """The tournament response ignores a warm, stale cache."""

    def setUp(self) -> None:
        if not cacheops_settings.CACHEOPS_ENABLED:
            self.skipTest("cacheops disabled")
        self.fx = TimedDraftFixture(prefix="caller")
        self.team = self.fx.teams[0]
        build_draft_state(self.fx.draft.pk, fresh=False)
        _ = TournamentSerializer(
            tournament_state_queryset(fresh=False).get(pk=self.fx.tournament.pk)
        ).data
        rename_team(self.team.pk)

    def team_name(self, tournament: dict) -> str:
        return next(t["name"] for t in tournament["teams"] if t["pk"] == self.team.pk)

    def test_serialize_tournament_reads_fresh_state(self) -> None:
        data = _serialize_tournament(self.fx.tournament)
        self.assertEqual(self.team_name(data), "Renamed")
        self.assertEqual(self.team_name(data["draft"]["tournament"]), "Renamed")

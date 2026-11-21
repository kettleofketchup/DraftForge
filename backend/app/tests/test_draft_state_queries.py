"""The tournament response serializes the team draft at a fixed query cost.

The tournament response embeds the draft state; it must cost the same number
of queries for a 4-team and an 8-team draft, serialize byte-identically to the
unprefetched (lazy) serialization, and, like the draft state, ignore a warm,
stale cache.
"""

from collections.abc import Callable
from unittest.mock import patch

from cacheops.conf import settings as cacheops_settings
from cacheops.signals import cache_read
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from app.functions.tournament import _serialize_tournament
from app.models import Tournament
from app.serializers import TournamentSerializer
from app.tournament_state import tournament_state_queryset
from draft.models import DraftEvent
from draft.services.team_broadcast import broadcast_event
from draft.services.team_state import build_draft_state
from draft.tests.team_fixtures import (
    FakeChannelLayer,
    TimedDraftFixture,
    count_queries,
    dumps,
    legacy_users_dict,
    mid_draft_fixture,
    rename_team,
)
from events.models import Event
from league.models import LeagueUser
from org.models import Organization, OrgUser

# Includes the OrgUserGameMmr prefetch in the users dict.
TOURNAMENT_RESPONSE_QUERIES: int = 24


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
        self.assertEqual(counts[0], TOURNAMENT_RESPONSE_QUERIES)


class FreshCallerTests(TransactionTestCase):
    """Broadcasts and endpoint responses ignore a warm, stale cache."""

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

    def test_cache_is_stale(self) -> None:
        state = build_draft_state(self.fx.draft.pk, fresh=False)
        self.assertEqual(self.team_name(state["tournament"]), "T1")

    def test_broadcast_event_reads_fresh_state(self) -> None:
        layer = FakeChannelLayer()
        event = DraftEvent.objects.create(
            draft=self.fx.draft, event_type="captain_ready"
        )
        with patch(
            "draft.services.team_broadcast.get_channel_layer", return_value=layer
        ):
            broadcast_event(event)
        self.assertEqual(
            self.team_name(layer.messages[0]["draft_state"]["tournament"]), "Renamed"
        )

    def test_serialize_tournament_reads_fresh_state(self) -> None:
        data = _serialize_tournament(self.fx.tournament)
        self.assertEqual(self.team_name(data), "Renamed")
        self.assertEqual(self.team_name(data["draft"]["tournament"]), "Renamed")


class DraftStateFreshReadTests(TransactionTestCase):
    """fresh=True payloads never read through cacheops, at any level."""

    def setUp(self) -> None:
        if not cacheops_settings.CACHEOPS_ENABLED:
            self.skipTest("cacheops disabled")

    def cached_reads(self, fn: Callable[[], object]) -> list[str]:
        reads: list[str] = []

        def record(sender: type | None, func: object = None, **kwargs: object) -> None:
            reads.append(getattr(sender, "__name__", None) or repr(func))

        cache_read.connect(record)
        try:
            fn()
        finally:
            cache_read.disconnect(record)
        return reads

    def org_fixture(self, prefix: str) -> TimedDraftFixture:
        fx = mid_draft_fixture(4, prefix)
        league = fx.tournament.league
        org_user = OrgUser.objects.get(user=fx.captains[0])
        LeagueUser.objects.create(
            user=fx.captains[0], org_user=org_user, league=league, mmr=1111
        )
        league.admins.add(fx.staff)
        return fx

    def event_fixture(self, prefix: str) -> TimedDraftFixture:
        fx = TimedDraftFixture(prefix=prefix)
        org = Organization.objects.create(name=f"{prefix} org")
        Event.objects.create(
            name=f"{prefix} event",
            organization=org,
            scheduled_at=timezone.now(),
            tournament=fx.tournament,
        )
        return fx

    def serialize_all(self, fx: TimedDraftFixture) -> None:
        build_draft_state(fx.draft.pk, fresh=True)
        _serialize_tournament(fx.tournament)

    def test_fresh_payloads_make_no_cached_reads(self) -> None:
        for label, make in (("org", self.org_fixture), ("event", self.event_fixture)):
            with self.subTest(fixture=label):
                fx = make(f"fr{label}")
                build_draft_state(fx.draft.pk, fresh=False)
                self.assertEqual(self.cached_reads(lambda: self.serialize_all(fx)), [])

    def test_fresh_state_sees_raw_sql_draft_options_change(self) -> None:
        fx = self.org_fixture("frdo")
        tournament_pk = fx.tournament.pk
        build_draft_state(fx.draft.pk, fresh=False)
        _serialize_tournament(fx.tournament)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE app_draftoptions SET grace_time_ms = %s "
                "WHERE tournament_id = %s",
                [12345, tournament_pk],
            )
        state = build_draft_state(fx.draft.pk, fresh=True)
        self.assertEqual(state["draft_options"]["grace_time_ms"], 12345)
        response = _serialize_tournament(fx.tournament)
        self.assertEqual(response["draft_options"]["grace_time_ms"], 12345)
        self.assertEqual(response["draft"]["draft_options"]["grace_time_ms"], 12345)

"""Team-draft state serialization runs a fixed number of SQL queries.

Every path that builds the draft state (broadcast re-fetch, DraftConsumer
initial state, the ready/start/pause/resume/pick/undo responses) must cost the
same number of queries for a 4-team and an 8-team draft, and must serialize
byte-identically to the unprefetched (lazy) serialization.
"""

import json
from collections.abc import Callable
from datetime import datetime
from datetime import timezone as dt_timezone
from unittest.mock import patch

from cacheops.conf import settings as cacheops_settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, reset_queries
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from app.broadcast import broadcast_event
from app.consumers import DraftConsumer
from app.draft_state import build_draft_state
from app.functions.tournament import _serialize_tournament
from app.models import Draft, DraftEvent, Tournament
from app.serializers import (
    DraftSerializerSlim,
    TournamentSerializer,
    _collect_context_mmr,
    _collect_tournament_user_pks,
    _tournament_organization,
)
from app.tests.teamdraft_fixtures import TimedDraftFixture
from app.user_cache import serialize_user_core

BASE: datetime = datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt_timezone.utc)
MMRS_4: list[int] = [1000, 2000, 3000, 4000]
MMRS_8: list[int] = [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000]

# Paused org draft: draft, tournament, rounds, teams, members, dropins, lefts,
# users (8 prefetch), users_remaining, latest_round, draft_options (3), league +
# organization (2), OrgUser lookup, missing-OrgUser probe, OrgUser profiles,
# league memberships (4), bulk _users core (1).
DRAFT_STATE_QUERIES: int = 18
# Ready = the post-commit broadcast (18) + the tournament response (26 with its
# league/source_event/games/captains/draft lookups) + the view's own captain
# check, row locks, update and event insert (6). Measured 47 for 4 and 8 teams.
READY_ENDPOINT_MAX_QUERIES: int = 50


def legacy_users_dict(tournament: Tournament) -> dict:
    """Pre-optimisation _build_users_dict: per-user cached core + MMR overlay."""
    seen_pks = _collect_tournament_user_pks(tournament)
    mmr_map = _collect_context_mmr(tournament, seen_pks)
    is_org = _tournament_organization(tournament) is not None
    result: dict = {}
    for pk in seen_pks:
        core = serialize_user_core(pk)
        if not core:
            continue
        if is_org:
            entry = {k: v for k, v in core.items() if k != "discordNickname"}
            entry.update(mmr_map.get(pk, {}))
        else:
            entry = dict(core)
        result[pk] = entry
    return result


def dumps(data: object) -> str:
    return json.dumps(data, cls=DjangoJSONEncoder)


class FakeChannelLayer:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def group_send(self, group: str, message: dict) -> None:
        self.messages.append(message)


def count_queries(fn: Callable[[], object]) -> int:
    # The query log is a capped deque; a full one makes every capture read 0.
    reset_queries()
    with CaptureQueriesContext(connection) as ctx:
        fn()
    return len(ctx.captured_queries)


def make_fixture(num_teams: int, prefix: str) -> TimedDraftFixture:
    mmrs = MMRS_4 if num_teams == 4 else MMRS_8
    fx = TimedDraftFixture(num_teams=num_teams, prefix=prefix, captain_mmrs=mmrs)
    fx.populate_mid_draft(BASE)
    return fx


def initial_state(draft_id: int) -> dict | None:
    fn = DraftConsumer.__dict__["get_initial_state_data"].func
    return fn(DraftConsumer(), draft_id)


class DraftStateOutputTests(TestCase):
    """Prefetched serialization is byte-identical to the lazy one."""

    def setUp(self) -> None:
        self.fx = make_fixture(4, "out")

    def lazy_draft_state(self) -> dict:
        draft = Draft.objects.nocache().get(pk=self.fx.draft.pk)
        data = DraftSerializerSlim(draft).data
        data["_users"] = {
            str(k): v for k, v in legacy_users_dict(draft.tournament).items()
        }
        return data

    def test_fixture_covers_picks_skip_and_pause(self) -> None:
        state = self.lazy_draft_state()
        self.assertEqual(state["state"], "paused")
        self.assertTrue(state["is_manual_pause"])
        self.assertEqual(sum(1 for r in state["draft_rounds"] if r["choice"]), 2)
        self.assertEqual(sum(r["skip_count"] for r in state["draft_rounds"]), 1)

    def test_build_draft_state_matches_lazy_serialization(self) -> None:
        expected = dumps(self.lazy_draft_state())
        self.assertEqual(
            dumps(build_draft_state(self.fx.draft.pk, fresh=True)), expected
        )
        self.assertEqual(
            dumps(build_draft_state(self.fx.draft.pk, fresh=False)), expected
        )

    def test_broadcast_and_initial_state_match_lazy_serialization(self) -> None:
        expected = dumps(self.lazy_draft_state())
        layer = FakeChannelLayer()
        event = DraftEvent.objects.filter(draft=self.fx.draft).first()
        with patch("app.broadcast.get_channel_layer", return_value=layer):
            broadcast_event(event)
        self.assertEqual(dumps(layer.messages[0]["draft_state"]), expected)
        self.assertEqual(dumps(initial_state(self.fx.draft.pk)), expected)

    def test_tournament_response_matches_lazy_serialization(self) -> None:
        tournament = Tournament.objects.nocache().get(pk=self.fx.tournament.pk)
        lazy = TournamentSerializer(tournament).data
        lazy["_users"] = legacy_users_dict(tournament)
        fresh = Tournament.objects.nocache().get(pk=self.fx.tournament.pk)
        self.assertEqual(dumps(_serialize_tournament(fresh)), dumps(lazy))

    def test_missing_draft_returns_none(self) -> None:
        self.assertIsNone(build_draft_state(10_000_000, fresh=True))


class DraftStateQueryCountTests(TestCase):
    """Query counts do not grow with teams, rounds or users."""

    def setUp(self) -> None:
        self.small = make_fixture(4, "q4")
        self.large = make_fixture(8, "q8")

    def count(self, fn: Callable[[], object]) -> int:
        return count_queries(fn)

    def test_fixture_sizes_differ(self) -> None:
        self.assertEqual(self.small.draft.draft_rounds.count(), 16)
        self.assertEqual(self.large.draft.draft_rounds.count(), 32)

    def test_build_draft_state_is_constant(self) -> None:
        for fx in (self.small, self.large):
            for fresh in (True, False):
                with self.subTest(teams=len(fx.teams), fresh=fresh):
                    reset_queries()
                    with self.assertNumQueries(DRAFT_STATE_QUERIES):
                        build_draft_state(fx.draft.pk, fresh=fresh)

    def test_consumer_initial_state_is_constant(self) -> None:
        for fx in (self.small, self.large):
            with self.subTest(teams=len(fx.teams)):
                reset_queries()
                with self.assertNumQueries(DRAFT_STATE_QUERIES):
                    initial_state(fx.draft.pk)

    def test_broadcast_event_is_constant(self) -> None:
        counts = []
        for fx in (self.small, self.large):
            event = DraftEvent.objects.filter(draft=fx.draft).first()
            with patch(
                "app.broadcast.get_channel_layer", return_value=FakeChannelLayer()
            ):
                counts.append(self.count(lambda e=event: broadcast_event(e)))
        self.assertEqual(counts[0], counts[1])
        self.assertLessEqual(counts[0], DRAFT_STATE_QUERIES + 2)

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

    def test_resume_endpoint_is_constant(self) -> None:
        counts = []
        for fx in (self.small, self.large):
            client = APIClient()
            client.force_authenticate(fx.staff)
            with patch(
                "app.tasks.draft_tick.start_tick_broadcaster", return_value=True
            ):
                counts.append(
                    self.count(
                        lambda f=fx, c=client: self.post_with_commit(
                            c, f"/api/draft/{f.draft.pk}/resume/"
                        )
                    )
                )
        self.assertEqual(counts[0], counts[1])

    def test_undo_endpoint_is_constant(self) -> None:
        counts = []
        for fx in (self.small, self.large):
            with patch(
                "app.tasks.draft_tick.start_tick_broadcaster", return_value=True
            ):
                counts.append(self.count(lambda f=fx: self.undo_with_commit(f)))
        self.assertEqual(counts[0], counts[1])

    def post_with_commit(self, client: APIClient, url: str) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            response = client.post(url, {}, format="json")
        self.assertLess(response.status_code, 300, response.content)

    def undo_with_commit(self, fx: TimedDraftFixture) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            response = fx.undo(fx.staff)
        self.assertEqual(response.status_code, 200, response.data)


class DraftStateFreshnessTests(TransactionTestCase):
    """fresh=True never reads cacheops; fresh=False keeps using it."""

    def team_name(self, state: dict, team_pk: int) -> str:
        return next(
            t["name"] for t in state["tournament"]["teams"] if t["pk"] == team_pk
        )

    def test_fresh_state_ignores_a_warm_cache(self) -> None:
        fx = TimedDraftFixture(prefix="fresh")
        team = fx.teams[0]
        build_draft_state(fx.draft.pk, fresh=False)
        # Raw SQL is invisible to cacheops, so only an uncached read can see it.
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE app_team SET name = %s WHERE id = %s", ["Renamed", team.pk]
            )
        fresh = build_draft_state(fx.draft.pk, fresh=True)
        self.assertEqual(self.team_name(fresh, team.pk), "Renamed")
        if cacheops_settings.CACHEOPS_ENABLED:
            cached = build_draft_state(fx.draft.pk, fresh=False)
            self.assertEqual(self.team_name(cached, team.pk), team.name)


class ReadyEndpointQueryTests(TestCase):
    def ready_queries(self, num_teams: int) -> int:
        fx = TimedDraftFixture(num_teams=num_teams, prefix=f"r{num_teams}")
        client = APIClient()
        client.force_authenticate(fx.captains[0])
        responses: list = []

        def ready() -> None:
            with self.captureOnCommitCallbacks(execute=True):
                responses.append(
                    client.post(
                        f"/api/draft/{fx.draft.pk}/ready/",
                        {"ready": True},
                        format="json",
                    )
                )

        queries = count_queries(ready)
        self.assertEqual(responses[0].status_code, 200, responses[0].content)
        return queries

    def test_ready_endpoint_is_constant_and_bounded(self) -> None:
        small, large = self.ready_queries(4), self.ready_queries(8)
        self.assertEqual(small, large)
        self.assertLessEqual(small, READY_ENDPOINT_MAX_QUERIES)

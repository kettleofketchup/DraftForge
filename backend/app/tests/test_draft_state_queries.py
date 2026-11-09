"""Team-draft state serialization runs a fixed number of SQL queries.

Every path that builds the draft state (broadcast re-fetch, DraftConsumer
initial state, the ready/start/pause/resume/pick/undo responses) must cost the
same number of queries for a 4-team and an 8-team draft, and must serialize
byte-identically to the unprefetched (lazy) serialization.
"""

import contextvars
import json
import threading
from collections.abc import Callable
from datetime import datetime
from datetime import timezone as dt_timezone
from unittest.mock import patch

from cacheops.conf import settings as cacheops_settings
from cacheops.signals import cache_read
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, reset_queries, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from app.broadcast import atomic_sharing_draft_state, broadcast_event
from app.consumers import DraftConsumer
from app.draft_state import (
    build_draft_state,
    draft_state_queryset,
    tournament_state_queryset,
)
from app.functions.tournament import _serialize_tournament
from app.models import (
    Draft,
    DraftEvent,
    DraftRound,
    Organization,
    Team,
    TeamDraftState,
    Tournament,
)
from app.serializers import (
    DraftSerializerSlim,
    TournamentSerializer,
    _collect_context_mmr,
    _collect_tournament_user_pks,
    _tournament_organization,
)
from app.tests.teamdraft_fixtures import TimedDraftFixture
from app.user_cache import serialize_user_core
from events.models import Event
from league.models import LeagueUser
from org.models import OrgUser

BASE: datetime = datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt_timezone.utc)
MMRS_4: list[int] = [1000, 2000, 3000, 4000]
MMRS_8: list[int] = [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000]

# Paused org draft: draft, tournament, rounds, teams, members, dropins, lefts,
# users (8 prefetch), users_remaining (1), draft_options (1), league +
# organization (2), OrgUser lookup, missing-OrgUser probe, OrgUser profiles,
# league memberships (4), bulk _users core (1). latest_round, active_round and
# clock_armed read the prefetched rounds.
DRAFT_STATE_QUERIES: int = 17
# Ready = the post-commit broadcast + the tournament response (with its
# league/source_event/games/captains/draft lookups) + the view's own captain
# check, row locks, update and event insert. Same for 4 and 8 teams.
READY_ENDPOINT_QUERIES: int = 44
# Pick, outermost transaction (TransactionTestCase, cacheops off): 26 for
# auth, locks, the pick, timing, next-round activation and two event inserts
# (+BEGIN/COMMIT), 17 for the one shared broadcast state behind both events,
# 2 data_version stamps (build + reuse), 23 for the tournament response.
PICK_QUERIES: int = 70
# Upper bounds at the time of writing; the 4 == 8 team equality is the real pin.
TOURNAMENT_RESPONSE_QUERIES: int = 24
RESUME_ENDPOINT_QUERIES: int = 55
UNDO_ENDPOINT_QUERIES: int = 65


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


class DraftRoundTeamTests(TestCase):
    """Prefetched DraftRound.team matches the filter(...).first() lookup."""

    def setUp(self) -> None:
        fx = make_fixture(4, "rt")
        self.fx = fx
        Team.objects.create(tournament=fx.tournament, name="NoCaptain", captain=None)
        Team.objects.create(
            tournament=fx.tournament, name="SharedCaptain", captain=fx.captains[1]
        )
        rounds = list(fx.draft.draft_rounds.order_by("pick_number"))
        DraftRound.objects.filter(pk=rounds[-1].pk).update(captain=fx.players[-1])
        DraftRound.objects.filter(pk=rounds[-2].pk).update(captain=None)

    def legacy_team(self, rnd: DraftRound) -> Team | None:
        return Team.objects.filter(
            tournament=rnd.draft.tournament, captain=rnd.captain
        ).first()

    def test_prefetched_team_matches_filter_first(self) -> None:
        draft = draft_state_queryset(fresh=True).get(pk=self.fx.draft.pk)
        rounds = list(draft.draft_rounds.all())
        cases = {
            "no_team": rounds[-1],
            "no_captain": rounds[-2],
            "shared_captain": next(
                r for r in rounds if r.captain_id == self.fx.captains[1].pk
            ),
        }
        for label, rnd in cases.items():
            with self.subTest(case=label):
                expected = self.legacy_team(rnd)
                self.assertEqual(
                    rnd.team.pk if rnd.team else None,
                    expected.pk if expected else None,
                )
        self.assertIsNone(cases["no_team"].team)
        self.assertEqual(cases["no_captain"].team.name, "NoCaptain")
        self.assertEqual(cases["shared_captain"].team, self.fx.teams[1])
        for rnd in rounds:
            expected = self.legacy_team(rnd)
            self.assertEqual(
                rnd.team.pk if rnd.team else None, expected.pk if expected else None
            )

    def test_edge_case_state_matches_lazy_serialization(self) -> None:
        lazy = Draft.objects.nocache().get(pk=self.fx.draft.pk)
        data = DraftSerializerSlim(lazy).data
        data["_users"] = {
            str(k): v for k, v in legacy_users_dict(lazy.tournament).items()
        }
        self.assertEqual(
            dumps(build_draft_state(self.fx.draft.pk, fresh=True)), dumps(data)
        )


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
        self.assertLessEqual(counts[0], TOURNAMENT_RESPONSE_QUERIES)

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
        self.assertLessEqual(counts[0], RESUME_ENDPOINT_QUERIES)

    def test_undo_endpoint_is_constant(self) -> None:
        counts = []
        for fx in (self.small, self.large):
            with patch(
                "app.tasks.draft_tick.start_tick_broadcaster", return_value=True
            ):
                counts.append(self.count(lambda f=fx: self.undo_with_commit(f)))
        self.assertEqual(counts[0], counts[1])
        self.assertLessEqual(counts[0], UNDO_ENDPOINT_QUERIES)

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
        with patch("app.broadcast.get_channel_layer", return_value=layer):
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
        fx = make_fixture(4, prefix)
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

    def test_ready_endpoint_is_constant(self) -> None:
        small, large = self.ready_queries(4), self.ready_queries(8)
        self.assertEqual(small, large)
        self.assertEqual(small, READY_ENDPOINT_QUERIES)


class PickHelpers(TransactionTestCase):
    def armed_fixture(self, num_teams: int) -> TimedDraftFixture:
        fx = make_fixture(num_teams, f"pick{num_teams}")
        Draft.objects.filter(pk=fx.draft.pk).update(
            state=TeamDraftState.DRAFTING, paused_at=None, is_manual_pause=False
        )
        active = Draft.objects.get(pk=fx.draft.pk).active_round
        DraftRound.objects.filter(pk=active.pk).update(started_at=timezone.now())
        return fx

    def pick(self, fx: TimedDraftFixture) -> tuple[int, FakeChannelLayer]:
        layer = FakeChannelLayer()
        draft = Draft.objects.get(pk=fx.draft.pk)
        active = draft.active_round
        player = draft.users_remaining.first()
        responses: list = []
        with (
            patch("app.broadcast.get_channel_layer", return_value=layer),
            patch("app.tasks.draft_tick.start_tick_broadcaster", return_value=True),
        ):
            queries = count_queries(
                lambda: responses.append(fx.pick(active, fx.staff, player))
            )
        self.assertEqual(responses[0].status_code, 201, responses[0].data)
        return queries, layer

    def assert_pick_builds_the_draft_state_once(self) -> None:
        fx = self.armed_fixture(4)
        with patch("app.broadcast.build_draft_state", wraps=build_draft_state) as spy:
            self.pick(fx)
        self.assertEqual(spy.call_count, 1)


@override_settings(CACHEOPS_ENABLED=False)
class PickEndpointQueryTests(PickHelpers):
    """The pick view's outermost transaction builds the broadcast state once."""

    def test_pick_is_constant_and_bounded(self) -> None:
        small, small_layer = self.pick(self.armed_fixture(4))
        large, large_layer = self.pick(self.armed_fixture(8))
        self.assertEqual(small, large)
        self.assertEqual(small, PICK_QUERIES)
        for layer in (small_layer, large_layer):
            # each event goes to the draft_<id> and tournament_<id> groups
            types = [m["payload"]["event_type"] for m in layer.messages[::2]]
            self.assertEqual(types, ["player_picked", "round_started"])
            states = {dumps(m["draft_state"]) for m in layer.messages}
            self.assertEqual(len(states), 1)

    def test_pick_builds_the_draft_state_once(self) -> None:
        self.assert_pick_builds_the_draft_state_once()


@override_settings(CACHEOPS_ENABLED=True)
class PickEndpointCacheopsTests(PickHelpers):
    """The single shared build also holds with cacheops reads and invalidation."""

    def test_pick_builds_the_draft_state_once(self) -> None:
        self.assert_pick_builds_the_draft_state_once()


def rename_team(team_pk: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE app_team SET name = %s WHERE id = %s", ["Renamed", team_pk]
        )


def rename_team_on_another_connection(team_pk: int) -> None:
    def run() -> None:
        try:
            Team.objects.filter(pk=team_pk).update(name="Renamed")
        finally:
            connection.close()

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()


@override_settings(CACHEOPS_ENABLED=False)
class SharedDraftStateTests(TransactionTestCase):
    def broadcast_twice(
        self, between: Callable[[int], None] | None = None, prefix: str = "shared"
    ) -> tuple[list[dict], int]:
        fx = TimedDraftFixture(prefix=prefix)
        team = fx.teams[0]
        first = DraftEvent.objects.create(draft=fx.draft, event_type="captain_ready")
        second = DraftEvent.objects.create(draft=fx.draft, event_type="captain_unready")
        layer = FakeChannelLayer()

        with (
            patch("app.broadcast.get_channel_layer", return_value=layer),
            patch("app.broadcast.build_draft_state", wraps=build_draft_state) as spy,
        ):
            with atomic_sharing_draft_state():
                transaction.on_commit(lambda: broadcast_event(first))
                if between is not None:
                    transaction.on_commit(lambda: between(team.pk))
                transaction.on_commit(lambda: broadcast_event(second))
        return [m["draft_state"] for m in layer.messages[::2]], spy.call_count

    def assert_rebuilt(self, states: list[dict], builds: int) -> None:
        self.assertEqual(builds, 2)
        names = [s["tournament"]["teams"][0]["name"] for s in states]
        self.assertEqual(names, ["T1", "Renamed"])

    def test_state_is_reused_without_writes(self) -> None:
        states, builds = self.broadcast_twice()
        self.assertEqual(builds, 1)
        self.assertEqual(dumps(states[0]), dumps(states[1]))

    def test_a_write_between_broadcasts_rebuilds_the_state(self) -> None:
        self.assert_rebuilt(*self.broadcast_twice(rename_team))

    def test_writes_with_any_whitespace_or_cte_prefix_rebuild_the_state(self) -> None:
        sqls = {
            "newline": "UPDATE\napp_team SET name = %(name)s WHERE id = %(pk)s",
            "tab": "\tUPDATE\tapp_team SET name = %(name)s WHERE id = %(pk)s",
            "cte": (
                "WITH target(id) AS (SELECT %(pk)s) UPDATE app_team "
                "SET name = %(name)s WHERE id IN (SELECT id FROM target)"
            ),
        }
        for label, sql in sqls.items():
            with self.subTest(sql=label):

                def between(pk: int, sql: str = sql) -> None:
                    with connection.cursor() as cursor:
                        cursor.execute(sql, {"name": "Renamed", "pk": pk})

                self.assert_rebuilt(*self.broadcast_twice(between, prefix=label))

    def test_a_write_on_another_connection_rebuilds_the_state(self) -> None:
        self.assert_rebuilt(*self.broadcast_twice(rename_team_on_another_connection))

    def test_a_thread_that_inherits_the_context_builds_its_own_state(self) -> None:
        fx = TimedDraftFixture(prefix="inherit")
        event = DraftEvent.objects.create(draft=fx.draft, event_type="captain_ready")

        def broadcast_from_inheriting_thread() -> None:
            ctx = contextvars.copy_context()

            def run() -> None:
                try:
                    ctx.run(broadcast_event, event)
                finally:
                    connection.close()

            thread = threading.Thread(target=run)
            thread.start()
            thread.join()

        with (
            patch("app.broadcast.get_channel_layer", return_value=FakeChannelLayer()),
            patch("app.broadcast.build_draft_state", wraps=build_draft_state) as spy,
        ):
            with atomic_sharing_draft_state():
                transaction.on_commit(lambda: broadcast_event(event))
                transaction.on_commit(broadcast_from_inheriting_thread)
                transaction.on_commit(lambda: broadcast_event(event))
        self.assertEqual(spy.call_count, 2)

    def test_nested_block_does_not_share(self) -> None:
        fx = TimedDraftFixture(prefix="nested")
        event = DraftEvent.objects.create(draft=fx.draft, event_type="captain_ready")
        with (
            patch("app.broadcast.get_channel_layer", return_value=FakeChannelLayer()),
            patch("app.broadcast.build_draft_state", wraps=build_draft_state) as spy,
        ):
            with transaction.atomic():
                with atomic_sharing_draft_state():
                    transaction.on_commit(lambda: broadcast_event(event))
                    transaction.on_commit(lambda: broadcast_event(event))
        self.assertEqual(spy.call_count, 2)

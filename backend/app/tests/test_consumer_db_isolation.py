"""One consumer's slow DB call must not stall other consumers (#352)."""

import asyncio
import threading
import time
from datetime import date
from typing import Any
from unittest.mock import patch

from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.db import close_old_connections, transaction
from django.test import SimpleTestCase, TransactionTestCase
from django.urls import re_path

from app import consumers
from app.consumers import DraftConsumer, HeroDraftConsumer
from app.consumers_base import consumer_db
from app.models import Draft, DraftTeam, Game, HeroDraft, Team, Tournament
from app.tasks.draft_tick import get_redis_client
from app.tasks.teamdraft_tick import captain_conn_key
from app.tests.ws_helpers import read_until_type

User = get_user_model()

VICTIM_DEADLINE_S: float = 3.0


class Gate:
    """Holds a DB call's worker thread the way a wait on SQLite's write lock does."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def hold(self) -> None:
        self.entered.set()
        self.release.wait(10)

    async def wait_entered(
        self, worker: "asyncio.Future[Any] | None" = None, timeout: float = 10.0
    ) -> None:
        deadline = time.monotonic() + timeout
        while not self.entered.is_set():
            if worker is not None and worker.done():
                await worker
                raise AssertionError("worker finished without reaching the gate")
            if time.monotonic() > deadline:
                raise AssertionError(f"gate not reached within {timeout}s")
            await asyncio.sleep(0.01)


APP = URLRouter(
    [
        re_path(r"api/draft/(?P<draft_id>\d+)/$", DraftConsumer.as_asgi()),
        re_path(r"api/herodraft/(?P<draft_id>\d+)/$", HeroDraftConsumer.as_asgi()),
    ]
)


def _team_draft(name: str, captain: Any) -> Draft:
    tournament = Tournament.objects.create(name=name, date_played=date.today())
    Team.objects.create(
        tournament=tournament, name=f"{name}-1", captain=captain, draft_order=1
    )
    return Draft.objects.create(tournament=tournament, draft_style="snake")


def _hero_draft(name: str, captain1: Any, captain2: Any) -> HeroDraft:
    tournament = Tournament.objects.create(name=name, date_played=date.today())
    team1 = Team.objects.create(
        tournament=tournament, name=f"{name}-1", captain=captain1
    )
    team2 = Team.objects.create(
        tournament=tournament, name=f"{name}-2", captain=captain2
    )
    game = Game.objects.create(
        tournament=tournament, radiant_team=team1, dire_team=team2
    )
    draft = HeroDraft.objects.create(game=game, state="waiting_for_captains")
    DraftTeam.objects.create(draft=draft, tournament_team=team1)
    DraftTeam.objects.create(draft=draft, tournament_team=team2)
    return draft


class ConsumerDbIsolationTests(TransactionTestCase):
    def setUp(self) -> None:
        self.cap_a = User.objects.create_user(username="iso_cap_a", password="x")
        self.cap_b = User.objects.create_user(username="iso_cap_b", password="x")
        self.cap_c = User.objects.create_user(username="iso_cap_c", password="x")
        self.spectator = User.objects.create_user(username="iso_spec", password="x")

    async def _blocked_captain_vs_spectator(
        self, gate: Gate, blocked_path: str, victim_path: str
    ) -> tuple[bool, float]:
        captain = WebsocketCommunicator(APP, blocked_path)
        captain.scope["user"] = self.cap_a
        captain_connect = asyncio.ensure_future(captain.connect(timeout=20))
        await gate.wait_entered()

        spectator = WebsocketCommunicator(APP, victim_path)
        spectator.scope["user"] = self.spectator
        started = time.monotonic()

        async def spectator_gets_state() -> float:
            await spectator.connect(timeout=20)
            await read_until_type(spectator, "initial_state", timeout=20)
            return time.monotonic() - started

        victim = asyncio.ensure_future(spectator_gets_state())
        done, _ = await asyncio.wait({victim}, timeout=VICTIM_DEADLINE_S)
        gate.release.set()
        elapsed = await victim
        await captain_connect
        await spectator.disconnect()
        await captain.disconnect()
        return bool(done), elapsed

    def test_teamdraft_presence_write_wait_does_not_stall_another_drafts_connect(
        self,
    ) -> None:
        blocked = _team_draft("ISO-D1", self.cap_a)
        other = _team_draft("ISO-D2", self.cap_b)
        gate = Gate()
        real_emit = consumers.emit_event

        def emit(draft: Draft, *args: Any, **kwargs: Any) -> Any:
            if draft.pk == blocked.pk and args[0] == "captain_connected":
                gate.hold()
            return real_emit(draft, *args, **kwargs)

        try:
            with patch("app.consumers.emit_event", new=emit):
                unblocked, elapsed = asyncio.run(
                    self._blocked_captain_vs_spectator(
                        gate, f"/api/draft/{blocked.pk}/", f"/api/draft/{other.pk}/"
                    )
                )
        finally:
            get_redis_client().delete(captain_conn_key(blocked.pk, self.cap_a.pk))
        self.assertTrue(
            unblocked,
            f"spectator on another draft waited {elapsed:.2f}s for the blocked write",
        )

    def test_herodraft_state_change_wait_does_not_stall_another_drafts_connect(
        self,
    ) -> None:
        blocked = _hero_draft("ISO-H1", self.cap_a, self.cap_b)
        other = _hero_draft("ISO-H2", self.cap_b, self.cap_c)
        gate = Gate()
        real_broadcast = consumers.broadcast_herodraft_state

        def broadcast(draft: HeroDraft, event_type: str, **kwargs: Any) -> Any:
            if draft.id == blocked.id and event_type == "captain_connected":
                gate.hold()
            return real_broadcast(draft, event_type, **kwargs)

        with patch("app.consumers.broadcast_herodraft_state", new=broadcast):
            unblocked, elapsed = asyncio.run(
                self._blocked_captain_vs_spectator(
                    gate,
                    f"/api/herodraft/{blocked.id}/",
                    f"/api/herodraft/{other.id}/",
                )
            )
        self.assertTrue(
            unblocked,
            f"spectator on another draft waited {elapsed:.2f}s for the blocked write",
        )

    def test_presence_writes_for_one_draft_apply_in_call_order(self) -> None:
        draft = _team_draft("ISO-ORDER", self.cap_a)
        team = Team.objects.get(tournament__draft=draft)
        gate = Gate()
        real_payload = consumers.team_payload

        def payload(t: Team) -> dict[str, Any]:
            if not gate.entered.is_set():
                gate.hold()
            return real_payload(t)

        def consumer() -> DraftConsumer:
            c = DraftConsumer()
            c.draft_id = draft.pk
            return c

        async def scenario() -> None:
            leaving = asyncio.ensure_future(
                consumer().on_captain_state_change(draft.pk, self.cap_a, False)
            )
            await gate.wait_entered(leaving)
            joining = asyncio.ensure_future(
                consumer().on_captain_state_change(draft.pk, self.cap_a, True)
            )
            await asyncio.sleep(0.3)
            gate.release.set()
            await asyncio.gather(leaving, joining)

        r = get_redis_client()
        key = captain_conn_key(draft.pk, self.cap_a.pk)
        r.set(key, 1)
        try:
            with patch("app.consumers.team_payload", new=payload):
                asyncio.run(scenario())
        finally:
            r.delete(key)
        team.refresh_from_db()
        self.assertTrue(team.draft_is_connected)


class ConsumerDbContentionTests(TransactionTestCase):
    """Pool threads each hold their own connection, as daphne does in production."""

    def test_read_succeeds_while_another_pool_thread_holds_a_write(self) -> None:
        captain1 = User.objects.create_user(username="lock-c1", password="x")
        captain2 = User.objects.create_user(username="lock-c2", password="x")
        draft = _hero_draft("lock", captain1, captain2)
        gate = Gate()

        @consumer_db
        def hold_write() -> None:
            with transaction.atomic():
                DraftTeam.objects.filter(draft=draft).update(is_connected=True)
                gate.hold()

        @consumer_db
        def read_captain_team() -> int:
            return DraftTeam.objects.filter(
                draft=draft, tournament_team__captain=captain2
            ).count()

        async def scenario() -> int:
            writer = asyncio.ensure_future(hold_write())
            await gate.wait_entered(writer)
            try:
                return await asyncio.wait_for(read_captain_team(), VICTIM_DEADLINE_S)
            finally:
                gate.release.set()
                await writer

        self.assertEqual(asyncio.run(scenario()), 1)


class ConsumerDbConnectionCleanupTests(SimpleTestCase):
    def test_pool_thread_closes_its_connection_around_each_call(self) -> None:
        events: list[tuple[str, str]] = []

        def spy_close() -> None:
            events.append(("close", threading.current_thread().name))
            close_old_connections()

        @consumer_db
        def work() -> None:
            events.append(("work", threading.current_thread().name))

        with patch("channels.db.close_old_connections", new=spy_close):
            asyncio.run(work())

        self.assertEqual([e for e, _ in events], ["close", "work", "close"])
        self.assertEqual(len({t for _, t in events}), 1)
        self.assertTrue(events[0][1].startswith("ws-db"), events)

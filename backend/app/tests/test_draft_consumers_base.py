"""DraftConsumer on BaseDraftConsumer: heartbeat, counts, prefix isolation, no kick/loop (spec §1)."""

import asyncio
import threading
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import redis
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.urls import re_path

from app.consumers import DraftConsumer
from app.models import Draft, Team, Tournament
from app.tasks import teamdraft_tick
from app.tasks.draft_tick import (
    captain_channel_key,
    conn_count_key,
    get_connection_count,
    get_redis_client,
    heartbeat_key,
    increment_connection_count,
    touch_connection,
)
from app.tests.ws_helpers import assert_no_frame_except_ping, read_until_type

User = get_user_model()


class DraftConsumerBaseTestCase(TransactionTestCase):
    def setUp(self):
        self.captain = User.objects.create_user(username="tdc_captain", password="x")
        self.spectator = User.objects.create_user(
            username="tdc_spectator", password="x"
        )
        self.tournament = Tournament.objects.create(
            name="TDC", date_played=date.today()
        )
        self.team = Team.objects.create(
            tournament=self.tournament, name="T1", captain=self.captain, draft_order=1
        )
        self.draft = Draft.objects.create(
            tournament=self.tournament, draft_style="snake"
        )
        self.r = get_redis_client()
        self._clear_keys()

    def tearDown(self):
        self._clear_keys()

    def _clear_keys(self):
        self.r.delete(
            conn_count_key("teamdraft", self.draft.pk),
            conn_count_key("herodraft", self.draft.pk),
            heartbeat_key("teamdraft", self.draft.pk, self.captain.pk),
            captain_channel_key("teamdraft", self.draft.pk, self.captain.pk),
            teamdraft_tick.captain_conn_key(self.draft.pk, self.captain.pk),
        )

    def app(self):
        return URLRouter(
            [re_path(r"api/draft/(?P<draft_id>\d+)/$", DraftConsumer.as_asgi())]
        )

    async def connect(self, user=None):
        comm = WebsocketCommunicator(self.app(), f"/api/draft/{self.draft.pk}/")
        if user is not None:
            comm.scope["user"] = user
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        initial_state = await read_until_type(comm, "initial_state")
        initial_events = await read_until_type(comm, "initial_events")
        if user is not None and user.pk == self.captain.pk:
            await read_until_type(comm, "draft_event")
        return comm, initial_state, initial_events

    async def test_spectator_gets_initial_state_then_initial_events_and_counts_under_teamdraft(
        self,
    ):
        comm, state_frame, events_frame = await self.connect(self.spectator)
        self.assertEqual(state_frame["type"], "initial_state")
        self.assertEqual(events_frame["type"], "initial_events")
        self.assertIn("events", events_frame)
        self.assertNotIn("draft_state", events_frame)
        self.assertEqual(state_frame["draft_state"]["pk"], self.draft.pk)
        self.assertIn("server_time", state_frame)
        self.assertEqual(get_connection_count("teamdraft", self.draft.pk), 1)
        self.assertEqual(get_connection_count("herodraft", self.draft.pk), 0)
        await assert_no_frame_except_ping(comm, 0.5)
        await comm.disconnect()
        self.assertEqual(get_connection_count("teamdraft", self.draft.pk), 0)

    async def test_captain_registers_heartbeat_and_channel_under_teamdraft(self):
        comm, _, _ = await self.connect(self.captain)
        hb = heartbeat_key("teamdraft", self.draft.pk, self.captain.pk)
        self.assertIsNotNone(self.r.get(hb))
        self.assertIsNotNone(
            self.r.get(captain_channel_key("teamdraft", self.draft.pk, self.captain.pk))
        )
        before = float(self.r.get(hb))
        await asyncio.sleep(0.05)
        await comm.send_json_to({"type": "heartbeat"})
        await asyncio.sleep(0.2)
        self.assertGreater(float(self.r.get(hb)), before)
        await comm.disconnect()

    async def test_clean_close_keeps_heartbeat_key(self):
        comm, _, _ = await self.connect(self.captain)
        hb = heartbeat_key("teamdraft", self.draft.pk, self.captain.pk)
        await comm.disconnect()
        self.assertIsNotNone(
            self.r.get(hb), "clear_heartbeat_on_disconnect=False keeps the key"
        )
        self.assertIsNone(
            self.r.get(captain_channel_key("teamdraft", self.draft.pk, self.captain.pk))
        )

    async def test_two_sockets_same_captain_both_stay_connected(self):
        comm1, _, _ = await self.connect(self.captain)
        comm2, _, _ = await self.connect(self.captain)
        await read_until_type(comm1, "draft_event")
        for comm in (comm1, comm2):
            await assert_no_frame_except_ping(comm, 0.5)
        self.assertEqual(get_connection_count("teamdraft", self.draft.pk), 2)
        await comm1.disconnect()
        await comm2.disconnect()

    async def test_open_socket_reregisters_after_its_count_key_is_lost(self):
        with patch("app.tasks.draft_tick.CONN_REFRESH_SECONDS", 0.1):
            comm, _, _ = await self.connect(self.spectator)
            self.r.delete(conn_count_key("teamdraft", self.draft.pk))
            await asyncio.sleep(1.5)
            self.assertEqual(get_connection_count("teamdraft", self.draft.pk), 1)
            await comm.disconnect()

    async def test_refresh_runs_without_the_ping_loop(self):
        with (
            patch.object(DraftConsumer, "PING_ENABLED", False),
            patch("app.tasks.draft_tick.CONN_REFRESH_SECONDS", 0.1),
        ):
            comm, _, _ = await self.connect(self.spectator)
            self.r.delete(conn_count_key("teamdraft", self.draft.pk))
            await asyncio.sleep(0.5)
            self.assertEqual(get_connection_count("teamdraft", self.draft.pk), 1)
            await comm.disconnect()
        self.assertEqual(get_connection_count("teamdraft", self.draft.pk), 0)

    async def test_refresh_registers_a_socket_whose_connect_increment_failed(self):
        with (
            patch(
                "app.tasks.draft_tick.increment_connection_count",
                side_effect=redis.RedisError("down"),
            ),
            patch("app.tasks.draft_tick.CONN_REFRESH_SECONDS", 0.1),
        ):
            comm, _, _ = await self.connect(self.spectator)
            self.assertEqual(get_connection_count("teamdraft", self.draft.pk), 0)
            await asyncio.sleep(0.5)
            self.assertEqual(get_connection_count("teamdraft", self.draft.pk), 1)
            await comm.disconnect()
        self.assertEqual(get_connection_count("teamdraft", self.draft.pk), 0)

    async def test_refresh_restarts_a_tick_loop_that_stopped_as_the_socket_connected(
        self,
    ):
        # The loop read zero connections and was exiting with the lock still held,
        # so the connect-time start lost the NX race; the refresh must retry.
        attempts: list[int] = []

        def start(driver: object, draft_id: int) -> bool:
            attempts.append(draft_id)
            return len(attempts) > 1

        with (
            patch.object(
                DraftConsumer, "should_start_tick_broadcaster", return_value=True
            ),
            patch("app.tasks.draft_tick.start_tick_broadcaster", side_effect=start),
            patch("app.tasks.draft_tick.CONN_REFRESH_SECONDS", 0.1),
        ):
            comm, _, _ = await self.connect(self.spectator)
            await asyncio.sleep(0.5)
            await comm.disconnect()
        self.assertGreaterEqual(len(attempts), 2)

    async def test_refresh_does_not_start_a_loop_for_an_idle_draft(self):
        with (
            patch("app.tasks.draft_tick.start_tick_broadcaster") as start,
            patch("app.tasks.draft_tick.CONN_REFRESH_SECONDS", 0.1),
        ):
            comm, _, _ = await self.connect(self.spectator)
            await asyncio.sleep(0.4)
            await comm.disconnect()
        start.assert_not_called()

    async def test_a_crashing_handler_still_runs_disconnect_cleanup(self):
        comm, _, _ = await self.connect(self.captain)
        self.assertEqual(get_connection_count("teamdraft", self.draft.pk), 1)
        with patch.object(
            DraftConsumer, "draft_tick", side_effect=RuntimeError("boom")
        ):
            await get_channel_layer().group_send(
                f"draft_{self.draft.pk}", {"type": "draft.tick"}
            )
            with self.assertRaises(RuntimeError):
                await comm.wait(timeout=5)
        self.assertEqual(get_connection_count("teamdraft", self.draft.pk), 0)
        self.assertIsNone(
            self.r.get(teamdraft_tick.captain_conn_key(self.draft.pk, self.captain.pk))
        )
        team = await database_sync_to_async(Team.objects.nocache().get)(pk=self.team.pk)
        self.assertFalse(team.draft_is_connected)

    async def test_a_failing_fallback_cleanup_keeps_the_handler_error(self):
        comm, _, _ = await self.connect(self.spectator)
        with (
            patch.object(DraftConsumer, "draft_tick", side_effect=RuntimeError("boom")),
            patch.object(
                DraftConsumer, "disconnect", side_effect=ValueError("cleanup")
            ),
        ):
            await get_channel_layer().group_send(
                f"draft_{self.draft.pk}", {"type": "draft.tick"}
            )
            with self.assertRaisesRegex(RuntimeError, "boom"):
                await comm.wait(timeout=5)

    async def test_the_fallback_cleanup_is_time_bounded(self):
        async def hang(consumer: DraftConsumer, code: int | None) -> None:
            await asyncio.sleep(30)

        comm, _, _ = await self.connect(self.spectator)
        with (
            patch.object(DraftConsumer, "draft_tick", side_effect=RuntimeError("boom")),
            patch.object(DraftConsumer, "disconnect", hang),
            patch("app.consumers_base.FALLBACK_CLEANUP_TIMEOUT_S", 0.2),
        ):
            await get_channel_layer().group_send(
                f"draft_{self.draft.pk}", {"type": "draft.tick"}
            )
            with self.assertRaises(RuntimeError):
                await comm.wait(timeout=3)

    async def test_ping_frames_arrive_within_2s(self):
        comm, _, _ = await self.connect(self.spectator)
        frame = await read_until_type(comm, "ping", timeout=2)
        self.assertEqual(frame["type"], "ping")
        await comm.disconnect()

    @patch("app.tasks.draft_tick.start_tick_broadcaster")
    @patch("app.tasks.herodraft_tick.start_tick_broadcaster")
    async def test_no_tick_broadcaster_started(self, hero_start, shared_start):
        comm, _, _ = await self.connect(self.captain)
        hero_start.assert_not_called()
        shared_start.assert_not_called()
        await comm.disconnect()

    async def test_anonymous_heartbeat_is_ignored(self):
        comm, _, _ = await self.connect(user=None)
        await comm.send_json_to({"type": "heartbeat"})
        await assert_no_frame_except_ping(comm, 0.5)
        await comm.disconnect()

    async def test_malformed_json_from_captain_keeps_socket_open(self):
        comm, _, _ = await self.connect(self.captain)
        await comm.send_to(text_data="{not json")
        await assert_no_frame_except_ping(comm, 0.5)
        await comm.disconnect()


class RefreshInFlightAtDisconnectTests(TransactionTestCase):
    def setUp(self) -> None:
        self.tournament = Tournament.objects.create(
            name="TDR", date_played=date.today()
        )
        self.draft = Draft.objects.create(
            tournament=self.tournament, draft_style="snake"
        )
        self.key = conn_count_key("teamdraft", self.draft.pk)
        get_redis_client().delete(self.key)

    def tearDown(self) -> None:
        get_redis_client().delete(self.key)

    def _consumer(self) -> DraftConsumer:
        consumer = DraftConsumer()
        consumer.draft_id = self.draft.pk
        consumer.channel_name = "test.refresh-inflight"
        consumer.room_group_name = f"draft_{self.draft.pk}"
        consumer.channel_layer = SimpleNamespace(group_discard=AsyncMock())
        consumer._is_captain = False
        consumer._tick_wanted = True
        consumer._connection_tracked = True
        return consumer

    def test_a_touch_in_flight_at_disconnect_cannot_re_add_the_socket(self) -> None:
        entered, release = threading.Event(), threading.Event()

        def blocked_touch(prefix: str, draft_id: int, channel: str) -> None:
            entered.set()
            release.wait(5)
            touch_connection(prefix, draft_id, channel)

        consumer = self._consumer()
        increment_connection_count("teamdraft", self.draft.pk, consumer.channel_name)

        async def scenario() -> None:
            consumer._refresh_task = asyncio.ensure_future(
                consumer._connection_refresh_loop()
            )
            while not entered.is_set():
                await asyncio.sleep(0.01)
            closing = asyncio.ensure_future(consumer.base_disconnect(1000))
            await asyncio.sleep(0.1)
            release.set()
            await closing
            await asyncio.sleep(0.2)

        with (
            patch("app.tasks.draft_tick.touch_connection", new=blocked_touch),
            patch("app.tasks.draft_tick.start_tick_broadcaster") as start,
            patch("app.tasks.draft_tick.CONN_REFRESH_SECONDS", 0.05),
        ):
            asyncio.run(scenario())
        self.assertEqual(get_connection_count("teamdraft", self.draft.pk), 0)
        start.assert_not_called()


class RedisOffEventLoopTests(TransactionTestCase):
    """Initial frames and heartbeats must not run blocking Redis on the loop."""

    def setUp(self) -> None:
        self.captain = User.objects.create_user(username="rol_captain", password="x")
        self.tournament = Tournament.objects.create(
            name="ROL", date_played=date.today()
        )
        Team.objects.create(
            tournament=self.tournament,
            name="T1",
            captain=self.captain,
            draft_order=1,
        )
        self.draft = Draft.objects.create(
            tournament=self.tournament, draft_style="snake"
        )
        self.threads: list[tuple[str, int]] = []

    def _recording_redis(self) -> SimpleNamespace:
        real = get_redis_client()

        def record(name: str):
            def call(*args, **kwargs):
                self.threads.append((name, threading.get_ident()))
                return getattr(real, name)(*args, **kwargs)

            return call

        return SimpleNamespace(
            **{n: record(n) for n in ("get", "set", "exists", "expire")}
        )

    def _consumer(self, is_captain: bool) -> DraftConsumer:
        consumer = DraftConsumer()
        consumer.draft_id = self.draft.pk
        consumer.user = self.captain
        consumer.channel_name = "test.redis-off-loop"
        consumer.room_group_name = f"draft_{self.draft.pk}"
        consumer.channel_layer = SimpleNamespace(group_send=AsyncMock())
        consumer._is_captain = is_captain
        consumer.send = AsyncMock()
        consumer._redis = self._recording_redis
        return consumer

    def _assert_all_off_loop(self, loop_thread: int, expected: set[str]) -> None:
        self.assertTrue(expected <= {n for n, _ in self.threads}, self.threads)
        self.assertNotIn(loop_thread, {t for _, t in self.threads})

    def test_send_initial_messages_reads_redis_off_the_loop_before_sending(
        self,
    ) -> None:
        consumer = self._consumer(is_captain=False)
        state = {"tournament": {"teams": [{"captain": self.captain.pk}]}}
        order: list[str] = []

        async def scenario() -> int:
            async def send(**kwargs) -> None:
                order.append(kwargs["text_data"][:30])

            consumer.send = send
            await consumer.send_initial_messages(state)
            return threading.get_ident()

        loop_thread = asyncio.run(scenario())
        self._assert_all_off_loop(loop_thread, {"get"})
        self.assertIn("initial_state", order[0])
        self.assertIn("initial_events", order[1])

    def test_captain_heartbeat_touches_redis_off_the_loop(self) -> None:
        consumer = self._consumer(is_captain=True)

        async def scenario() -> int:
            with patch.object(DraftConsumer, "_restore_presence", new=AsyncMock()):
                await consumer.handle_heartbeat()
            return threading.get_ident()

        loop_thread = asyncio.run(scenario())
        self._assert_all_off_loop(loop_thread, {"get", "set", "exists"})

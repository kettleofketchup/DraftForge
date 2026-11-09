"""DraftConsumer on BaseDraftConsumer: heartbeat, counts, prefix isolation, no kick/loop (spec §1)."""

import asyncio
from datetime import date
from unittest.mock import patch

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

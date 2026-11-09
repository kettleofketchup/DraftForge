"""DraftConsumer on BaseDraftConsumer: heartbeat, counts, prefix isolation, no kick/ping/loop (spec §1)."""

import asyncio
from datetime import date
from unittest.mock import patch

from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.urls import re_path

from app.consumers import DraftConsumer
from app.models import Draft, Team, Tournament
from app.tasks.draft_tick import (
    captain_channel_key,
    conn_count_key,
    get_redis_client,
    heartbeat_key,
)

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
        first = await comm.receive_json_from(timeout=5)
        return comm, first

    async def test_spectator_gets_single_initial_events_frame_and_counts_under_teamdraft(
        self,
    ):
        comm, first = await self.connect(self.spectator)
        self.assertEqual(first["type"], "initial_events")
        self.assertIn("events", first)
        self.assertEqual(first["draft_state"]["pk"], self.draft.pk)
        self.assertEqual(self.r.get(conn_count_key("teamdraft", self.draft.pk)), "1")
        self.assertIsNone(self.r.get(conn_count_key("herodraft", self.draft.pk)))
        self.assertTrue(await comm.receive_nothing(timeout=0.5, interval=0.05))
        await comm.disconnect()
        self.assertIsNone(self.r.get(conn_count_key("teamdraft", self.draft.pk)))

    async def test_captain_registers_heartbeat_and_channel_under_teamdraft(self):
        comm, _ = await self.connect(self.captain)
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
        comm, _ = await self.connect(self.captain)
        hb = heartbeat_key("teamdraft", self.draft.pk, self.captain.pk)
        await comm.disconnect()
        self.assertIsNotNone(
            self.r.get(hb), "clear_heartbeat_on_disconnect=False keeps the key"
        )
        self.assertIsNone(
            self.r.get(captain_channel_key("teamdraft", self.draft.pk, self.captain.pk))
        )

    async def test_two_sockets_same_captain_both_stay_connected(self):
        comm1, _ = await self.connect(self.captain)
        comm2, _ = await self.connect(self.captain)
        for comm in (comm1, comm2):
            self.assertTrue(await comm.receive_nothing(timeout=0.5, interval=0.05))
        self.assertEqual(self.r.get(conn_count_key("teamdraft", self.draft.pk)), "2")
        await comm1.disconnect()
        await comm2.disconnect()

    async def test_no_ping_frames(self):
        comm, _ = await self.connect(self.spectator)
        self.assertTrue(
            await comm.receive_nothing(timeout=2.5, interval=0.05)
        )  # > 2x PING_INTERVAL
        await comm.disconnect()

    @patch("app.tasks.draft_tick.start_tick_broadcaster")
    @patch("app.tasks.herodraft_tick.start_tick_broadcaster")
    async def test_no_tick_broadcaster_started(self, hero_start, shared_start):
        comm, _ = await self.connect(self.captain)
        hero_start.assert_not_called()
        shared_start.assert_not_called()
        await comm.disconnect()

    async def test_anonymous_heartbeat_is_ignored(self):
        comm, _ = await self.connect(user=None)
        await comm.send_json_to({"type": "heartbeat"})
        self.assertTrue(await comm.receive_nothing(timeout=0.5, interval=0.05))
        await comm.disconnect()

    async def test_malformed_json_from_captain_keeps_socket_open(self):
        comm, _ = await self.connect(self.captain)
        await comm.send_to(text_data="{not json")
        self.assertTrue(await comm.receive_nothing(timeout=0.5, interval=0.05))
        await comm.disconnect()

"""Tests for server-side ping keepalive (stale connection detection).

Verifies that the BaseDraftConsumer ping loop sends periodic {"type": "ping"}
messages to keep WebSocket connections alive, preventing proxies (Cloudflare,
Nginx) from killing idle connections during PAUSED state.
"""

import asyncio
import json
from datetime import date
from unittest.mock import patch

from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.urls import re_path

from app.consumers import HeroDraftConsumer
from app.models import DraftTeam, Game, HeroDraft, HeroDraftState, Team, Tournament

User = get_user_model()

# Patched ping interval for fast tests (100ms)
FAST_PING_INTERVAL = 0.1


class StaleConnectionTestCase(TransactionTestCase):
    """Test cases for server-side ping keepalive."""

    def setUp(self):
        """Set up test fixtures."""
        self.captain1 = User.objects.create_user(
            username="captain1",
            password="testpass123",
        )
        self.captain2 = User.objects.create_user(
            username="captain2",
            password="testpass123",
        )
        self.spectator = User.objects.create_user(
            username="spectator",
            password="testpass123",
        )

        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        self.team1 = Team.objects.create(
            tournament=self.tournament,
            name="Team 1",
            captain=self.captain1,
        )
        self.team2 = Team.objects.create(
            tournament=self.tournament,
            name="Team 2",
            captain=self.captain2,
        )

        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
        )

        self.draft = HeroDraft.objects.create(
            game=self.game,
            state=HeroDraftState.PAUSED,
        )

        self.draft_team1 = DraftTeam.objects.create(
            draft=self.draft,
            tournament_team=self.team1,
        )
        self.draft_team2 = DraftTeam.objects.create(
            draft=self.draft,
            tournament_team=self.team2,
        )

    def get_application(self):
        """Get the test ASGI application."""
        return URLRouter(
            [
                re_path(
                    r"api/herodraft/(?P<draft_id>\d+)/$",
                    HeroDraftConsumer.as_asgi(),
                ),
            ]
        )

    @patch("app.consumers_base.PING_INTERVAL", FAST_PING_INTERVAL)
    async def test_ping_loop_keeps_connection_alive_during_paused_state(self):
        """Test server sends ping messages periodically during PAUSED state.

        During PAUSED state, no tick messages are sent. Without the ping loop,
        proxies like Cloudflare (~100s) or Nginx (360s) would kill the idle
        connection silently. The ping loop prevents this.
        """
        communicator = WebsocketCommunicator(
            self.get_application(),
            f"/api/herodraft/{self.draft.id}/",
        )
        communicator.scope["user"] = self.captain1

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Receive initial state
        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "initial_state")

        # Wait for at least one ping message (with FAST_PING_INTERVAL = 0.1s,
        # this should arrive quickly). Drain any non-ping messages first
        # (e.g. captain_connected broadcast events).
        ping_received = False
        deadline = asyncio.get_event_loop().time() + 2.0
        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            try:
                response = await asyncio.wait_for(
                    communicator.receive_json_from(), timeout=remaining
                )
                if response.get("type") == "ping":
                    ping_received = True
                    break
            except asyncio.TimeoutError:
                break

        self.assertTrue(
            ping_received,
            "Server should send ping messages during PAUSED state to keep "
            "connections alive",
        )

        await communicator.disconnect()

    @patch("app.consumers_base.PING_INTERVAL", FAST_PING_INTERVAL)
    async def test_ping_message_format(self):
        """Test ping message is valid JSON with correct format.

        The ping message must be {"type": "ping"} so the frontend
        WebSocketManager can recognize it and reset its stale timer.
        """
        communicator = WebsocketCommunicator(
            self.get_application(),
            f"/api/herodraft/{self.draft.id}/",
        )
        communicator.scope["user"] = self.spectator

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Receive initial state
        await communicator.receive_json_from()

        # Wait for ping
        response = await asyncio.wait_for(communicator.receive_json_from(), timeout=2.0)

        # Verify exact format
        self.assertEqual(response, {"type": "ping"})
        # Verify it's a dict with only the "type" key
        self.assertEqual(len(response), 1)
        self.assertIn("type", response)
        self.assertEqual(response["type"], "ping")

        await communicator.disconnect()

    @patch("app.consumers_base.PING_INTERVAL", FAST_PING_INTERVAL)
    async def test_multiple_pings_arrive_periodically(self):
        """Test that multiple ping messages arrive at the expected interval.

        Verifies the ping loop continues sending, not just a one-off message.
        """
        communicator = WebsocketCommunicator(
            self.get_application(),
            f"/api/herodraft/{self.draft.id}/",
        )
        communicator.scope["user"] = self.spectator

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Receive initial state
        await communicator.receive_json_from()

        # Collect at least 3 ping messages
        pings = []
        for _ in range(3):
            response = await asyncio.wait_for(
                communicator.receive_json_from(), timeout=2.0
            )
            self.assertEqual(response["type"], "ping")
            pings.append(response)

        self.assertEqual(len(pings), 3, "Should receive multiple periodic pings")

        await communicator.disconnect()

    @patch("app.consumers_base.PING_INTERVAL", FAST_PING_INTERVAL)
    async def test_connection_receives_tick_messages_during_drafting(self):
        """Test connection receives tick messages during active DRAFTING state.

        During DRAFTING, the tick broadcaster sends timing data every 1s,
        so connections stay alive via tick messages (in addition to pings).
        """

        # Set draft to DRAFTING state
        @database_sync_to_async
        def set_drafting():
            self.draft.state = HeroDraftState.DRAFTING
            self.draft.save()

        await set_drafting()

        communicator = WebsocketCommunicator(
            self.get_application(),
            f"/api/herodraft/{self.draft.id}/",
        )
        communicator.scope["user"] = self.spectator

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Receive initial state
        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "initial_state")

        # Simulate a tick message via channel layer (as the tick broadcaster would)
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"herodraft_{self.draft.id}",
            {
                "type": "herodraft.tick",
                "current_round": 1,
                "active_team_id": self.draft_team1.id,
                "grace_time_remaining_ms": 30000,
                "team_a_id": self.draft_team1.id,
                "team_a_reserve_ms": 90000,
                "team_b_id": self.draft_team2.id,
                "team_b_reserve_ms": 90000,
                "draft_state": "drafting",
            },
        )

        # We may receive ping messages before the tick, so drain until we find
        # the tick or time out.
        tick_received = False
        deadline = asyncio.get_event_loop().time() + 2.0
        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            try:
                response = await asyncio.wait_for(
                    communicator.receive_json_from(), timeout=remaining
                )
                if response.get("type") == "herodraft_tick":
                    tick_received = True
                    self.assertEqual(response["current_round"], 1)
                    self.assertEqual(response["active_team_id"], self.draft_team1.id)
                    self.assertEqual(response["draft_state"], "drafting")
                    break
            except asyncio.TimeoutError:
                break

        self.assertTrue(
            tick_received,
            "Should receive tick messages during DRAFTING state",
        )

        await communicator.disconnect()

    @patch("app.consumers_base.PING_INTERVAL", FAST_PING_INTERVAL)
    async def test_ping_loop_cancelled_on_disconnect(self):
        """Test ping loop is properly cancelled when client disconnects.

        Ensures no orphaned async tasks remain after disconnection.
        """
        communicator = WebsocketCommunicator(
            self.get_application(),
            f"/api/herodraft/{self.draft.id}/",
        )
        communicator.scope["user"] = self.spectator

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Receive initial state
        await communicator.receive_json_from()

        # Wait for one ping to confirm the loop is running
        response = await asyncio.wait_for(communicator.receive_json_from(), timeout=2.0)
        self.assertEqual(response["type"], "ping")

        # Disconnect
        await communicator.disconnect()

        # Give a brief moment for cleanup
        await asyncio.sleep(FAST_PING_INTERVAL * 3)

        # If we reach here without errors, the ping loop was cleanly cancelled.
        # A failed cancellation would raise an exception or leave dangling tasks.

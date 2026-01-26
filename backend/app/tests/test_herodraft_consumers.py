"""Tests for HeroDraft WebSocket consumer."""

import asyncio
import json
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.urls import re_path
from django.utils import timezone

from app.consumers import HeroDraftConsumer
from app.models import (
    DraftTeam,
    Game,
    HeroDraft,
    HeroDraftRound,
    HeroDraftState,
    Team,
    Tournament,
)

User = get_user_model()


class HeroDraftConsumerTestCase(TransactionTestCase):
    """Test cases for HeroDraftConsumer WebSocket consumer."""

    def setUp(self):
        """Set up test fixtures."""
        # Create users for captains
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

        # Create tournament and teams
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

        # Create game
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team1,
            dire_team=self.team2,
        )

        # Create hero draft
        self.draft = HeroDraft.objects.create(
            game=self.game,
            state="waiting_for_captains",
        )

        # Create draft teams
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

    async def test_connect_valid_draft(self):
        """Test successful connection to valid draft."""
        communicator = WebsocketCommunicator(
            self.get_application(),
            f"/api/herodraft/{self.draft.id}/",
        )
        communicator.scope["user"] = self.spectator

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Should receive initial state
        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "initial_state")
        self.assertIn("draft_state", response)
        self.assertEqual(response["draft_state"]["id"], self.draft.id)

        await communicator.disconnect()

    async def test_connect_invalid_draft(self):
        """Test connection to non-existent draft is rejected."""
        communicator = WebsocketCommunicator(
            self.get_application(),
            "/api/herodraft/99999/",
        )
        communicator.scope["user"] = self.spectator

        connected, close_code = await communicator.connect()
        # Connection should be rejected
        self.assertFalse(connected)

    async def test_captain_marked_connected_on_connect(self):
        """Test captain is marked connected when they join."""
        communicator = WebsocketCommunicator(
            self.get_application(),
            f"/api/herodraft/{self.draft.id}/",
        )
        communicator.scope["user"] = self.captain1

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Receive initial state
        await communicator.receive_json_from()

        # Check captain is marked connected
        @database_sync_to_async
        def check_connected():
            self.draft_team1.refresh_from_db()
            return self.draft_team1.is_connected

        is_connected = await check_connected()
        self.assertTrue(is_connected)

        await communicator.disconnect()

    async def test_captain_marked_disconnected_on_disconnect(self):
        """Test captain is marked disconnected when they leave."""
        communicator = WebsocketCommunicator(
            self.get_application(),
            f"/api/herodraft/{self.draft.id}/",
        )
        communicator.scope["user"] = self.captain1

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Receive initial state
        await communicator.receive_json_from()

        # Disconnect
        await communicator.disconnect()

        # Check captain is marked disconnected
        @database_sync_to_async
        def check_disconnected():
            self.draft_team1.refresh_from_db()
            return self.draft_team1.is_connected

        is_connected = await check_disconnected()
        self.assertFalse(is_connected)

    async def test_draft_paused_on_captain_disconnect_during_drafting(self):
        """Test draft is paused when captain disconnects during drafting."""

        # Set draft to drafting state
        @database_sync_to_async
        def set_drafting():
            self.draft.state = "drafting"
            self.draft.save()
            self.draft_team1.is_connected = True
            self.draft_team1.save()

        await set_drafting()

        communicator = WebsocketCommunicator(
            self.get_application(),
            f"/api/herodraft/{self.draft.id}/",
        )
        communicator.scope["user"] = self.captain1

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Receive initial state
        await communicator.receive_json_from()

        # Disconnect
        await communicator.disconnect()

        # Check draft is paused
        @database_sync_to_async
        def check_paused():
            self.draft.refresh_from_db()
            return self.draft.state

        state = await check_paused()
        self.assertEqual(state, "paused")

    async def test_spectator_does_not_affect_captain_status(self):
        """Test spectator connect/disconnect doesn't affect captain status."""
        # First connect captain
        captain_communicator = WebsocketCommunicator(
            self.get_application(),
            f"/api/herodraft/{self.draft.id}/",
        )
        captain_communicator.scope["user"] = self.captain1
        await captain_communicator.connect()
        await captain_communicator.receive_json_from()

        # Connect spectator
        spectator_communicator = WebsocketCommunicator(
            self.get_application(),
            f"/api/herodraft/{self.draft.id}/",
        )
        spectator_communicator.scope["user"] = self.spectator
        await spectator_communicator.connect()
        await spectator_communicator.receive_json_from()

        # Disconnect spectator
        await spectator_communicator.disconnect()

        # Captain should still be connected
        @database_sync_to_async
        def check_captain_connected():
            self.draft_team1.refresh_from_db()
            return self.draft_team1.is_connected

        is_connected = await check_captain_connected()
        self.assertTrue(is_connected)

        await captain_communicator.disconnect()

    async def test_herodraft_event_message_forwarded(self):
        """Test herodraft_event messages are forwarded to clients."""
        communicator = WebsocketCommunicator(
            self.get_application(),
            f"/api/herodraft/{self.draft.id}/",
        )
        communicator.scope["user"] = self.spectator

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Receive initial state
        await communicator.receive_json_from()

        # Send event through channel layer
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"herodraft_{self.draft.id}",
            {
                "type": "herodraft.event",
                "event_type": "hero_selected",
                "event_id": 123,
                "draft_team": self.draft_team1.id,
                "draft_state": {"id": self.draft.id, "state": "drafting"},
                "timestamp": "2024-01-01T00:00:00Z",
            },
        )

        # Receive event
        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "herodraft_event")
        self.assertEqual(response["event_type"], "hero_selected")
        self.assertEqual(response["draft_team"], self.draft_team1.id)

        await communicator.disconnect()

    async def test_herodraft_tick_message_forwarded(self):
        """Test herodraft_tick messages are forwarded to clients."""
        communicator = WebsocketCommunicator(
            self.get_application(),
            f"/api/herodraft/{self.draft.id}/",
        )
        communicator.scope["user"] = self.spectator

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Receive initial state
        await communicator.receive_json_from()

        # Send tick through channel layer
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

        # Receive tick
        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "herodraft_tick")
        self.assertEqual(response["current_round"], 1)
        self.assertEqual(response["active_team_id"], self.draft_team1.id)
        self.assertEqual(response["team_a_id"], self.draft_team1.id)
        self.assertEqual(response["team_b_id"], self.draft_team2.id)

        await communicator.disconnect()

    async def test_pause_resume_timing_adjustment(self):
        """Test that pause/resume adjusts round started_at correctly."""
        # Set up draft in drafting state with both captains connected
        original_started_at = timezone.now() - timedelta(seconds=10)

        @database_sync_to_async
        def setup_drafting_state():
            self.draft.state = HeroDraftState.DRAFTING
            self.draft.save()
            self.draft_team1.is_connected = True
            self.draft_team1.save()
            self.draft_team2.is_connected = True
            self.draft_team2.save()
            # Create an active round with started_at 10 seconds ago
            return HeroDraftRound.objects.create(
                draft=self.draft,
                draft_team=self.draft_team1,
                round_number=1,
                action_type="ban",
                state="active",
                started_at=original_started_at,
            )

        active_round = await setup_drafting_state()

        # Connect captain1
        captain1_communicator = WebsocketCommunicator(
            self.get_application(),
            f"/api/herodraft/{self.draft.id}/",
        )
        captain1_communicator.scope["user"] = self.captain1
        connected, _ = await captain1_communicator.connect()
        self.assertTrue(connected)
        await captain1_communicator.receive_json_from()  # initial state

        # Connect captain2
        captain2_communicator = WebsocketCommunicator(
            self.get_application(),
            f"/api/herodraft/{self.draft.id}/",
        )
        captain2_communicator.scope["user"] = self.captain2
        connected, _ = await captain2_communicator.connect()
        self.assertTrue(connected)
        await captain2_communicator.receive_json_from()  # initial state

        # Disconnect captain1 - this should trigger pause
        await captain1_communicator.disconnect()

        # Verify draft is paused and paused_at is set
        @database_sync_to_async
        def check_paused():
            self.draft.refresh_from_db()
            return self.draft.state, self.draft.paused_at

        state, paused_at = await check_paused()
        self.assertEqual(state, HeroDraftState.PAUSED)
        self.assertIsNotNone(paused_at)

        # Drain any messages from captain2's communicator
        try:
            while True:
                await asyncio.wait_for(
                    captain2_communicator.receive_json_from(), timeout=0.1
                )
        except asyncio.TimeoutError:
            pass

        # Simulate 2 seconds passing by adjusting paused_at backwards
        @database_sync_to_async
        def simulate_pause_duration():
            self.draft.refresh_from_db()
            self.draft.paused_at = timezone.now() - timedelta(seconds=2)
            self.draft.save()

        await simulate_pause_duration()

        # Verify captain2 is still connected before captain1 reconnects
        @database_sync_to_async
        def check_captain2_connected():
            self.draft_team2.refresh_from_db()
            return self.draft_team2.is_connected

        captain2_is_connected = await check_captain2_connected()
        self.assertTrue(
            captain2_is_connected, "Captain2 should still be connected before resume"
        )

        # Reconnect captain1 - this should trigger resume with timing adjustment
        captain1_reconnect = WebsocketCommunicator(
            self.get_application(),
            f"/api/herodraft/{self.draft.id}/",
        )
        captain1_reconnect.scope["user"] = self.captain1
        connected, _ = await captain1_reconnect.connect()
        self.assertTrue(connected)

        # Give some time for the resume to process
        await asyncio.sleep(0.2)

        # Verify timing adjustment: started_at should be moved forward by ~5 seconds
        # (2s pause duration + 3s countdown)
        @database_sync_to_async
        def check_timing_adjustment():
            self.draft.refresh_from_db()
            active_round.refresh_from_db()
            # Also check team connection status for debugging
            self.draft_team1.refresh_from_db()
            self.draft_team2.refresh_from_db()
            return (
                self.draft.state,
                active_round.started_at,
                self.draft_team1.is_connected,
                self.draft_team2.is_connected,
            )

        state, new_started_at, team1_connected, team2_connected = (
            await check_timing_adjustment()
        )
        self.assertTrue(team1_connected, "Captain1 should be connected after reconnect")
        self.assertTrue(team2_connected, "Captain2 should still be connected")
        self.assertEqual(state, HeroDraftState.DRAFTING)

        # Calculate expected adjustment: original + 5 seconds (2s pause + 3s countdown)
        expected_started_at = original_started_at + timedelta(seconds=5)
        time_difference = abs((new_started_at - expected_started_at).total_seconds())

        # Allow 1 second tolerance for timing variations
        self.assertLess(
            time_difference,
            1.0,
            f"started_at adjustment incorrect. Expected ~{expected_started_at}, got {new_started_at}",
        )

        # Clean up
        await captain1_reconnect.disconnect()
        await captain2_communicator.disconnect()

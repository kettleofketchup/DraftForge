"""Tests for Team Draft WebSocket consumer (DraftConsumer)."""

import asyncio
import json
from datetime import date
from unittest.mock import patch

from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.urls import re_path

from app.consumers import DraftConsumer
from app.models import Draft, DraftEvent, DraftRound, Team, Tournament

User = get_user_model()


class DraftConsumerTestCase(TransactionTestCase):
    """Test cases for DraftConsumer WebSocket consumer."""

    def setUp(self):
        """Set up test fixtures."""
        self.captain1 = User.objects.create_user(
            username="draft_captain1",
            password="testpass123",
        )
        self.captain2 = User.objects.create_user(
            username="draft_captain2",
            password="testpass123",
        )
        self.spectator = User.objects.create_user(
            username="draft_spectator",
            password="testpass123",
        )
        self.player1 = User.objects.create_user(
            username="draft_player1",
            password="testpass123",
        )

        # Create tournament with draft
        self.tournament = Tournament.objects.create(
            name="Draft Consumer Test Tournament",
            date_played=date.today(),
        )
        self.tournament.users.add(
            self.captain1, self.captain2, self.player1, self.spectator
        )

        self.team1 = Team.objects.create(
            tournament=self.tournament,
            name="Draft Test Team 1",
            captain=self.captain1,
            draft_order=1,
        )
        self.team2 = Team.objects.create(
            tournament=self.tournament,
            name="Draft Test Team 2",
            captain=self.captain2,
            draft_order=2,
        )

        self.draft = Draft.objects.create(
            tournament=self.tournament,
            draft_style="snake",
        )

    def get_application(self):
        """Get the test ASGI application."""
        return URLRouter(
            [
                re_path(
                    r"api/draft/(?P<draft_id>\d+)/$",
                    DraftConsumer.as_asgi(),
                ),
            ]
        )

    async def connect_to_draft(self, draft_id=None, user=None):
        """Helper: connect to a draft and return communicator + initial response."""
        if draft_id is None:
            draft_id = self.draft.pk
        communicator = WebsocketCommunicator(
            self.get_application(),
            f"/api/draft/{draft_id}/",
        )
        if user:
            communicator.scope["user"] = user
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        response = await asyncio.wait_for(communicator.receive_json_from(), timeout=5)
        return communicator, response

    # =========================================================================
    # Connection Tests
    # =========================================================================

    async def test_connect_valid_draft(self):
        """WebSocket connects and receives initial_events with draft_state."""
        communicator, response = await self.connect_to_draft(user=self.spectator)

        self.assertEqual(response["type"], "initial_events")
        self.assertIn("events", response)
        self.assertIn("draft_state", response)

        await communicator.disconnect()

    async def test_connect_invalid_draft(self):
        """Rejects connection for non-existent draft IDs."""
        communicator = WebsocketCommunicator(
            self.get_application(),
            "/api/draft/99999/",
        )
        communicator.scope["user"] = self.spectator

        connected, close_code = await communicator.connect()
        self.assertFalse(connected)

    async def test_connect_without_user(self):
        """Connection works without authenticated user (spectator mode)."""
        communicator = WebsocketCommunicator(
            self.get_application(),
            f"/api/draft/{self.draft.pk}/",
        )
        # No user set in scope

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "initial_events")

        await communicator.disconnect()

    # =========================================================================
    # Initial Events Tests
    # =========================================================================

    async def test_initial_events_contain_draft_state(self):
        """draft_state in initial_events has tournament and draft info."""
        communicator, response = await self.connect_to_draft(user=self.spectator)

        draft_state = response["draft_state"]
        self.assertIsNotNone(draft_state)
        self.assertEqual(draft_state["pk"], self.draft.pk)

        await communicator.disconnect()

    async def test_initial_events_include_existing_events(self):
        """initial_events contains previously created draft events."""

        @database_sync_to_async
        def create_events():
            DraftEvent.objects.create(
                draft=self.draft,
                event_type="draft_started",
                payload={"captain_count": 2},
            )
            DraftEvent.objects.create(
                draft=self.draft,
                event_type="captain_assigned",
                payload={
                    "captain_name": "draft_captain1",
                    "team_name": "Draft Test Team 1",
                },
            )

        await create_events()

        communicator, response = await self.connect_to_draft(user=self.spectator)

        events = response["events"]
        self.assertEqual(len(events), 2)

        await communicator.disconnect()

    async def test_draft_state_has_users_dict(self):
        """_users dict present in draft_state for frontend cache hydration."""
        communicator, response = await self.connect_to_draft(user=self.spectator)

        draft_state = response["draft_state"]
        self.assertIn("_users", draft_state)
        self.assertIsInstance(draft_state["_users"], dict)

        await communicator.disconnect()

    async def test_draft_state_has_draft_rounds(self):
        """draft_state includes draft_rounds array."""

        @database_sync_to_async
        def create_round():
            DraftRound.objects.create(
                draft=self.draft,
                captain=self.captain1,
                pick_number=1,
            )

        await create_round()

        communicator, response = await self.connect_to_draft(user=self.spectator)

        draft_state = response["draft_state"]
        self.assertIn("draft_rounds", draft_state)
        self.assertEqual(len(draft_state["draft_rounds"]), 1)

        await communicator.disconnect()

    # =========================================================================
    # Event Forwarding Tests
    # =========================================================================

    async def test_draft_event_forwarded(self):
        """Channel layer draft.event message reaches connected client."""
        communicator, _ = await self.connect_to_draft(user=self.spectator)

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"draft_{self.draft.pk}",
            {
                "type": "draft.event",
                "payload": {
                    "event_type": "player_picked",
                    "captain_name": "draft_captain1",
                    "picked_name": "draft_player1",
                    "pick_number": 1,
                },
            },
        )

        response = await asyncio.wait_for(communicator.receive_json_from(), timeout=5)
        self.assertEqual(response["type"], "draft_event")
        self.assertEqual(response["event"]["event_type"], "player_picked")
        self.assertEqual(response["event"]["captain_name"], "draft_captain1")
        self.assertEqual(response["event"]["picked_name"], "draft_player1")

        await communicator.disconnect()

    async def test_draft_state_in_forwarded_event(self):
        """Forwarded events include updated draft_state when present."""
        communicator, _ = await self.connect_to_draft(user=self.spectator)

        channel_layer = get_channel_layer()
        mock_state = {"id": self.draft.pk, "draft_style": "snake"}
        await channel_layer.group_send(
            f"draft_{self.draft.pk}",
            {
                "type": "draft.event",
                "payload": {"event_type": "player_picked"},
                "draft_state": mock_state,
            },
        )

        response = await asyncio.wait_for(communicator.receive_json_from(), timeout=5)
        self.assertEqual(response["type"], "draft_event")
        self.assertIn("draft_state", response)
        self.assertEqual(response["draft_state"]["id"], self.draft.pk)

        await communicator.disconnect()

    async def test_event_without_draft_state(self):
        """Events without draft_state don't include that field."""
        communicator, _ = await self.connect_to_draft(user=self.spectator)

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"draft_{self.draft.pk}",
            {
                "type": "draft.event",
                "payload": {"event_type": "draft_started"},
                # No draft_state field
            },
        )

        response = await asyncio.wait_for(communicator.receive_json_from(), timeout=5)
        self.assertEqual(response["type"], "draft_event")
        self.assertNotIn("draft_state", response)

        await communicator.disconnect()

    # =========================================================================
    # Disconnect Tests
    # =========================================================================

    async def test_disconnect_clean(self):
        """No errors on clean disconnect."""
        communicator, _ = await self.connect_to_draft(user=self.spectator)
        await communicator.disconnect()
        # No exception = pass

    async def test_force_disconnect(self):
        """force_disconnect handler closes connection with code 1012."""
        communicator, _ = await self.connect_to_draft(user=self.spectator)

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"draft_{self.draft.pk}",
            {"type": "force.disconnect"},
        )

        # Connection should close
        response = await communicator.receive_output(timeout=5)
        self.assertEqual(response["type"], "websocket.close")
        self.assertEqual(response.get("code", 1000), 1012)

    async def test_read_only_ignores_incoming_messages(self):
        """Consumer ignores incoming messages (read-only WS)."""
        communicator, _ = await self.connect_to_draft(user=self.spectator)

        # Send a message — should be silently ignored
        await communicator.send_json_to({"type": "some_action", "data": "test"})

        # Verify no response (would timeout if nothing sent)
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(communicator.receive_json_from(), timeout=0.5)

        await communicator.disconnect()

    # =========================================================================
    # Multiple Clients Tests
    # =========================================================================

    async def test_multiple_spectators_receive_events(self):
        """Multiple connected clients all receive the same broadcast events."""
        comm1, _ = await self.connect_to_draft(user=self.spectator)
        comm2, _ = await self.connect_to_draft(user=self.captain1)

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"draft_{self.draft.pk}",
            {
                "type": "draft.event",
                "payload": {"event_type": "draft_started"},
            },
        )

        response1 = await asyncio.wait_for(comm1.receive_json_from(), timeout=5)
        response2 = await asyncio.wait_for(comm2.receive_json_from(), timeout=5)

        self.assertEqual(response1["type"], "draft_event")
        self.assertEqual(response2["type"], "draft_event")
        self.assertEqual(
            response1["event"]["event_type"],
            response2["event"]["event_type"],
        )

        await comm1.disconnect()
        await comm2.disconnect()

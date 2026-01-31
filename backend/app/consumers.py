"""
WebSocket consumers for draft event broadcasting.
"""

import json
import logging
import time
from datetime import timedelta

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from telemetry.websocket import TelemetryConsumerMixin

log = logging.getLogger(__name__)


class DraftConsumer(TelemetryConsumerMixin, AsyncWebsocketConsumer):
    """WebSocket consumer for draft-specific events."""

    async def connect(self):
        await self.telemetry_connect()
        self.draft_id = self.scope["url_route"]["kwargs"]["draft_id"]
        self.room_group_name = f"draft_{self.draft_id}"

        # Validate draft exists
        draft_exists = await self.draft_exists(self.draft_id)
        if not draft_exists:
            await self.close()
            return

        # Join draft group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Send recent events and current draft state on connect
        recent_events = await self.get_recent_events(self.draft_id)
        draft_state = await self.get_draft_state(self.draft_id)
        await self.send(
            text_data=json.dumps(
                {
                    "type": "initial_events",
                    "events": recent_events,
                    "draft_state": draft_state,
                }
            )
        )

    async def disconnect(self, close_code):
        await self.telemetry_disconnect(close_code)
        # Leave draft group
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        # Read-only WebSocket - ignore incoming messages
        pass

    async def draft_event(self, event):
        """Handle draft.event messages from channel layer."""
        message = {
            "type": "draft_event",
            "event": event["payload"],
        }
        # Include draft state if available (allows clients to update without API calls)
        if "draft_state" in event:
            message["draft_state"] = event["draft_state"]
        await self.send(text_data=json.dumps(message))

    @database_sync_to_async
    def draft_exists(self, draft_id):
        from app.models import Draft

        return Draft.objects.filter(pk=draft_id).exists()

    @database_sync_to_async
    def get_recent_events(self, draft_id, limit=20):
        from app.models import DraftEvent
        from app.serializers import DraftEventSerializer

        events = DraftEvent.objects.filter(draft_id=draft_id)[:limit]
        return DraftEventSerializer(events, many=True).data

    @database_sync_to_async
    def get_draft_state(self, draft_id):
        from app.models import Draft
        from app.serializers import DraftSerializerForTournament

        try:
            # Note: users_remaining is a property, not a relation, so it can't be prefetched
            draft = Draft.objects.prefetch_related(
                "draft_rounds__captain",
                "draft_rounds__choice",
                "tournament__teams__captain",
                "tournament__teams__members",
                "tournament__users",  # Prefetch users for users_remaining calculation
            ).get(pk=draft_id)
            return DraftSerializerForTournament(draft).data
        except Draft.DoesNotExist:
            return None


class TournamentConsumer(TelemetryConsumerMixin, AsyncWebsocketConsumer):
    """WebSocket consumer for tournament-wide events."""

    async def connect(self):
        await self.telemetry_connect()
        self.tournament_id = self.scope["url_route"]["kwargs"]["tournament_id"]
        self.room_group_name = f"tournament_{self.tournament_id}"

        # Validate tournament exists
        tournament_exists = await self.tournament_exists(self.tournament_id)
        if not tournament_exists:
            await self.close()
            return

        # Join tournament group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Send recent events on connect
        recent_events = await self.get_recent_events(self.tournament_id)
        await self.send(
            text_data=json.dumps(
                {
                    "type": "initial_events",
                    "events": recent_events,
                }
            )
        )

    async def disconnect(self, close_code):
        await self.telemetry_disconnect(close_code)
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        # Read-only WebSocket - ignore incoming messages
        pass

    async def draft_event(self, event):
        """Handle draft.event messages from channel layer."""
        message = {
            "type": "draft_event",
            "event": event["payload"],
        }
        # Include draft state if available (allows clients to update without API calls)
        if "draft_state" in event:
            message["draft_state"] = event["draft_state"]
        await self.send(text_data=json.dumps(message))

    @database_sync_to_async
    def tournament_exists(self, tournament_id):
        from app.models import Tournament

        return Tournament.objects.filter(pk=tournament_id).exists()

    @database_sync_to_async
    def get_recent_events(self, tournament_id, limit=20):
        from app.models import Draft, DraftEvent
        from app.serializers import DraftEventSerializer

        # Get events from the tournament's draft
        try:
            draft = Draft.objects.get(tournament_id=tournament_id)
            events = DraftEvent.objects.filter(draft=draft)[:limit]
            return DraftEventSerializer(events, many=True).data
        except Draft.DoesNotExist:
            return []


class HeroDraftConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for Captain's Mode hero draft."""

    # Redis key patterns for captain connection tracking
    CAPTAIN_CHANNEL_KEY = "herodraft:{draft_id}:captain:{user_id}:channel"
    CAPTAIN_HEARTBEAT_KEY = "herodraft:{draft_id}:captain:{user_id}:heartbeat"

    async def connect(self):
        self.draft_id = self.scope["url_route"]["kwargs"]["draft_id"]
        self.room_group_name = f"herodraft_{self.draft_id}"
        self.user = self.scope.get("user")
        self._connection_tracked = False
        self._is_captain = False

        # Verify draft exists
        draft_exists = await self.draft_exists(self.draft_id)
        if not draft_exists:
            log.warning(f"HeroDraft {self.draft_id} not found, closing connection")
            await self.close()
            return

        # Check if this user is a captain and kick any existing connection
        if self.user and self.user.is_authenticated:
            is_captain = await self.check_is_captain(self.draft_id, self.user)
            if is_captain:
                self._is_captain = True
                await self.kick_existing_captain_connection()

        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Track connection count for tick broadcaster
        await self.track_connection(True)

        # Register captain's channel for future kick detection
        if self._is_captain:
            await self.register_captain_channel()

        # Send initial state
        try:
            initial_state = await self.get_draft_state(self.draft_id)
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "initial_state",
                        "draft_state": initial_state,
                    }
                )
            )

            # Start tick broadcaster if draft is in drafting state
            # Compare against enum value since initial_state is serialized JSON
            from app.models import HeroDraftState

            if initial_state.get("state") == HeroDraftState.DRAFTING.value:
                await self.maybe_start_tick_broadcaster()

        except Exception as e:
            log.error(
                f"Failed to send initial state for herodraft {self.draft_id}: {e}"
            )
            await self.close()
            return

        # Mark captain as connected if authenticated
        if self.user and self.user.is_authenticated:
            await self.mark_captain_connected(self.draft_id, self.user, True)

    async def disconnect(self, close_code):
        # Track disconnection
        if hasattr(self, "_connection_tracked") and self._connection_tracked:
            await self.track_connection(False)

        # If this connection was kicked by a new connection, don't mark as disconnected
        # The new connection is already active and has marked the captain as connected
        was_kicked = getattr(self, "_was_kicked", False)
        if was_kicked:
            log.info(
                f"Skipping disconnect handling for kicked connection "
                f"(user {getattr(self, 'user', None)}, draft {getattr(self, 'draft_id', None)})"
            )
            # Still leave the room group
            if hasattr(self, "room_group_name"):
                await self.channel_layer.group_discard(
                    self.room_group_name, self.channel_name
                )
            return

        # Clean up captain channel registration and mark as disconnected
        if (
            hasattr(self, "user")
            and hasattr(self, "draft_id")
            and self.user
            and self.user.is_authenticated
        ):
            try:
                # Only clean up if this is still the registered channel
                # (prevents race condition where new connection already registered)
                if hasattr(self, "_is_captain") and self._is_captain:
                    await self.unregister_captain_channel_if_current()
                await self.mark_captain_connected(self.draft_id, self.user, False)
            except Exception as e:
                log.error(
                    f"Failed to mark captain disconnected for herodraft {self.draft_id}: {e}"
                )

        # Leave room group
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name, self.channel_name
            )

    @database_sync_to_async
    def track_connection(self, is_connecting: bool):
        """Track WebSocket connection count in Redis."""
        from app.tasks.herodraft_tick import (
            decrement_connection_count,
            increment_connection_count,
        )

        try:
            if is_connecting:
                increment_connection_count(self.draft_id)
                self._connection_tracked = True
            else:
                decrement_connection_count(self.draft_id)
                self._connection_tracked = False
        except Exception as e:
            log.warning(f"Failed to track connection for draft {self.draft_id}: {e}")

    @database_sync_to_async
    def maybe_start_tick_broadcaster(self):
        """Start tick broadcaster if not already running."""
        from app.tasks.herodraft_tick import start_tick_broadcaster

        try:
            start_tick_broadcaster(self.draft_id)
        except Exception as e:
            log.warning(
                f"Failed to start tick broadcaster for draft {self.draft_id}: {e}"
            )

    @database_sync_to_async
    def check_is_captain(self, draft_id, user):
        """Check if user is a captain for this draft."""
        from app.models import HeroDraft

        try:
            draft = HeroDraft.objects.get(id=draft_id)
            return draft.draft_teams.filter(tournament_team__captain=user).exists()
        except HeroDraft.DoesNotExist:
            return False

    async def kick_existing_captain_connection(self):
        """Kick any existing WebSocket connection for this captain."""
        from app.tasks.herodraft_tick import get_redis_client

        r = get_redis_client()
        channel_key = self.CAPTAIN_CHANNEL_KEY.format(
            draft_id=self.draft_id, user_id=self.user.id
        )

        old_channel = r.get(channel_key)
        log.info(
            f"[KICK DEBUG] Checking kick for user {self.user.id} in draft {self.draft_id}: "
            f"old_channel={old_channel!r}, new_channel={self.channel_name!r}"
        )
        if old_channel and old_channel != self.channel_name:
            log.info(
                f"Kicking existing captain connection for user {self.user.id} "
                f"in draft {self.draft_id}: {old_channel} -> {self.channel_name}"
            )
            # Send kick message to old connection
            try:
                await self.channel_layer.send(
                    old_channel,
                    {"type": "herodraft.kicked", "reason": "new_connection"},
                )
                log.info(f"[KICK DEBUG] Sent kick message to {old_channel}")
            except Exception as e:
                log.warning(f"Failed to send kick message to {old_channel}: {e}")
        else:
            log.info(f"[KICK DEBUG] No kick needed - old_channel={old_channel!r}")

    async def register_captain_channel(self):
        """Register this connection as the captain's active channel."""
        from app.tasks.herodraft_tick import get_redis_client

        r = get_redis_client()
        channel_key = self.CAPTAIN_CHANNEL_KEY.format(
            draft_id=self.draft_id, user_id=self.user.id
        )
        # Store channel name with expiry (cleaned up if server crashes)
        r.set(channel_key, self.channel_name, ex=300)
        # Initialize heartbeat
        await self.update_captain_heartbeat()
        log.debug(
            f"Registered captain channel for user {self.user.id} "
            f"in draft {self.draft_id}: {self.channel_name}"
        )

    async def unregister_captain_channel_if_current(self):
        """Unregister captain channel only if it's still this connection."""
        from app.tasks.herodraft_tick import get_redis_client

        r = get_redis_client()
        channel_key = self.CAPTAIN_CHANNEL_KEY.format(
            draft_id=self.draft_id, user_id=self.user.id
        )
        heartbeat_key = self.CAPTAIN_HEARTBEAT_KEY.format(
            draft_id=self.draft_id, user_id=self.user.id
        )

        current_channel = r.get(channel_key)
        if current_channel == self.channel_name:
            r.delete(channel_key)
            r.delete(heartbeat_key)
            log.debug(
                f"Unregistered captain channel for user {self.user.id} "
                f"in draft {self.draft_id}"
            )

    async def update_captain_heartbeat(self):
        """Update the captain's heartbeat timestamp."""
        from app.tasks.herodraft_tick import get_redis_client

        r = get_redis_client()
        heartbeat_key = self.CAPTAIN_HEARTBEAT_KEY.format(
            draft_id=self.draft_id, user_id=self.user.id
        )
        # Store current timestamp with expiry
        r.set(heartbeat_key, str(time.time()), ex=30)

    async def herodraft_kicked(self, event):
        """Handle being kicked by a newer connection."""
        reason = event.get("reason", "unknown")
        log.info(f"Captain {self.user.id} kicked from draft {self.draft_id}: {reason}")
        # Mark this connection as kicked so disconnect() knows not to trigger
        # disconnect events (the new connection is already active)
        self._was_kicked = True
        await self.send(
            text_data=json.dumps(
                {
                    "type": "herodraft_kicked",
                    "reason": reason,
                }
            )
        )
        await self.close(code=4000)  # Custom close code for "kicked"

    async def receive(self, text_data):
        """Handle incoming WebSocket messages from clients."""
        if not self._is_captain:
            return  # Only process messages from captains

        try:
            data = json.loads(text_data)
            msg_type = data.get("type")

            if msg_type == "heartbeat":
                await self.update_captain_heartbeat()
        except json.JSONDecodeError:
            pass  # Ignore malformed messages

    async def herodraft_event(self, event):
        """Handle herodraft.event messages from channel layer."""
        # Build message with only fields that have actual values
        # Using .get() with missing keys returns None, which serializes to null
        # and fails Zod validation where .optional() expects undefined, not null
        message = {
            "type": "herodraft_event",
            "event_type": event.get("event_type"),
        }
        # Only include optional fields if they have values
        if "event_id" in event and event["event_id"] is not None:
            message["event_id"] = event["event_id"]
        if "draft_team" in event and event["draft_team"] is not None:
            message["draft_team"] = event["draft_team"]
        if "draft_state" in event and event["draft_state"] is not None:
            message["draft_state"] = event["draft_state"]
        if "timestamp" in event and event["timestamp"] is not None:
            message["timestamp"] = event["timestamp"]
        if "metadata" in event and event["metadata"] is not None:
            message["metadata"] = event["metadata"]

        await self.send(text_data=json.dumps(message))

    async def herodraft_tick(self, event):
        """Handle tick updates during active drafting."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "herodraft_tick",
                    "current_round": event.get("current_round"),
                    "active_team_id": event.get("active_team_id"),
                    "grace_time_remaining_ms": event.get("grace_time_remaining_ms"),
                    "team_a_id": event.get("team_a_id"),
                    "team_a_reserve_ms": event.get("team_a_reserve_ms"),
                    "team_b_id": event.get("team_b_id"),
                    "team_b_reserve_ms": event.get("team_b_reserve_ms"),
                    "draft_state": event.get("draft_state"),
                }
            )
        )

    @database_sync_to_async
    def draft_exists(self, draft_id):
        from app.models import HeroDraft

        return HeroDraft.objects.filter(id=draft_id).exists()

    @database_sync_to_async
    def get_draft_state(self, draft_id):
        from app.models import HeroDraft
        from app.serializers import HeroDraftSerializer

        draft = HeroDraft.objects.prefetch_related(
            "draft_teams__tournament_team__captain",
            "draft_teams__tournament_team__members",
            "rounds",
        ).get(id=draft_id)
        return HeroDraftSerializer(draft).data

    @database_sync_to_async
    def mark_captain_connected(self, draft_id, user, is_connected):
        from django.db import transaction

        from app.broadcast import broadcast_herodraft_state
        from app.models import DraftTeam, HeroDraft, HeroDraftEvent, HeroDraftState

        # Track what to do after transaction commits
        broadcast_event_type = None
        should_broadcast = False
        should_restart_tick_broadcaster = False

        try:
            with transaction.atomic():
                draft = HeroDraft.objects.select_for_update().get(id=draft_id)

                draft_team = draft.draft_teams.filter(
                    tournament_team__captain=user
                ).first()

                if draft_team:
                    draft_team.is_connected = is_connected
                    draft_team.save()

                    event_type = (
                        "captain_connected" if is_connected else "captain_disconnected"
                    )
                    HeroDraftEvent.objects.create(
                        draft=draft,
                        event_type=event_type,
                        draft_team=draft_team,
                        metadata={"user_id": user.id, "username": user.username},
                    )

                    # Handle pause/resume on disconnect - only during DRAFTING phase
                    # (when timers are running and picks matter)
                    # Ignore disconnects during RESUMING to prevent infinite time exploit
                    if not is_connected and draft.state == HeroDraftState.DRAFTING:
                        draft.state = HeroDraftState.PAUSED
                        draft.paused_at = timezone.now()
                        draft.save()
                        HeroDraftEvent.objects.create(
                            draft=draft,
                            event_type="draft_paused",
                            draft_team=draft_team,
                            metadata={"reason": "captain_disconnected"},
                        )
                        log.info(
                            f"HeroDraft {draft_id} paused: captain {user.username} disconnected"
                        )
                        broadcast_event_type = "draft_paused"
                        should_broadcast = True
                    elif is_connected and draft.state == HeroDraftState.PAUSED:
                        # All pauses require manual resume via the Resume button
                        # Just broadcast the connection status change
                        broadcast_event_type = event_type
                        should_broadcast = True
                    else:
                        # Always broadcast connection status changes so UI updates
                        broadcast_event_type = event_type
                        should_broadcast = True

        except HeroDraft.DoesNotExist:
            return

        # Broadcast AFTER transaction commits to ensure other connections see changes
        if should_broadcast and broadcast_event_type:
            try:
                # Re-fetch draft to get committed state
                draft = HeroDraft.objects.prefetch_related(
                    "draft_teams__tournament_team__captain",
                    "draft_teams__tournament_team__members",
                    "rounds",
                ).get(id=draft_id)
                # Get fresh draft_team from prefetched data (filter() bypasses prefetch cache)
                # Use DraftTeam.captain property which accesses tournament_team.captain
                fresh_draft_team = None
                for dt in draft.draft_teams.all():
                    # DraftTeam.captain property returns tournament_team.captain
                    if dt.captain and dt.captain.id == user.id:
                        fresh_draft_team = dt
                        break

                broadcast_herodraft_state(
                    draft, broadcast_event_type, draft_team=fresh_draft_team
                )
                log.debug(
                    f"HeroDraft {draft_id} broadcast {broadcast_event_type} after transaction commit"
                )
            except Exception as e:
                log.error(f"Failed to broadcast herodraft state: {e}")

        # Restart tick broadcaster AFTER transaction commits
        if should_restart_tick_broadcaster:
            from app.tasks.herodraft_tick import start_tick_broadcaster

            try:
                start_tick_broadcaster(draft_id)
                log.debug(f"HeroDraft {draft_id} tick broadcaster restarted")
            except Exception as e:
                log.warning(
                    f"Failed to restart tick broadcaster for draft {draft_id}: {e}"
                )

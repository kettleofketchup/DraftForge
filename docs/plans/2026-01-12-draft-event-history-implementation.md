# Draft Event History & WebSocket Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add real-time event history to shuffle draft with WebSocket notifications, displaying roll results and draft events to spectators.

**Architecture:** Django Channels for WebSocket support using existing Redis. DraftEvent model stores events, broadcast helper pushes to channel groups. Frontend FAB opens modal with event history, toasts for significant events, WebSocket triggers data refresh.

**Tech Stack:** Django Channels, channels-redis, React hooks, shadcn/ui components, Cypress for E2E testing

---

## Task 1: Add Django Channels Dependencies

**Files:**
- Modify: `/home/kettle/git_repos/website/.worktrees/draft-events/pyproject.toml`

**Step 1: Add channels and channels-redis to pyproject.toml**

Add to `[tool.poetry.dependencies]` section:
```toml
channels = "^4.0.0"
channels-redis = "^4.2.0"
daphne = "^4.0.0"
```

**Step 2: Install dependencies**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/draft-events
.venv/bin/poetry lock --no-update
.venv/bin/poetry install
```
Expected: Dependencies installed successfully

**Step 3: Commit**

```bash
git add pyproject.toml poetry.lock
git commit -m "feat: add Django Channels dependencies for WebSocket support"
```

---

## Task 2: Create DraftEvent Model

**Files:**
- Modify: `/home/kettle/git_repos/website/.worktrees/draft-events/backend/app/models.py`
- Create: `/home/kettle/git_repos/website/.worktrees/draft-events/backend/app/tests/test_draft_events.py`

**Step 1: Write the failing test**

Create test file with initial model test:

```python
# backend/app/tests/test_draft_events.py
from django.test import TestCase
from app.models import CustomUser, Draft, DraftEvent, PositionsModel, Team, Tournament
from datetime import date


class DraftEventModelTest(TestCase):
    def setUp(self):
        # Create positions for users
        self.positions = PositionsModel.objects.create()

        # Create test user
        self.user = CustomUser.objects.create_user(
            username="testcaptain",
            password="testpass",
            positions=self.positions,
        )
        self.user.mmr = 5000
        self.user.save()

        # Create tournament
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        self.tournament.users.add(self.user)

        # Create team
        self.team = Team.objects.create(
            name="Test Team",
            tournament=self.tournament,
            captain=self.user,
        )

        # Create draft
        self.draft = Draft.objects.create(
            tournament=self.tournament,
            draft_style="shuffle",
        )

    def test_create_draft_started_event(self):
        """Can create a draft_started event."""
        event = DraftEvent.objects.create(
            draft=self.draft,
            event_type="draft_started",
            payload={
                "draft_id": self.draft.pk,
                "draft_style": "shuffle",
                "team_count": 4,
            },
        )
        self.assertEqual(event.event_type, "draft_started")
        self.assertEqual(event.payload["draft_style"], "shuffle")
        self.assertIsNone(event.actor)

    def test_create_player_picked_event_with_actor(self):
        """Can create a player_picked event with actor."""
        event = DraftEvent.objects.create(
            draft=self.draft,
            event_type="player_picked",
            payload={
                "round": 1,
                "captain_id": self.user.pk,
                "captain_name": self.user.username,
                "picked_id": self.user.pk,
                "picked_name": "SomePlayer",
                "team_id": self.team.pk,
            },
            actor=self.user,
        )
        self.assertEqual(event.event_type, "player_picked")
        self.assertEqual(event.actor, self.user)

    def test_create_tie_roll_event(self):
        """Can create a tie_roll event with roll data."""
        event = DraftEvent.objects.create(
            draft=self.draft,
            event_type="tie_roll",
            payload={
                "tied_captains": [
                    {"id": 1, "name": "CaptainA", "mmr": 5000},
                    {"id": 2, "name": "CaptainB", "mmr": 5000},
                ],
                "roll_rounds": [
                    [{"captain_id": 1, "roll": 4}, {"captain_id": 2, "roll": 6}]
                ],
                "winner_id": 2,
                "winner_name": "CaptainB",
            },
        )
        self.assertEqual(event.event_type, "tie_roll")
        self.assertEqual(len(event.payload["tied_captains"]), 2)
        self.assertEqual(event.payload["winner_id"], 2)

    def test_events_ordered_by_created_at_desc(self):
        """Events are ordered newest first."""
        event1 = DraftEvent.objects.create(
            draft=self.draft,
            event_type="draft_started",
            payload={},
        )
        event2 = DraftEvent.objects.create(
            draft=self.draft,
            event_type="player_picked",
            payload={},
        )
        events = list(DraftEvent.objects.all())
        self.assertEqual(events[0], event2)
        self.assertEqual(events[1], event1)
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/draft-events/backend
DISABLE_CACHE=true ../.venv/bin/python manage.py test app.tests.test_draft_events -v 2
```
Expected: FAIL with "cannot import name 'DraftEvent' from 'app.models'"

**Step 3: Write minimal implementation**

Add to `backend/app/models.py` after the DraftRound class:

```python
class DraftEvent(models.Model):
    """Tracks draft lifecycle events for history and WebSocket broadcast."""

    EVENT_TYPE_CHOICES = [
        ("draft_started", "Draft Started"),
        ("draft_completed", "Draft Completed"),
        ("captain_assigned", "Captain Assigned"),
        ("player_picked", "Player Picked"),
        ("tie_roll", "Tie Roll"),
        ("pick_undone", "Pick Undone"),
    ]

    draft = models.ForeignKey(
        Draft,
        related_name="events",
        on_delete=models.CASCADE,
    )
    event_type = models.CharField(
        max_length=32,
        choices=EVENT_TYPE_CHOICES,
    )
    payload = models.JSONField(
        default=dict,
        help_text="Event-specific data (JSON)",
    )
    actor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="draft_events_triggered",
        help_text="User who triggered this event",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type} - Draft {self.draft_id} at {self.created_at}"
```

**Step 4: Create and run migration**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/draft-events/backend
DISABLE_CACHE=true ../.venv/bin/python manage.py makemigrations app --name draft_event_model
DISABLE_CACHE=true ../.venv/bin/python manage.py migrate
```
Expected: Migration created and applied

**Step 5: Run test to verify it passes**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/draft-events/backend
DISABLE_CACHE=true ../.venv/bin/python manage.py test app.tests.test_draft_events -v 2
```
Expected: All 4 tests PASS

**Step 6: Commit**

```bash
git add backend/app/models.py backend/app/migrations/ backend/app/tests/test_draft_events.py
git commit -m "feat: add DraftEvent model for draft history tracking"
```

---

## Task 3: Add DraftEvent Serializer

**Files:**
- Modify: `/home/kettle/git_repos/website/.worktrees/draft-events/backend/app/serializers.py`
- Modify: `/home/kettle/git_repos/website/.worktrees/draft-events/backend/app/tests/test_draft_events.py`

**Step 1: Write the failing test**

Add to `test_draft_events.py`:

```python
from app.serializers import DraftEventSerializer


class DraftEventSerializerTest(TestCase):
    def setUp(self):
        self.positions = PositionsModel.objects.create()
        self.user = CustomUser.objects.create_user(
            username="testcaptain",
            password="testpass",
            positions=self.positions,
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        self.draft = Draft.objects.create(
            tournament=self.tournament,
            draft_style="shuffle",
        )

    def test_serializer_contains_expected_fields(self):
        """Serializer includes all required fields."""
        event = DraftEvent.objects.create(
            draft=self.draft,
            event_type="player_picked",
            payload={"round": 1, "captain_name": "TestCaptain"},
            actor=self.user,
        )
        serializer = DraftEventSerializer(event)
        data = serializer.data

        self.assertIn("pk", data)
        self.assertIn("event_type", data)
        self.assertIn("payload", data)
        self.assertIn("actor", data)
        self.assertIn("created_at", data)
        self.assertEqual(data["event_type"], "player_picked")
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/draft-events/backend
DISABLE_CACHE=true ../.venv/bin/python manage.py test app.tests.test_draft_events.DraftEventSerializerTest -v 2
```
Expected: FAIL with "cannot import name 'DraftEventSerializer'"

**Step 3: Write minimal implementation**

Add to `backend/app/serializers.py`:

```python
from .models import DraftEvent

class DraftEventSerializer(serializers.ModelSerializer):
    actor = TournamentUserSerializer(read_only=True)

    class Meta:
        model = DraftEvent
        fields = (
            "pk",
            "event_type",
            "payload",
            "actor",
            "created_at",
        )
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/draft-events/backend
DISABLE_CACHE=true ../.venv/bin/python manage.py test app.tests.test_draft_events.DraftEventSerializerTest -v 2
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/serializers.py backend/app/tests/test_draft_events.py
git commit -m "feat: add DraftEventSerializer for API/WebSocket payloads"
```

---

## Task 4: Configure Django Channels

**Files:**
- Create: `/home/kettle/git_repos/website/.worktrees/draft-events/backend/backend/asgi.py`
- Modify: `/home/kettle/git_repos/website/.worktrees/draft-events/backend/backend/settings.py`

**Step 1: Create ASGI configuration**

Create `backend/backend/asgi.py`:

```python
"""
ASGI config for backend project.

Exposes the ASGI callable as a module-level variable named ``application``.
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

from app.routing import websocket_urlpatterns

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            URLRouter(websocket_urlpatterns)
        ),
    }
)
```

**Step 2: Add Channels to INSTALLED_APPS and configure channel layer**

Add to `backend/backend/settings.py`:

In INSTALLED_APPS, add `"channels"` and `"daphne"` at the beginning:
```python
INSTALLED_APPS = [
    "daphne",
    "channels",
    # ... rest of apps
]
```

Add ASGI_APPLICATION setting after WSGI_APPLICATION:
```python
ASGI_APPLICATION = "backend.asgi.application"
```

Add CHANNEL_LAYERS configuration after CACHEOPS_DEGRADE_ON_FAILURE:
```python
# Channel Layers for WebSocket support
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(REDIS_HOST, 6379)],
        },
    },
}
```

**Step 3: Create empty routing file (placeholder)**

Create `backend/app/routing.py`:

```python
"""
WebSocket URL routing for draft events.
"""

websocket_urlpatterns = []
```

**Step 4: Verify Django starts without errors**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/draft-events/backend
DISABLE_CACHE=true ../.venv/bin/python manage.py check
```
Expected: "System check identified no issues"

**Step 5: Commit**

```bash
git add backend/backend/asgi.py backend/backend/settings.py backend/app/routing.py
git commit -m "feat: configure Django Channels with Redis channel layer"
```

---

## Task 5: Create WebSocket Consumers

**Files:**
- Create: `/home/kettle/git_repos/website/.worktrees/draft-events/backend/app/consumers.py`
- Modify: `/home/kettle/git_repos/website/.worktrees/draft-events/backend/app/routing.py`

**Step 1: Create WebSocket consumers**

Create `backend/app/consumers.py`:

```python
"""
WebSocket consumers for draft event broadcasting.
"""

import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.exceptions import ObjectDoesNotExist

log = logging.getLogger(__name__)


class DraftConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for draft-specific events."""

    async def connect(self):
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

        # Send recent events on connect
        recent_events = await self.get_recent_events(self.draft_id)
        await self.send(
            text_data=json.dumps(
                {
                    "type": "initial_events",
                    "events": recent_events,
                }
            )
        )

    async def disconnect(self, close_code):
        # Leave draft group
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        # Read-only WebSocket - ignore incoming messages
        pass

    async def draft_event(self, event):
        """Handle draft.event messages from channel layer."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "draft_event",
                    "event": event["payload"],
                }
            )
        )

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


class TournamentConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for tournament-wide events."""

    async def connect(self):
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
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        # Read-only WebSocket - ignore incoming messages
        pass

    async def draft_event(self, event):
        """Handle draft.event messages from channel layer."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "draft_event",
                    "event": event["payload"],
                }
            )
        )

    @database_sync_to_async
    def tournament_exists(self, tournament_id):
        from app.models import Tournament

        return Tournament.objects.filter(pk=tournament_id).exists()

    @database_sync_to_async
    def get_recent_events(self, tournament_id, limit=20):
        from app.models import DraftEvent, Draft
        from app.serializers import DraftEventSerializer

        # Get events from the tournament's draft
        try:
            draft = Draft.objects.get(tournament_id=tournament_id)
            events = DraftEvent.objects.filter(draft=draft)[:limit]
            return DraftEventSerializer(events, many=True).data
        except Draft.DoesNotExist:
            return []
```

**Step 2: Update routing with WebSocket URLs**

Update `backend/app/routing.py`:

```python
"""
WebSocket URL routing for draft events.
"""

from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws/draft/<int:draft_id>/", consumers.DraftConsumer.as_asgi()),
    path("ws/tournament/<int:tournament_id>/", consumers.TournamentConsumer.as_asgi()),
]
```

**Step 3: Verify Django starts without errors**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/draft-events/backend
DISABLE_CACHE=true ../.venv/bin/python manage.py check
```
Expected: "System check identified no issues"

**Step 4: Commit**

```bash
git add backend/app/consumers.py backend/app/routing.py
git commit -m "feat: add WebSocket consumers for draft and tournament events"
```

---

## Task 6: Create Broadcast Helper

**Files:**
- Create: `/home/kettle/git_repos/website/.worktrees/draft-events/backend/app/broadcast.py`
- Modify: `/home/kettle/git_repos/website/.worktrees/draft-events/backend/app/tests/test_draft_events.py`

**Step 1: Write the failing test**

Add to `test_draft_events.py`:

```python
from unittest.mock import patch, MagicMock


class BroadcastEventTest(TestCase):
    def setUp(self):
        self.positions = PositionsModel.objects.create()
        self.user = CustomUser.objects.create_user(
            username="testcaptain",
            password="testpass",
            positions=self.positions,
        )
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        self.draft = Draft.objects.create(
            tournament=self.tournament,
            draft_style="shuffle",
        )

    @patch("app.broadcast.get_channel_layer")
    def test_broadcast_event_sends_to_draft_group(self, mock_get_channel_layer):
        """Broadcast sends event to draft channel group."""
        from app.broadcast import broadcast_event

        mock_channel_layer = MagicMock()
        mock_get_channel_layer.return_value = mock_channel_layer

        event = DraftEvent.objects.create(
            draft=self.draft,
            event_type="player_picked",
            payload={"round": 1},
        )

        broadcast_event(event)

        # Verify group_send was called for draft group
        calls = mock_channel_layer.group_send.call_args_list
        draft_call = [c for c in calls if f"draft_{self.draft.pk}" in str(c)]
        self.assertEqual(len(draft_call), 1)

    @patch("app.broadcast.get_channel_layer")
    def test_broadcast_event_sends_to_tournament_group(self, mock_get_channel_layer):
        """Broadcast sends event to tournament channel group."""
        from app.broadcast import broadcast_event

        mock_channel_layer = MagicMock()
        mock_get_channel_layer.return_value = mock_channel_layer

        event = DraftEvent.objects.create(
            draft=self.draft,
            event_type="player_picked",
            payload={"round": 1},
        )

        broadcast_event(event)

        # Verify group_send was called for tournament group
        calls = mock_channel_layer.group_send.call_args_list
        tournament_call = [c for c in calls if f"tournament_{self.tournament.pk}" in str(c)]
        self.assertEqual(len(tournament_call), 1)
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/draft-events/backend
DISABLE_CACHE=true ../.venv/bin/python manage.py test app.tests.test_draft_events.BroadcastEventTest -v 2
```
Expected: FAIL with "No module named 'app.broadcast'"

**Step 3: Write minimal implementation**

Create `backend/app/broadcast.py`:

```python
"""
Broadcast helper for sending draft events to WebSocket channel groups.
"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from app.serializers import DraftEventSerializer

log = logging.getLogger(__name__)


def broadcast_event(event):
    """
    Broadcast a DraftEvent to both draft-specific and tournament channel groups.

    Args:
        event: DraftEvent instance to broadcast
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        log.warning("No channel layer configured, skipping broadcast")
        return

    payload = DraftEventSerializer(event).data

    # Send to draft-specific channel
    async_to_sync(channel_layer.group_send)(
        f"draft_{event.draft_id}",
        {
            "type": "draft.event",
            "payload": payload,
        },
    )

    # Send to tournament channel
    tournament_id = event.draft.tournament_id
    async_to_sync(channel_layer.group_send)(
        f"tournament_{tournament_id}",
        {
            "type": "draft.event",
            "payload": payload,
        },
    )

    log.debug(
        f"Broadcast {event.event_type} to draft_{event.draft_id} and tournament_{tournament_id}"
    )
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/draft-events/backend
DISABLE_CACHE=true ../.venv/bin/python manage.py test app.tests.test_draft_events.BroadcastEventTest -v 2
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/broadcast.py backend/app/tests/test_draft_events.py
git commit -m "feat: add broadcast helper for WebSocket event distribution"
```

---

## Task 7: Integrate Events into Draft Functions

**Files:**
- Modify: `/home/kettle/git_repos/website/.worktrees/draft-events/backend/app/functions/shuffle_draft.py`
- Modify: `/home/kettle/git_repos/website/.worktrees/draft-events/backend/app/functions/tournament.py`
- Modify: `/home/kettle/git_repos/website/.worktrees/draft-events/backend/app/tests/test_draft_events.py`

**Step 1: Write the failing test for event creation in shuffle_draft**

Add to `test_draft_events.py`:

```python
class ShuffleDraftEventIntegrationTest(TestCase):
    def setUp(self):
        self.positions = PositionsModel.objects.create()

        # Create 4 captains with different MMRs
        self.captains = []
        for i in range(4):
            captain = CustomUser.objects.create_user(
                username=f"captain{i}",
                password="testpass",
                positions=PositionsModel.objects.create(),
            )
            captain.mmr = 5000 + (i * 100)  # 5000, 5100, 5200, 5300
            captain.save()
            self.captains.append(captain)

        # Create tournament
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        for captain in self.captains:
            self.tournament.users.add(captain)

        # Create teams
        self.teams = []
        for i, captain in enumerate(self.captains):
            team = Team.objects.create(
                name=f"Team {i}",
                tournament=self.tournament,
                captain=captain,
                draft_order=i,
            )
            team.members.add(captain)
            self.teams.append(team)

        # Create draft
        self.draft = Draft.objects.create(
            tournament=self.tournament,
            draft_style="shuffle",
        )

    def test_build_shuffle_rounds_creates_draft_started_event(self):
        """Building shuffle rounds creates a draft_started event."""
        from app.functions.shuffle_draft import build_shuffle_rounds

        build_shuffle_rounds(self.draft)

        events = DraftEvent.objects.filter(draft=self.draft, event_type="draft_started")
        self.assertEqual(events.count(), 1)
        event = events.first()
        self.assertEqual(event.payload["draft_style"], "shuffle")
        self.assertEqual(event.payload["team_count"], 4)

    def test_assign_next_shuffle_captain_creates_captain_assigned_event(self):
        """Assigning next captain creates a captain_assigned event."""
        from app.functions.shuffle_draft import build_shuffle_rounds, assign_next_shuffle_captain

        build_shuffle_rounds(self.draft)

        # Clear events from build to isolate test
        DraftEvent.objects.filter(draft=self.draft).delete()

        # Make a pick to trigger next captain assignment
        first_round = self.draft.draft_rounds.first()
        first_round.choice = self.captains[1]  # Pick someone
        first_round.save()

        assign_next_shuffle_captain(self.draft)

        events = DraftEvent.objects.filter(draft=self.draft, event_type="captain_assigned")
        self.assertEqual(events.count(), 1)
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/draft-events/backend
DISABLE_CACHE=true ../.venv/bin/python manage.py test app.tests.test_draft_events.ShuffleDraftEventIntegrationTest -v 2
```
Expected: FAIL with assertion error (no events created)

**Step 3: Implement event creation in shuffle_draft.py**

Read the current file first, then add event creation. Add imports at top:
```python
from app.models import DraftEvent
from app.broadcast import broadcast_event
```

In `build_shuffle_rounds()`, after creating rounds and before return, add:
```python
    # Create draft_started event
    event = DraftEvent.objects.create(
        draft=draft,
        event_type="draft_started",
        payload={
            "draft_id": draft.pk,
            "draft_style": draft.draft_style,
            "team_count": len(teams),
        },
    )
    broadcast_event(event)
```

In `assign_next_shuffle_captain()`, after assigning captain to next_round and saving, add:
```python
    # Create captain_assigned event
    event = DraftEvent.objects.create(
        draft=draft,
        event_type="captain_assigned",
        payload={
            "round": next_round.pick_number,
            "captain_id": next_team.captain.pk,
            "captain_name": next_team.captain.username,
            "team_id": next_team.pk,
            "was_tie": bool(tie_data),
        },
    )
    broadcast_event(event)

    # If there was a tie, also create a tie_roll event
    if tie_data:
        tie_event = DraftEvent.objects.create(
            draft=draft,
            event_type="tie_roll",
            payload={
                "tied_captains": [
                    {"id": t.captain.pk, "name": t.captain.username, "mmr": get_team_total_mmr(t)}
                    for t in [Team.objects.get(pk=td["id"]) for td in tie_data["tied_teams"]]
                ],
                "roll_rounds": tie_data["roll_rounds"],
                "winner_id": tie_data["winner_id"],
                "winner_name": next_team.captain.username,
            },
        )
        broadcast_event(tie_event)
```

**Step 4: Run test to verify it passes**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/draft-events/backend
DISABLE_CACHE=true ../.venv/bin/python manage.py test app.tests.test_draft_events.ShuffleDraftEventIntegrationTest -v 2
```
Expected: PASS

**Step 5: Write test for tournament.py integration**

Add to `test_draft_events.py`:

```python
class TournamentEventIntegrationTest(TestCase):
    def setUp(self):
        # Same setup as ShuffleDraftEventIntegrationTest
        self.positions = PositionsModel.objects.create()

        self.captains = []
        self.players = []
        for i in range(4):
            captain = CustomUser.objects.create_user(
                username=f"captain{i}",
                password="testpass",
                positions=PositionsModel.objects.create(),
            )
            captain.mmr = 5000 + (i * 100)
            captain.save()
            self.captains.append(captain)

        # Create extra players to pick
        for i in range(16):
            player = CustomUser.objects.create_user(
                username=f"player{i}",
                password="testpass",
                positions=PositionsModel.objects.create(),
            )
            player.mmr = 4000 + (i * 50)
            player.save()
            self.players.append(player)

        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            date_played=date.today(),
        )
        for captain in self.captains:
            self.tournament.users.add(captain)
        for player in self.players:
            self.tournament.users.add(player)

        self.teams = []
        for i, captain in enumerate(self.captains):
            team = Team.objects.create(
                name=f"Team {i}",
                tournament=self.tournament,
                captain=captain,
                draft_order=i,
            )
            team.members.add(captain)
            self.teams.append(team)

        self.draft = Draft.objects.create(
            tournament=self.tournament,
            draft_style="shuffle",
        )

        # Build rounds
        from app.functions.shuffle_draft import build_shuffle_rounds
        build_shuffle_rounds(self.draft)

    def test_pick_player_creates_player_picked_event(self):
        """Picking a player creates a player_picked event."""
        # Clear existing events
        DraftEvent.objects.filter(draft=self.draft).delete()

        first_round = self.draft.draft_rounds.first()
        player_to_pick = self.players[0]

        first_round.pick_player(player_to_pick)

        events = DraftEvent.objects.filter(draft=self.draft, event_type="player_picked")
        self.assertEqual(events.count(), 1)
        event = events.first()
        self.assertEqual(event.payload["picked_name"], player_to_pick.username)
```

**Step 6: Implement event creation in tournament.py pick_player_for_round**

In `backend/app/functions/tournament.py`, add imports at top:
```python
from app.models import DraftEvent
from app.broadcast import broadcast_event
```

In `pick_player_for_round()`, after successful pick (after `draft_round.pick_player(user)`), add:
```python
    # Create player_picked event
    event = DraftEvent.objects.create(
        draft=draft_round.draft,
        event_type="player_picked",
        payload={
            "round": draft_round.pick_number,
            "captain_id": draft_round.captain.pk if draft_round.captain else None,
            "captain_name": draft_round.captain.username if draft_round.captain else "Unknown",
            "picked_id": user.pk,
            "picked_name": user.username,
            "team_id": draft_round.team.pk if draft_round.team else None,
        },
        actor=request.user,
    )
    broadcast_event(event)
```

In `undo_pick()`, add after successful undo:
```python
    # Create pick_undone event
    event = DraftEvent.objects.create(
        draft=draft,
        event_type="pick_undone",
        payload={
            "round": last_round.pick_number,
            "captain_name": last_round.captain.username if last_round.captain else "Unknown",
            "picked_name": undone_user.username,
        },
        actor=request.user,
    )
    broadcast_event(event)
```

**Step 7: Run all event tests**

Run:
```bash
cd /home/kettle/git_repos/website/.worktrees/draft-events/backend
DISABLE_CACHE=true ../.venv/bin/python manage.py test app.tests.test_draft_events -v 2
```
Expected: All tests PASS

**Step 8: Commit**

```bash
git add backend/app/functions/shuffle_draft.py backend/app/functions/tournament.py backend/app/tests/test_draft_events.py
git commit -m "feat: integrate DraftEvent creation into draft functions with broadcast"
```

---

## Task 8: Update Nginx Configuration for WebSocket

**Files:**
- Modify: `/home/kettle/git_repos/website/.worktrees/draft-events/nginx/default.template.conf`

**Step 1: Update nginx config for backend WebSocket routing**

Change the existing `/ws` location block (around line 111) from:
```nginx
    location /ws {
        proxy_pass http://frontend_server;
        ...
    }
```

To route `/ws/draft/` and `/ws/tournament/` to backend:
```nginx
    location /ws/draft/ {
        proxy_pass http://backend_server;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;
    }

    location /ws/tournament/ {
        proxy_pass http://backend_server;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;
    }

    # Keep frontend /ws for HMR
    location /ws {
        proxy_pass http://frontend_server;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 360s;
    }
```

**Step 2: Commit**

```bash
git add nginx/default.template.conf
git commit -m "feat: add nginx WebSocket proxy for draft and tournament channels"
```

---

## Task 9: Update Backend Dockerfile for Daphne

**Files:**
- Modify: `/home/kettle/git_repos/website/.worktrees/draft-events/backend/Dockerfile`

**Step 1: Update Dockerfile entrypoint to use Daphne**

Change the ENTRYPOINT lines in both runtime stages from:
```dockerfile
ENTRYPOINT ["python", "backend/manage.py", "runserver", "0.0.0.0:8000"]
```

To:
```dockerfile
ENTRYPOINT ["daphne", "-b", "0.0.0.0", "-p", "8000", "backend.asgi:application"]
```

**Step 2: Commit**

```bash
git add backend/Dockerfile
git commit -m "feat: switch backend from runserver to Daphne ASGI server"
```

---

## Task 10: Create Frontend Types for Draft Events

**Files:**
- Create: `/home/kettle/git_repos/website/.worktrees/draft-events/frontend/app/types/draftEvent.ts`

**Step 1: Create TypeScript types**

Create `frontend/app/types/draftEvent.ts`:

```typescript
export type DraftEventType =
  | "draft_started"
  | "draft_completed"
  | "captain_assigned"
  | "player_picked"
  | "tie_roll"
  | "pick_undone";

export interface DraftEvent {
  pk: number;
  event_type: DraftEventType;
  payload: DraftEventPayload;
  actor: {
    pk: number;
    username: string;
    avatarUrl: string | null;
  } | null;
  created_at: string;
}

export type DraftEventPayload =
  | DraftStartedPayload
  | DraftCompletedPayload
  | CaptainAssignedPayload
  | PlayerPickedPayload
  | TieRollPayload
  | PickUndonePayload;

export interface DraftStartedPayload {
  draft_id: number;
  draft_style: string;
  team_count: number;
}

export interface DraftCompletedPayload {
  draft_id: number;
  draft_style: string;
  team_count: number;
}

export interface CaptainAssignedPayload {
  round: number;
  captain_id: number;
  captain_name: string;
  team_id: number;
  was_tie: boolean;
}

export interface PlayerPickedPayload {
  round: number;
  captain_id: number;
  captain_name: string;
  picked_id: number;
  picked_name: string;
  team_id: number;
}

export interface TieRollPayload {
  tied_captains: {
    id: number;
    name: string;
    mmr: number;
  }[];
  roll_rounds: {
    captain_id: number;
    roll: number;
  }[][];
  winner_id: number;
  winner_name: string;
}

export interface PickUndonePayload {
  round: number;
  captain_name: string;
  picked_name: string;
}

export interface WebSocketMessage {
  type: "initial_events" | "draft_event";
  events?: DraftEvent[];
  event?: DraftEvent;
}
```

**Step 2: Commit**

```bash
git add frontend/app/types/draftEvent.ts
git commit -m "feat: add TypeScript types for draft events and WebSocket messages"
```

---

## Task 11: Create useDraftWebSocket Hook

**Files:**
- Create: `/home/kettle/git_repos/website/.worktrees/draft-events/frontend/app/components/draft/hooks/useDraftWebSocket.ts`

**Step 1: Create the WebSocket hook**

Create `frontend/app/components/draft/hooks/useDraftWebSocket.ts`:

```typescript
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import type { DraftEvent, WebSocketMessage } from "~/types/draftEvent";
import { getLogger } from "~/lib/logger";

const log = getLogger("useDraftWebSocket");

interface UseDraftWebSocketOptions {
  draftId: number | null;
  onEvent?: (event: DraftEvent) => void;
  onRefreshNeeded?: () => void;
}

interface UseDraftWebSocketReturn {
  events: DraftEvent[];
  isConnected: boolean;
  connectionError: string | null;
  hasNewEvent: boolean;
  clearNewEventFlag: () => void;
}

const SIGNIFICANT_EVENTS: DraftEvent["event_type"][] = [
  "draft_started",
  "draft_completed",
  "player_picked",
  "tie_roll",
];

function getEventMessage(event: DraftEvent): string {
  switch (event.event_type) {
    case "draft_started":
      return "Draft has started!";
    case "draft_completed":
      return "Draft completed!";
    case "player_picked": {
      const payload = event.payload as { captain_name: string; picked_name: string; round: number };
      return `${payload.captain_name} picked ${payload.picked_name} (Round ${payload.round})`;
    }
    case "tie_roll": {
      const payload = event.payload as { winner_name: string; roll_rounds: { captain_id: number; roll: number }[][] };
      const lastRound = payload.roll_rounds[payload.roll_rounds.length - 1];
      const rolls = lastRound.map((r) => r.roll).join(" vs ");
      return `Tie resolved! ${payload.winner_name} wins (${rolls})`;
    }
    case "captain_assigned": {
      const payload = event.payload as { captain_name: string };
      return `${payload.captain_name} is picking next`;
    }
    case "pick_undone": {
      const payload = event.payload as { picked_name: string; round: number };
      return `Round ${payload.round} pick undone (${payload.picked_name})`;
    }
    default:
      return "Draft event occurred";
  }
}

export function useDraftWebSocket({
  draftId,
  onEvent,
  onRefreshNeeded,
}: UseDraftWebSocketOptions): UseDraftWebSocketReturn {
  const [events, setEvents] = useState<DraftEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [hasNewEvent, setHasNewEvent] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const clearNewEventFlag = useCallback(() => {
    setHasNewEvent(false);
  }, []);

  const connect = useCallback(() => {
    if (!draftId) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/draft/${draftId}/`;

    log.debug(`Connecting to WebSocket: ${wsUrl}`);

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      log.debug("WebSocket connected");
      setIsConnected(true);
      setConnectionError(null);
    };

    ws.onmessage = (messageEvent) => {
      try {
        const data: WebSocketMessage = JSON.parse(messageEvent.data);
        log.debug("WebSocket message:", data);

        if (data.type === "initial_events" && data.events) {
          setEvents(data.events);
        } else if (data.type === "draft_event" && data.event) {
          const newEvent = data.event;

          // Add to events list (newest first)
          setEvents((prev) => [newEvent, ...prev]);
          setHasNewEvent(true);

          // Show toast for significant events
          if (SIGNIFICANT_EVENTS.includes(newEvent.event_type)) {
            toast(getEventMessage(newEvent));
          }

          // Trigger refresh callback
          onRefreshNeeded?.();
          onEvent?.(newEvent);
        }
      } catch (err) {
        log.error("Failed to parse WebSocket message:", err);
      }
    };

    ws.onclose = (closeEvent) => {
      log.debug("WebSocket closed:", closeEvent.code, closeEvent.reason);
      setIsConnected(false);

      // Attempt reconnect after 3 seconds
      if (closeEvent.code !== 1000) {
        reconnectTimeoutRef.current = setTimeout(() => {
          log.debug("Attempting reconnect...");
          connect();
        }, 3000);
      }
    };

    ws.onerror = (error) => {
      log.error("WebSocket error:", error);
      setConnectionError("Connection error");
    };
  }, [draftId, onEvent, onRefreshNeeded]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close(1000, "Component unmounting");
      }
    };
  }, [connect]);

  return {
    events,
    isConnected,
    connectionError,
    hasNewEvent,
    clearNewEventFlag,
  };
}
```

**Step 2: Commit**

```bash
git add frontend/app/components/draft/hooks/useDraftWebSocket.ts
git commit -m "feat: add useDraftWebSocket hook for real-time draft events"
```

---

## Task 12: Create DraftEventModal Component

**Files:**
- Create: `/home/kettle/git_repos/website/.worktrees/draft-events/frontend/app/components/draft/DraftEventModal.tsx`

**Step 1: Create the modal component**

Create `frontend/app/components/draft/DraftEventModal.tsx`:

```typescript
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog";
import { ScrollArea } from "~/components/ui/scroll-area";
import type { DraftEvent } from "~/types/draftEvent";
import { formatDistanceToNow } from "date-fns";

interface DraftEventModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  events: DraftEvent[];
}

function getEventIcon(eventType: DraftEvent["event_type"]): string {
  switch (eventType) {
    case "draft_started":
      return "▶️";
    case "draft_completed":
      return "🏁";
    case "player_picked":
      return "🎯";
    case "tie_roll":
      return "🎲";
    case "captain_assigned":
      return "👑";
    case "pick_undone":
      return "↩️";
    default:
      return "📋";
  }
}

function getEventDescription(event: DraftEvent): string {
  switch (event.event_type) {
    case "draft_started":
      return "Draft started";
    case "draft_completed":
      return "Draft completed";
    case "player_picked": {
      const payload = event.payload as { captain_name: string; picked_name: string; round: number };
      return `${payload.captain_name} picked ${payload.picked_name} (Round ${payload.round})`;
    }
    case "tie_roll": {
      const payload = event.payload as {
        tied_captains: { name: string }[];
        roll_rounds: { captain_id: number; roll: number }[][];
        winner_name: string;
      };
      const names = payload.tied_captains.map((c) => c.name).join(" vs ");
      const lastRound = payload.roll_rounds[payload.roll_rounds.length - 1];
      const rolls = lastRound.map((r) => `${r.roll}`).join(" vs ");
      return `Tie! ${names} rolled ${rolls} → ${payload.winner_name} wins`;
    }
    case "captain_assigned": {
      const payload = event.payload as { captain_name: string };
      return `${payload.captain_name} is picking next`;
    }
    case "pick_undone": {
      const payload = event.payload as { captain_name: string; picked_name: string; round: number };
      return `Round ${payload.round} pick undone (${payload.picked_name})`;
    }
    default:
      return "Unknown event";
  }
}

export function DraftEventModal({ open, onOpenChange, events }: DraftEventModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Draft Event History</DialogTitle>
        </DialogHeader>
        <ScrollArea className="h-[400px] pr-4">
          {events.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">
              No events yet
            </p>
          ) : (
            <div className="space-y-3">
              {events.map((event) => (
                <div
                  key={event.pk}
                  className="flex items-start gap-3 p-2 rounded-lg bg-muted/50"
                >
                  <span className="text-lg">{getEventIcon(event.event_type)}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium">
                      {getEventDescription(event)}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {formatDistanceToNow(new Date(event.created_at), {
                        addSuffix: true,
                      })}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/components/draft/DraftEventModal.tsx
git commit -m "feat: add DraftEventModal component for event history display"
```

---

## Task 13: Create DraftEventFab Component

**Files:**
- Create: `/home/kettle/git_repos/website/.worktrees/draft-events/frontend/app/components/draft/DraftEventFab.tsx`

**Step 1: Create the FAB component**

Create `frontend/app/components/draft/DraftEventFab.tsx`:

```typescript
import { useState } from "react";
import { Button } from "~/components/ui/button";
import { Badge } from "~/components/ui/badge";
import { History } from "lucide-react";
import { cn } from "~/lib/utils";
import type { DraftEvent } from "~/types/draftEvent";
import { DraftEventModal } from "./DraftEventModal";

interface DraftEventFabProps {
  events: DraftEvent[];
  hasNewEvent: boolean;
  onViewed: () => void;
  isConnected: boolean;
}

export function DraftEventFab({
  events,
  hasNewEvent,
  onViewed,
  isConnected,
}: DraftEventFabProps) {
  const [modalOpen, setModalOpen] = useState(false);

  const handleOpenChange = (open: boolean) => {
    setModalOpen(open);
    if (open) {
      onViewed();
    }
  };

  return (
    <>
      <Button
        variant="default"
        size="icon"
        className={cn(
          "fixed bottom-6 right-6 h-14 w-14 rounded-full shadow-lg z-50",
          hasNewEvent && "animate-pulse"
        )}
        onClick={() => handleOpenChange(true)}
      >
        <History className="h-6 w-6" />
        {events.length > 0 && (
          <Badge
            variant={hasNewEvent ? "destructive" : "secondary"}
            className="absolute -top-1 -right-1 h-6 min-w-6 rounded-full"
          >
            {events.length}
          </Badge>
        )}
        {!isConnected && (
          <span className="absolute bottom-0 right-0 h-3 w-3 rounded-full bg-yellow-500 border-2 border-background" />
        )}
      </Button>

      <DraftEventModal
        open={modalOpen}
        onOpenChange={handleOpenChange}
        events={events}
      />
    </>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/app/components/draft/DraftEventFab.tsx
git commit -m "feat: add DraftEventFab floating action button with badge and pulse"
```

---

## Task 14: Integrate WebSocket into Draft View

**Files:**
- Modify: `/home/kettle/git_repos/website/.worktrees/draft-events/frontend/app/components/draft/draftRoundView.tsx`

**Step 1: Add WebSocket integration to DraftRoundView**

Update `frontend/app/components/draft/draftRoundView.tsx`:

Add imports:
```typescript
import { useDraftWebSocket } from './hooks/useDraftWebSocket';
import { DraftEventFab } from './DraftEventFab';
import { useCallback } from 'react';
```

Inside the component, add the WebSocket hook and refresh logic:
```typescript
  // Add after existing store hooks
  const refreshTournament = useUserStore((state) => state.refreshTournament);

  const handleRefreshNeeded = useCallback(() => {
    if (tournament?.pk) {
      refreshTournament(tournament.pk);
    }
  }, [tournament?.pk, refreshTournament]);

  const {
    events: draftEvents,
    isConnected,
    hasNewEvent,
    clearNewEventFlag,
  } = useDraftWebSocket({
    draftId: draft?.pk ?? null,
    onRefreshNeeded: handleRefreshNeeded,
  });
```

At the end of the JSX, before the closing fragment, add:
```typescript
      {draft?.pk && (
        <DraftEventFab
          events={draftEvents}
          hasNewEvent={hasNewEvent}
          onViewed={clearNewEventFlag}
          isConnected={isConnected}
        />
      )}
```

**Step 2: Commit**

```bash
git add frontend/app/components/draft/draftRoundView.tsx
git commit -m "feat: integrate WebSocket and event FAB into draft view"
```

---

## Task 15: Add Cypress Test for Tie Roll Display

**Files:**
- Create: `/home/kettle/git_repos/website/.worktrees/draft-events/frontend/tests/cypress/e2e/shuffle-draft-roll.cy.ts`
- Modify: `/home/kettle/git_repos/website/.worktrees/draft-events/backend/app/management/commands/populate_test_data.py` (or equivalent)

**Step 1: Create Cypress test file**

Create `frontend/tests/cypress/e2e/shuffle-draft-roll.cy.ts`:

```typescript
describe("Shuffle Draft Roll Results", () => {
  beforeEach(() => {
    // Login as admin
    cy.visit("/");
    cy.get('[data-testid="login-button"]').click();
    // Handle Discord OAuth mock or use test login
  });

  it("displays tie roll event in history when captains have equal MMR", () => {
    // This test requires seeded data with equal MMR captains
    // Navigate to tournament with equal MMR captains
    cy.visit("/tournaments/equal-mmr-test");

    // Start draft
    cy.get('[data-testid="init-draft-button"]').click();
    cy.get('[data-testid="draft-style-shuffle"]').click();
    cy.get('[data-testid="confirm-init-draft"]').click();

    // Wait for draft to initialize
    cy.contains("Pick A player").should("be.visible");

    // Check FAB is visible with events
    cy.get('[data-testid="draft-event-fab"]')
      .should("be.visible")
      .find(".badge")
      .should("have.text.match", /[1-9]/);

    // Open event modal
    cy.get('[data-testid="draft-event-fab"]').click();

    // Verify tie roll event is displayed
    cy.contains("Tie!").should("be.visible");
    cy.contains("rolled").should("be.visible");
    cy.contains("wins").should("be.visible");

    // Close modal
    cy.get('[data-testid="close-modal"]').click();

    // Make a pick
    cy.get('[data-testid="player-choice-card"]').first().click();

    // Verify event count increased
    cy.get('[data-testid="draft-event-fab"]')
      .find(".badge")
      .invoke("text")
      .then((text) => {
        expect(parseInt(text)).to.be.greaterThan(1);
      });

    // Reopen modal and verify pick event
    cy.get('[data-testid="draft-event-fab"]').click();
    cy.contains("picked").should("be.visible");
  });

  it("shows toast notification when player is picked", () => {
    cy.visit("/tournaments/equal-mmr-test");

    // Assuming draft is already in progress
    cy.get('[data-testid="player-choice-card"]').first().click();

    // Verify toast appears
    cy.get('[data-sonner-toast]')
      .should("be.visible")
      .and("contain", "picked");
  });
});
```

**Step 2: Add data-testid attributes to components**

Update `DraftEventFab.tsx` to add data-testid:
```typescript
<Button
  data-testid="draft-event-fab"
  ...
>
```

**Step 3: Commit**

```bash
git add frontend/tests/cypress/e2e/shuffle-draft-roll.cy.ts frontend/app/components/draft/DraftEventFab.tsx
git commit -m "test: add Cypress tests for shuffle draft roll results display"
```

---

## Task 16: Run Full Test Suite and Verify

**Step 1: Run backend tests**

```bash
cd /home/kettle/git_repos/website/.worktrees/draft-events/backend
DISABLE_CACHE=true ../.venv/bin/python manage.py test app.tests -v 2
```
Expected: All tests pass

**Step 2: Start test environment**

```bash
cd /home/kettle/git_repos/website/.worktrees/draft-events
../.venv/bin/inv test.up
```

**Step 3: Run Cypress tests (if environment is ready)**

```bash
cd /home/kettle/git_repos/website/.worktrees/draft-events
../.venv/bin/inv test.headless
```

**Step 4: Final commit with all changes verified**

```bash
git status
git log --oneline -10
```

---

## Summary

This plan implements:

1. **DraftEvent model** - Stores draft lifecycle events with JSON payloads
2. **Django Channels** - WebSocket infrastructure using existing Redis
3. **Broadcast helper** - Sends events to draft and tournament channel groups
4. **Event integration** - Creates events in shuffle_draft.py and tournament.py
5. **Frontend WebSocket hook** - Connects to draft channel, handles messages
6. **FAB and Modal** - Displays event history with badge count and pulse animation
7. **Toast notifications** - Shows significant events as toasts
8. **Nginx config** - Routes `/ws/draft/` and `/ws/tournament/` to backend
9. **Cypress tests** - E2E tests for tie roll display

All changes follow TDD approach with tests written before implementation.

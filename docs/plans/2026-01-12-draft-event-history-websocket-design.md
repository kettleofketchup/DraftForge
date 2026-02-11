# Draft Event History & WebSocket Notifications

**Date:** 2026-01-12
**Status:** Design Complete

## Overview

Add a real-time event history system to shuffle draft that captures the full draft lifecycle (picks, tie rolls, captain assignments, etc.) and broadcasts events to spectators via WebSocket. A floating action button opens a modal showing event history, and significant events appear as toasts.

## Goals

1. Display roll results when tie-breakers occur in shuffle draft
2. Provide complete draft event history for spectators
3. Replace polling with WebSocket-based real-time updates
4. Add Cypress test coverage for tie roll scenarios

## Non-Goals

- Write operations over WebSocket (all mutations stay in REST API)
- Historical event storage beyond draft completion
- Mobile push notifications

---

## Architecture

### Backend

#### New Model: DraftEvent

```python
class DraftEvent(models.Model):
    draft = ForeignKey(Draft, related_name='events', on_delete=CASCADE)
    event_type = CharField(max_length=32, choices=[
        ('draft_started', 'Draft Started'),
        ('draft_completed', 'Draft Completed'),
        ('captain_assigned', 'Captain Assigned'),
        ('player_picked', 'Player Picked'),
        ('tie_roll', 'Tie Roll'),
        ('pick_undone', 'Pick Undone'),
    ])
    payload = JSONField()  # Event-specific data
    actor = ForeignKey(User, null=True, blank=True)  # Who triggered it
    created_at = DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
```

#### Payload Structures

**player_picked:**
```json
{
  "round": 3,
  "captain_id": 1,
  "captain_name": "CaptainA",
  "picked_id": 5,
  "picked_name": "PlayerB",
  "team_id": 1
}
```

**tie_roll:**
```json
{
  "tied_captains": [
    {"id": 1, "name": "CaptainA", "mmr": 5000},
    {"id": 2, "name": "CaptainB", "mmr": 5000}
  ],
  "roll_rounds": [
    [{"captain_id": 1, "roll": 4}, {"captain_id": 2, "roll": 6}]
  ],
  "winner_id": 2,
  "winner_name": "CaptainB"
}
```

**captain_assigned:**
```json
{
  "round": 4,
  "captain_id": 2,
  "captain_name": "CaptainB",
  "team_id": 2,
  "was_tie": false
}
```

**draft_started / draft_completed:**
```json
{
  "draft_id": 1,
  "draft_style": "shuffle",
  "team_count": 4
}
```

**pick_undone:**
```json
{
  "round": 3,
  "captain_name": "CaptainA",
  "picked_name": "PlayerB"
}
```

#### WebSocket Infrastructure

**Dependencies:**
- `channels>=4.0.0` - Django Channels for WebSocket support
- `channels-redis>=4.0.0` - Redis channel layer

**ASGI Configuration (`backend/backend/asgi.py`):**
```python
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from app.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
```

**WebSocket Routes (`backend/app/routing.py`):**
```python
websocket_urlpatterns = [
    path("ws/draft/<int:draft_id>/", DraftConsumer.as_asgi()),
    path("ws/tournament/<int:tournament_id>/", TournamentConsumer.as_asgi()),
]
```

**Channel Groups:**
- `draft_{draft_id}` - Draft-specific events only
- `tournament_{tournament_id}` - All draft events for that tournament

**Consumer Behavior:**
- On connect: validate resource exists, join group, send last 20 events
- On receive: ignored (read-only WebSocket)
- On disconnect: leave group
- Authentication: session-based when available, anonymous allowed

#### Broadcast Helper (`backend/app/broadcast.py`)

```python
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def broadcast_event(event: DraftEvent):
    """Broadcast event to draft and tournament channels."""
    channel_layer = get_channel_layer()
    payload = DraftEventSerializer(event).data

    # Send to draft-specific channel
    async_to_sync(channel_layer.group_send)(
        f"draft_{event.draft_id}",
        {"type": "draft.event", "payload": payload}
    )

    # Send to tournament channel
    tournament_id = event.draft.tournament_id
    async_to_sync(channel_layer.group_send)(
        f"tournament_{tournament_id}",
        {"type": "draft.event", "payload": payload}
    )
```

#### Integration Points

**shuffle_draft.py:**
- `build_shuffle_rounds()` → create `draft_started` event
- `assign_next_shuffle_captain()` → create `captain_assigned` event, plus `tie_roll` event if tie occurred

**tournament.py:**
- `pick_player_for_round()` → create `player_picked` event after successful pick
- After final pick detected → create `draft_completed` event
- `undo_pick()` → create `pick_undone` event

**serializers.py:**
- Add `DraftEventSerializer` for API/WebSocket payloads
- Update `DraftRoundSerializer` to include `was_tie` and `tie_roll_data`

---

### Frontend

#### New Components

**`DraftEventFab.tsx`** - Floating action button
- Fixed position bottom-right of draft view
- Badge showing event count
- Pulse animation (CSS) when new event arrives
- Click opens DraftEventModal

**`DraftEventModal.tsx`** - Event history modal
- Scrollable list, newest events at top
- Event rendering by type:
  - Pick: "CaptainName picked PlayerName (Round 3)"
  - Tie Roll: "Tie! CaptainA rolled 4, CaptainB rolled 6 → CaptainB wins"
  - Draft Started: "Draft started"
  - Draft Completed: "Draft completed"
  - Undo: "Round 3 pick undone"
- Auto-scroll to top on new event (if already at top)

**`useDraftWebSocket.ts`** - WebSocket hook
```typescript
interface UseDraftWebSocketReturn {
  events: DraftEvent[];
  isConnected: boolean;
  connectionError: string | null;
}

function useDraftWebSocket(draftId: number): UseDraftWebSocketReturn {
  // Connect to /ws/draft/{draftId}/
  // On event received:
  //   1. Add to local events list
  //   2. Trigger toast if significant event
  //   3. Call refreshDraftHook() to fetch fresh draft data
  // Handle reconnection on disconnect
}
```

#### Toast Integration

- Uses existing shadcn/sonner toast system
- Significant events trigger toasts:
  - `player_picked`
  - `tie_roll`
  - `draft_started`
  - `draft_completed`
- Minor events (captain_assigned) do not toast
- Clicking toast opens event modal

#### Data Flow

1. WebSocket receives event notification
2. Event added to local history (for modal display)
3. Toast shown if significant event
4. `refreshDraftHook()` called to fetch fresh draft state from REST API
5. UI updates with new draft data (existing logic unchanged)

This approach:
- Keeps backend as single source of truth
- Allows removal/reduction of polling
- Reuses existing draft display logic

---

### Infrastructure

#### Nginx Configuration

Add WebSocket proxy to `nginx/nginx.conf`:
```nginx
location /ws/ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_read_timeout 86400;
}
```

#### Backend Server

Replace Gunicorn with Daphne (ASGI server) to handle both HTTP and WebSocket:
```dockerfile
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "backend.asgi:application"]
```

#### Redis Channel Layer

Add to Django settings:
```python
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(os.environ.get("REDIS_HOST", "redis"), 6379)],
        },
    },
}
```

No new Redis instance needed - uses existing caching Redis.

---

## Testing

### Cypress Test: `shuffle-draft-roll.cy.ts`

**Setup:**
- Seed 4 captains with identical MMR (e.g., 5000 each)
- Guarantees tie on first captain assignment

**Test Flow:**
1. Login as admin
2. Navigate to tournament draft page
3. Start shuffle draft
4. Wait for draft initialization
5. Assert: FAB visible with event count >= 1
6. Click FAB to open modal
7. Assert: Modal contains tie roll event (match "rolled" text)
8. Assert: Event shows two captain names and roll values
9. Make a pick
10. Assert: Event count increases, new pick event in modal

**Test Data:**
- Add fixture or API endpoint for creating equal-MMR captain scenario
- Could extend existing `just db::populate::all` with specific test case

### Backend Unit Tests

- Test DraftEvent creation for each event type
- Test broadcast_event sends to correct channels
- Test consumer authentication (session vs anonymous)
- Test event serialization

---

## Migration Plan

1. Add DraftEvent model, run migrations
2. Add Django Channels infrastructure (asgi.py, routing, consumers)
3. Update Nginx config for WebSocket proxy
4. Switch backend from Gunicorn to Daphne
5. Add broadcast calls to existing draft functions
6. Build frontend components (FAB, modal, hook)
7. Integrate WebSocket hook into draft view
8. Add Cypress tests
9. Reduce/remove polling once WebSocket stable

---

## File Changes Summary

### Backend (New Files)
- `backend/backend/asgi.py` - ASGI application config
- `backend/app/routing.py` - WebSocket URL routes
- `backend/app/consumers.py` - WebSocket consumers
- `backend/app/broadcast.py` - Event broadcast helper

### Backend (Modified Files)
- `backend/app/models.py` - Add DraftEvent model
- `backend/app/serializers.py` - Add DraftEventSerializer, update DraftRoundSerializer
- `backend/app/functions/shuffle_draft.py` - Add event creation
- `backend/app/functions/tournament.py` - Add event creation
- `backend/requirements.txt` - Add channels, channels-redis
- `backend/backend/settings.py` - Add CHANNEL_LAYERS config

### Frontend (New Files)
- `frontend/app/components/draft/DraftEventFab.tsx`
- `frontend/app/components/draft/DraftEventModal.tsx`
- `frontend/app/hooks/useDraftWebSocket.ts`
- `frontend/app/types/draftEvent.ts`

### Frontend (Modified Files)
- `frontend/app/components/draft/DraftRoundView.tsx` - Add FAB and WebSocket integration

### Infrastructure (Modified Files)
- `nginx/nginx.conf` - Add WebSocket proxy
- `docker/backend/Dockerfile` - Switch to Daphne
- `docker-compose.*.yaml` - Update backend command if needed

### Tests (New Files)
- `frontend/tests/cypress/e2e/shuffle-draft-roll.cy.ts`
- `backend/app/tests/test_draft_events.py`

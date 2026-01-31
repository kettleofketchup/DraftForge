# User Presence System Design

**Status**: Draft
**Created**: 2025-01-31
**Author**: Claude + kettle

## Problem Statement

Users cannot see who else is currently active on the site. We want to show real-time presence (online/away/offline) and disconnect WebSockets when browser tabs are inactive to save server resources.

## Goals

1. Show real-time user presence status (green dot = online)
2. Disconnect WebSocket when tab is hidden for extended period
3. Minimal resource overhead
4. Reusable across different features (tournaments, drafts, etc.)

## Non-Goals (v1)

- Typing indicators
- "Last seen" timestamps
- Custom status messages
- Presence in specific rooms/channels (global presence only for v1)

---

## Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         BROWSER                                  │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │ Visibility  │───▶│  Presence    │───▶│ UI Components    │   │
│  │ Detection   │    │  WebSocket   │    │ (green dots)     │   │
│  └─────────────┘    └──────────────┘    └──────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ WebSocket + Heartbeats
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DJANGO/DAPHNE                               │
│  ┌─────────────────┐         ┌─────────────────────────────┐   │
│  │ PresenceConsumer │────────▶│ Batched Broadcast Service  │   │
│  │ (lightweight)    │         │ (collects updates, sends   │   │
│  └─────────────────┘         │  every 2-5 seconds)         │   │
└──────────────────────────────┴─────────────────────────────────┘
                              │
                              │ Redis Operations
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         REDIS                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ presence:online (Sorted Set)                             │   │
│  │   score=timestamp, member=user_id                        │   │
│  │   Example: {user:123: 1706745600, user:456: 1706745590}  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

#### 1. Dedicated Presence WebSocket vs Piggyback on Existing

**Option A: Dedicated `/api/presence/` WebSocket** (Recommended for v1)
- Pros: Simple, isolated, easy to disable/enable
- Cons: Additional connection per user
- Memory: ~50-100KB per connection (can optimize with uvicorn)

**Option B: Add presence to existing WebSockets (HeroDraft, Tournament)**
- Pros: No additional connections
- Cons: Couples presence to feature WebSockets, complex

**Decision**: Start with Option A for simplicity. Can migrate to Option B later if memory is a concern.

#### 2. Heartbeat Strategy

```
Client                          Server                         Redis
   │                               │                              │
   │──── connect ─────────────────▶│                              │
   │                               │──── ZADD presence:online ───▶│
   │                               │     (user_id, timestamp)     │
   │                               │                              │
   │◀─── initial_presence ────────│◀─── ZRANGEBYSCORE ──────────│
   │     {users: [...]}            │                              │
   │                               │                              │
   │──── heartbeat (every 30s) ──▶│                              │
   │                               │──── ZADD (update score) ───▶│
   │                               │                              │
   │     [tab hidden 30s+]         │                              │
   │──── stop heartbeats ─────────▶│                              │
   │                               │                              │
   │                               │◀─── Celery: cleanup stale ──│
   │                               │     ZREMRANGEBYSCORE         │
   │                               │──── broadcast offline ──────▶│
   │                               │                              │
```

#### 3. Batched Broadcasting

Instead of broadcasting every status change immediately, collect changes and broadcast in batches:

```python
class PresenceBroadcaster:
    """Collects presence changes and broadcasts every BATCH_INTERVAL seconds."""

    BATCH_INTERVAL = 2.0  # seconds

    def __init__(self):
        self.pending_updates: dict[int, str] = {}  # user_id -> status
        self._task: asyncio.Task | None = None

    async def queue_update(self, user_id: int, status: str):
        """Queue a presence update for batched broadcast."""
        self.pending_updates[user_id] = status

        # Start batch timer if not running
        if self._task is None:
            self._task = asyncio.create_task(self._batch_loop())

    async def _batch_loop(self):
        """Flush pending updates every BATCH_INTERVAL."""
        while self.pending_updates:
            await asyncio.sleep(self.BATCH_INTERVAL)
            await self._flush()
        self._task = None

    async def _flush(self):
        """Broadcast all pending updates as single message."""
        if not self.pending_updates:
            return

        updates = self.pending_updates.copy()
        self.pending_updates.clear()

        await channel_layer.group_send("presence", {
            "type": "presence.batch",
            "updates": updates,  # {user_id: status, ...}
        })
```

**Why batching matters:**

| Scenario | Without Batching | With Batching (2s) |
|----------|------------------|-------------------|
| 10 users come online in 5s | 10 broadcasts | 2-3 broadcasts |
| 100 users, heartbeats every 30s | 3.3 msg/sec | 0.5 msg/sec |
| Network traffic | O(users × updates) | O(batches) |

---

## Resource Estimates

### Memory Breakdown

| Component | Per User | 1,000 Users | Notes |
|-----------|----------|-------------|-------|
| WebSocket connection | 50-100 KB | 50-100 MB | Can reduce with uvicorn |
| Redis presence data | 135 bytes | 135 KB | Sorted set + metadata |
| Python consumer state | 500 bytes | 500 KB | Minimal state |
| **Total incremental** | **~500 bytes** | **~500 KB** | If reusing existing WS |
| **Total dedicated WS** | **~100 KB** | **~100 MB** | New presence connection |

### CPU Estimates

| Operation | Cost | Frequency | Impact |
|-----------|------|-----------|--------|
| Heartbeat processing | 0.1ms | Every 30s/user | Negligible |
| Redis ZADD | 0.05ms | Every 30s/user | Negligible |
| Batch broadcast | 1-5ms | Every 2s | Low |
| Stale cleanup | 10-50ms | Every 60s | Low |

**For 1,000 concurrent users**: <5% single CPU core

### Network Estimates

| Message Type | Size | Frequency |
|--------------|------|-----------|
| Heartbeat (client→server) | ~50 bytes | Every 30s |
| Presence batch (server→client) | ~500 bytes | Every 2-5s |
| Initial presence list | ~5 KB | On connect |

**Monthly data per user**: ~1-2 MB (with 30s heartbeats, 2s batches)

---

## Implementation Phases

### Phase 1: Core Infrastructure (Backend)

**Files to create:**

```
backend/app/presence/
├── __init__.py
├── consumer.py      # PresenceConsumer WebSocket
├── manager.py       # PresenceBroadcaster + Redis operations
└── tasks.py         # Celery cleanup tasks
```

**Redis schema:**

```python
# Sorted Set: Online users with timestamps
KEY = "presence:online"
# ZADD presence:online {user_id: timestamp}
# ZRANGEBYSCORE presence:online (now-90) +inf  → online users
# ZREMRANGEBYSCORE presence:online -inf (now-90)  → cleanup

# Optional: User metadata hash
KEY = "presence:user:{user_id}"
# HSET presence:user:123 username "kettle" avatar_url "..."
```

**WebSocket routing:**

```python
# backend/app/routing.py
websocket_urlpatterns = [
    # ... existing routes ...
    path("api/presence/", PresenceConsumer.as_asgi()),
]
```

### Phase 2: Frontend Hooks

**Files to create:**

```
frontend/app/hooks/
├── usePageVisibility.ts      # Tab visibility detection
└── usePresence.ts            # Presence WebSocket + state
```

**usePageVisibility hook:**

```typescript
export function usePageVisibility(options?: {
  onVisible?: () => void;
  onHidden?: () => void;
  hiddenDelayMs?: number;  // Delay before calling onHidden
}): { isVisible: boolean };
```

**usePresence hook:**

```typescript
export function usePresence(): {
  // State
  presences: Map<number, PresenceStatus>;
  myStatus: 'online' | 'away' | 'offline';
  isConnected: boolean;

  // Derived
  isUserOnline: (userId: number) => boolean;
  onlineCount: number;
};
```

### Phase 3: UI Components

**Files to create:**

```
frontend/app/components/presence/
├── PresenceIndicator.tsx     # Green/yellow/gray dot
├── PresenceBadge.tsx         # Dot positioned on avatar
└── OnlineUsersList.tsx       # List of online users
```

**Component API:**

```tsx
// Simple indicator
<PresenceIndicator status="online" size="sm" />

// On avatar
<div className="relative">
  <Avatar src={user.avatar} />
  <PresenceBadge userId={user.id} position="bottom-right" />
</div>

// Online users list
<OnlineUsersList
  showCount={true}
  maxDisplay={10}
/>
```

### Phase 4: Tab Visibility Integration

**Behavior:**

| Tab State | After 0s | After 30s | After 5min |
|-----------|----------|-----------|------------|
| Hidden | Continue heartbeats | Stop heartbeats (→ "away") | Disconnect WS |
| Visible | Resume heartbeats | - | Reconnect if needed |

**Configuration:**

```typescript
const PRESENCE_CONFIG = {
  heartbeatIntervalMs: 30_000,      // Send heartbeat every 30s
  awayThresholdMs: 30_000,          // Stop heartbeats after 30s hidden
  disconnectThresholdMs: 300_000,   // Disconnect after 5min hidden
  reconnectOnVisible: true,          // Auto-reconnect when tab visible
};
```

---

## API Specification

### WebSocket Messages

**Client → Server:**

```typescript
// Heartbeat (sent every 30s while tab visible)
{ "type": "heartbeat" }

// Explicit status change (optional)
{ "type": "set_status", "status": "away" | "online" }
```

**Server → Client:**

```typescript
// Initial presence list (on connect)
{
  "type": "presence_init",
  "users": [
    { "user_id": 123, "status": "online", "username": "kettle" },
    { "user_id": 456, "status": "away", "username": "player2" }
  ]
}

// Batched presence updates (every 2-5s)
{
  "type": "presence_batch",
  "updates": {
    "123": "offline",  // user_id: new_status
    "789": "online"
  }
}
```

### REST Endpoints (Optional)

```
GET /api/presence/online/
  → { "count": 42, "users": [...] }

GET /api/presence/user/{id}/
  → { "status": "online", "last_seen": "2025-01-31T12:00:00Z" }
```

---

## Configuration

### Backend Settings

```python
# backend/backend/settings.py

PRESENCE_CONFIG = {
    # Timing
    "heartbeat_timeout_seconds": 45,      # Expect heartbeat within this
    "presence_timeout_seconds": 90,       # Mark offline after this
    "batch_interval_seconds": 2,          # Broadcast batch interval
    "cleanup_interval_seconds": 60,       # Celery cleanup frequency

    # Limits
    "max_connections": 10_000,            # Connection limit
    "max_presence_broadcast": 1_000,      # Max users in single broadcast

    # Redis
    "redis_key_prefix": "presence:",
    "redis_db": 2,                        # Separate DB for presence
}
```

### Frontend Settings

```typescript
// frontend/app/config/presence.ts

export const PRESENCE_CONFIG = {
  // WebSocket
  url: '/api/presence/',
  reconnectDelayMs: 1_000,
  maxReconnectAttempts: 5,

  // Heartbeat
  heartbeatIntervalMs: 30_000,

  // Tab visibility
  awayThresholdMs: 30_000,
  disconnectThresholdMs: 300_000,

  // UI
  showAwayStatus: true,
  statusColors: {
    online: 'bg-green-500',
    away: 'bg-yellow-500',
    offline: 'bg-gray-500',
  },
};
```

---

## Testing Plan

### Unit Tests

- [ ] PresenceBroadcaster batching logic
- [ ] Redis operations (ZADD, ZRANGEBYSCORE, cleanup)
- [ ] usePageVisibility hook
- [ ] usePresence hook state management

### Integration Tests

- [ ] WebSocket connect/disconnect flow
- [ ] Heartbeat timeout → offline transition
- [ ] Tab hidden → away → offline flow
- [ ] Reconnection after tab becomes visible

### Load Tests

- [ ] 100 concurrent connections
- [ ] 1,000 concurrent connections
- [ ] Rapid connect/disconnect (page refresh simulation)

---

## Rollout Plan

### Stage 1: Internal Testing
- Deploy to test environment
- Manual testing with 2-3 users
- Verify memory/CPU metrics

### Stage 2: Limited Release
- Enable for staff users only
- Monitor for 1 week
- Gather feedback

### Stage 3: Full Release
- Enable for all users
- Add to user settings (optional disable)
- Monitor metrics

---

## Open Questions

1. **Should presence be opt-in or opt-out?**
   - Opt-out (default on) recommended for better UX

2. **Show presence globally or only in specific contexts?**
   - v1: Global presence (simpler)
   - v2: Context-specific (tournament, draft room)

3. **Should we show "last seen" for offline users?**
   - v1: No (privacy concerns, storage cost)
   - v2: Optional setting

4. **Mobile app considerations?**
   - Need to handle app backgrounding differently
   - Consider longer timeouts for mobile

---

## Alternatives Considered

### 1. Polling Instead of WebSockets
- Simpler but higher latency and server load
- Rejected: We already use WebSockets, presence fits naturally

### 2. Server-Sent Events (SSE)
- Simpler than WebSockets, one-way only
- Rejected: Need bidirectional for heartbeats

### 3. Third-Party Service (Pusher, Ably)
- Zero infrastructure, handles scale
- Rejected: Additional cost, already have WebSocket infrastructure

---

## References

- [Discord Architecture](https://d4dummies.com/architecting-for-hyperscale-an-in-depth-analysis-of-discords-billion-message-per-day-infrastructure/)
- [Slack Real-time Messaging](https://slack.engineering/real-time-messaging/)
- [Redis Sorted Sets](https://redis.io/docs/data-types/sorted-sets/)
- [Page Visibility API](https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API)

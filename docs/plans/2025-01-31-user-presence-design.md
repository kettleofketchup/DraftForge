# User Presence System Design

**Status**: Draft
**Created**: 2025-01-31
**Author**: Claude + kettle

## Problem Statement

Users cannot see who else is currently viewing the same page. We want to show "X users are here" or display avatars of users on the same page, similar to Google Docs or Figma's presence indicators.

## Goals

1. Show which users are viewing the same page (URL-based presence)
2. Real-time updates when users join/leave a page
3. Disconnect WebSocket when tab is hidden (save resources)
4. Minimal resource overhead

## Non-Goals (v1)

- Global "online" status across the whole site
- Typing indicators
- Cursor positions
- "Last seen" timestamps

---

## Core Concept

**Page-based presence**: Each URL path is a "room". Users on the same page see each other.

```
/tournament/5/players  →  [kettle, player2, player3] viewing
/tournament/5/games    →  [admin, spectator1] viewing
/leagues/2             →  [kettle] viewing (alone)
```

---

## Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         BROWSER                                  │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │ Visibility  │───▶│  Presence    │───▶│ "3 users here"   │   │
│  │ Detection   │    │  WebSocket   │    │ [avatar][avatar] │   │
│  └─────────────┘    └──────────────┘    └──────────────────┘   │
│        │                   │                                    │
│        │ Tab hidden?       │ Send current URL                   │
│        │ Stop heartbeats   │ on connect + route change          │
└────────┴───────────────────┴────────────────────────────────────┘
                              │
                              │ WebSocket: {url: "/tournament/5"}
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DJANGO/DAPHNE                               │
│  ┌─────────────────┐                                            │
│  │ PresenceConsumer │─── Join group for URL path                │
│  │                  │─── Track user → URL in Redis              │
│  │                  │─── Broadcast to same-page users           │
│  └─────────────────┘                                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         REDIS                                    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ presence:user:{user_id}  (STRING with TTL)              │   │
│  │   Value: "/tournament/5/players"                         │   │
│  │   TTL: 60 seconds (refreshed by heartbeat)              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ presence:page:{url_hash}  (SET)                          │   │
│  │   Members: [user_id, user_id, ...]                       │   │
│  │   Example: presence:page:tournament_5_players → {1,2,3} │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Authentication & Anonymous Users

Support both authenticated and anonymous users:

```python
class PresenceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]

        if user.is_authenticated:
            # Authenticated user - use their PK
            self.user_id = f"user:{user.pk}"
            self.user_data = {
                "type": "user",
                "pk": user.pk,
                "username": user.username,
                # avatar fetched separately if needed
            }
        else:
            # Anonymous user - generate session-based ID
            session_key = self.scope.get("session", {}).get("_session_key")
            if not session_key:
                session_key = str(uuid.uuid4())[:8]
            self.user_id = f"anon:{session_key}"
            self.user_data = {
                "type": "anonymous",
                "id": session_key,
            }

        await self.accept()
        # ... rest of connect logic
```

**Display in UI:**

```
┌─────────────────────────────────────────────────────┐
│  Tournament Players                                  │
│                                                      │
│  Viewing: [👤 kettle] [👤 player2] [👻 Guest] [👻 Guest] │
│           ─────────── ───────────  ─────────────────── │
│           authenticated users      anonymous users     │
└─────────────────────────────────────────────────────┘
```

### Redis Schema

```python
# Key 1: User/session presence data (HASH with TTL)
# For authenticated users: presence:user:123
# For anonymous users: presence:anon:a1b2c3d4
KEY = "presence:{user_id}"
VALUE = {
    "type": "user" | "anonymous",
    "url": "/tournament/5/players",
    "username": "kettle",        # only for authenticated
    "pk": "123",                 # only for authenticated
}
TTL = 60 seconds  # Auto-expires if no heartbeat

# Key 2: Who is on this page? (SET)
KEY = "presence:page:{url_path}"
VALUE = SET of user_ids (both "user:123" and "anon:a1b2c3d4")

# Example - Authenticated user:
HSET presence:user:123 type "user" url "/tournament/5/players" username "kettle" pk "123"
EXPIRE presence:user:123 60
SADD presence:page:/tournament/5/players user:123

# Example - Anonymous user:
HSET presence:anon:a1b2c3d4 type "anonymous" url "/tournament/5/players"
EXPIRE presence:anon:a1b2c3d4 60
SADD presence:page:/tournament/5/players anon:a1b2c3d4
```

**Querying page presence:**

```python
async def get_page_users(url: str) -> dict:
    """Get all users on a page, separated by type."""
    user_ids = redis.smembers(f"presence:page:{url}")

    users = []
    anonymous_count = 0

    for user_id in user_ids:
        data = redis.hgetall(f"presence:{user_id}")
        if data.get("type") == "user":
            users.append({
                "pk": int(data["pk"]),
                "username": data["username"],
            })
        else:
            anonymous_count += 1

    return {
        "users": users,              # [{pk: 123, username: "kettle"}, ...]
        "anonymous_count": anonymous_count,  # 3
    }
```

### URL Grouping: Exact Path Match

Each URL path is its own room. Users only see others on the exact same page:

```
/tournament/5/players  →  Room A  →  [kettle, player2]
/tournament/5/games    →  Room B  →  [admin]
/tournament/5          →  Room C  →  [spectator1]
```

This means navigating between tabs on the same tournament shows different users.

### Message Flow

```
Client                          Server                         Redis
   │                               │                              │
   │── connect(url="/tour/5") ────▶│                              │
   │                               │── SET presence:user:123 ────▶│
   │                               │   "/tour/5" EX 60            │
   │                               │── SADD presence:page:tour_5 ─▶│
   │                               │   123                         │
   │                               │── SMEMBERS presence:page:... ─▶│
   │◀── page_users: [123,456] ────│◀─────────────────────────────│
   │                               │                              │
   │── navigate(url="/tour/5/g") ─▶│                              │
   │                               │── SREM old page set ────────▶│
   │                               │── SADD new page set ────────▶│
   │                               │── broadcast to old page ────▶│
   │                               │── broadcast to new page ────▶│
   │◀── page_users: [789] ────────│                              │
   │                               │                              │
   │── heartbeat (every 30s) ─────▶│                              │
   │                               │── EXPIRE presence:user:123 ─▶│
   │                               │   60 (refresh TTL)           │
   │                               │                              │
   │     [tab hidden > 30s]        │                              │
   │     [stop heartbeats]         │                              │
   │                               │                              │
   │                               │   [TTL expires after 60s]    │
   │                               │◀── key expired ──────────────│
   │                               │── SREM from page set ───────▶│
   │                               │── broadcast user left ──────▶│
```

### Key Design Decisions

#### 1. URL Normalization

Normalize URLs to group related pages:

```python
def normalize_url(url: str) -> str:
    """Normalize URL for presence grouping."""
    # Remove query params and trailing slashes
    # /tournament/5/players?tab=1 → /tournament/5/players
    # /tournament/5/players/ → /tournament/5/players
    parsed = urlparse(url)
    return parsed.path.rstrip('/')

def url_to_group_key(url: str) -> str:
    """Convert URL to Redis-safe group key."""
    normalized = normalize_url(url)
    # /tournament/5/players → tournament_5_players
    return normalized.strip('/').replace('/', '_')
```

#### 2. Channel Layer Groups

Each page URL becomes a Django Channels group:

```python
# On connect/navigate:
group_name = f"presence_{url_to_group_key(url)}"
await self.channel_layer.group_add(group_name, self.channel_name)

# On disconnect/navigate away:
await self.channel_layer.group_discard(old_group_name, self.channel_name)
```

#### 3. Tab Visibility Handling

| Tab State | Action | Result |
|-----------|--------|--------|
| Visible | Send heartbeats every 30s | TTL refreshed, stay in page set |
| Hidden | Stop heartbeats | TTL expires after 60s, removed from page |
| Visible again | Resume heartbeats | Re-add to page set if expired |

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
└── usePagePresence.ts        # Page presence WebSocket + state

frontend/app/store/
└── presenceStore.ts          # Zustand store for presence
```

**usePageVisibility hook:**

```typescript
export function usePageVisibility(options?: {
  onVisible?: () => void;
  onHidden?: () => void;
  hiddenDelayMs?: number;  // Delay before calling onHidden
}): { isVisible: boolean };
```

**usePagePresence hook:**

```typescript
export function usePagePresence(): {
  // Users on current page
  usersOnPage: User[];
  userCount: number;

  // Connection state
  isConnected: boolean;

  // Helpers
  isUserHere: (userId: number) => boolean;
};

// Usage in component:
function TournamentPage() {
  const { usersOnPage, userCount } = usePagePresence();

  return (
    <div>
      <span>{userCount} users viewing</span>
      {usersOnPage.map(u => <Avatar key={u.id} user={u} />)}
    </div>
  );
}
```

**Automatic URL tracking:**

The hook automatically:
1. Connects to `/api/presence/` WebSocket on mount
2. Sends current URL from `useLocation()` (React Router)
3. Sends new URL on route changes
4. Pauses heartbeats when tab is hidden
5. Disconnects after extended inactivity

### Phase 3: UI Components

**Files to create:**

```
frontend/app/components/presence/
├── PagePresence.tsx          # "3 users viewing this page"
├── PagePresenceAvatars.tsx   # Row of avatars for users on page
└── PresenceProvider.tsx      # Context provider for presence state
```

**Component API:**

```tsx
// Simple count
<PagePresence />
// Renders: "3 users viewing this page" or "You're the only one here"

// Avatar stack (like Google Docs)
<PagePresenceAvatars maxDisplay={5} />
// Renders: [avatar][avatar][avatar] +2 more

// Full usage in a page layout
<PresenceProvider>
  <div className="flex justify-between">
    <h1>Tournament Players</h1>
    <PagePresenceAvatars />
  </div>
  {/* ... page content ... */}
</PresenceProvider>
```

**Avatar stack design:**

```
┌─────────────────────────────────────────┐
│  Tournament Players    [👤][👤][👤] +2  │
│                                         │
│  (page content...)                      │
└─────────────────────────────────────────┘
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

### WebSocket Endpoint

```
ws://localhost/api/presence/
```

### WebSocket Messages

**Client → Server:**

```typescript
// Initial connection with current URL
{ "type": "join", "url": "/tournament/5/players" }

// Navigate to new page (or send new join)
{ "type": "navigate", "url": "/tournament/5/games" }

// Heartbeat (sent every 30s while tab visible)
{ "type": "heartbeat" }

// Tab became hidden (optional - can just stop heartbeats)
{ "type": "away" }

// Tab became visible again
{ "type": "active" }
```

**Server → Client:**

```typescript
// Who's on this page (sent on join/navigate)
{
  "type": "page_presence",
  "url": "/tournament/5/players",
  "users": [
    { "pk": 123, "username": "kettle", "avatar": "..." },
    { "pk": 456, "username": "player2", "avatar": "..." }
  ],
  "anonymous_count": 3  // 3 anonymous guests on this page
}

// Authenticated user joined
{
  "type": "user_joined",
  "user": { "pk": 789, "username": "newuser", "avatar": "..." }
}

// Authenticated user left
{
  "type": "user_left",
  "user_pk": 456
}

// Anonymous user joined/left (just update count)
{
  "type": "anonymous_count",
  "count": 4  // Updated count of anonymous users
}
```

### REST Endpoint (Optional - for non-WebSocket clients)

```
GET /api/presence/page/?url=/tournament/5/players
  → {
      "url": "/tournament/5/players",
      "count": 3,
      "users": [...]
    }
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

## Decisions Made

1. **URL grouping**: ✅ **Exact path match** - `/tournament/5/players` and `/tournament/5/games` are different rooms

2. **Anonymous users**: ✅ **Supported** - Track both authenticated and anonymous users
   - Authenticated: Show avatar + username
   - Anonymous: Show ghost icon + count ("+ 3 guests")

3. **User identification**: ✅ **Hybrid IDs**
   - Authenticated: `user:{pk}` (e.g., `user:123`)
   - Anonymous: `anon:{session_id}` (e.g., `anon:a1b2c3d4`)

4. **Privacy**: ✅ **No opt-out** - All users are visible when on a page

## Open Questions

1. **Which pages should show presence?**
   - All pages? Only specific pages (tournament, draft, league)?
   - Recommendation: Start with tournament/league detail pages only

2. **Should users see themselves in the count?**
   - "3 users here" (includes you) vs "2 others here"
   - Recommendation: Include self, clearer mental model

3. **What user info to show?**
   - Just count? Avatars? Usernames on hover?
   - Recommendation: Avatar stack for users, count for anonymous

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

# User Presence System Design

**Status**: Draft
**Created**: 2025-01-31
**Author**: Claude + kettle

## Problem Statement

Users cannot see who else is currently viewing the same page. We want to show "X users are here" or display avatars of users on the same page, similar to Google Docs or Figma's presence indicators.

## Goals

1. Show which users are viewing the same page (URL-based presence)
2. Near-real-time updates (up to 30s latency acceptable)
3. Stop heartbeats when tab is hidden (save resources, auto-remove after TTL)
4. Minimal resource overhead (~1-2% CPU, ~120KB Redis for 1000 users)

## Non-Goals (v1)

- Global "who's online" live feed (we DO support checking if specific users are online via batch lookup)
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

**Key insight**: No separate presence WebSocket. Existing consumers (Tournament, Draft, HeroDraft) include presence data in their messages. Clients read cached Redis data.

```
┌─────────────────────────────────────────────────────────────────┐
│                         BROWSER                                  │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │ Visibility  │───▶│  Existing    │───▶│ "3 users here"   │   │
│  │ Detection   │    │  WebSocket   │    │ [avatar][avatar] │   │
│  └─────────────┘    │ (Tournament, │    └──────────────────┘   │
│        │            │  Draft, etc) │                            │
│        │ Tab hidden?└──────────────┘                            │
│        │ Stop heartbeats    │                                   │
└────────┴────────────────────┴───────────────────────────────────┘
                              │
                              │ Existing WS messages include presence
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DJANGO/DAPHNE                               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ TournamentConsumer / DraftConsumer / HeroDraftConsumer   │  │
│  │                                                           │  │
│  │  on_connect():                                            │  │
│  │    - Register user in Redis presence                      │  │
│  │    - Include presence in state response                   │  │
│  │                                                           │  │
│  │  on_heartbeat():                                          │  │
│  │    - Refresh TTL in Redis                                 │  │
│  │    - Return current presence (cached read)                │  │
│  │                                                           │  │
│  │  on_disconnect():                                         │  │
│  │    - Remove from Redis presence                           │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         REDIS                                    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ presence:{user_id}  (HASH with TTL)                      │   │
│  │   Value: {url, username, pk, type}                       │   │
│  │   TTL: 60 seconds (refreshed by heartbeat)              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ presence:page:{url_path}  (SET)                          │   │
│  │   Members: [user_id, user_id, ...]                       │   │
│  │   Example: presence:page:/tournament/5 → {user:1,anon:x}│   │
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
                "avatar": getattr(user, "avatar_url", None),
            }
        else:
            # Anonymous user - use channel_name for stable ID per connection
            # channel_name is unique per WebSocket connection
            anon_id = self.channel_name[-12:]  # Last 12 chars are unique enough
            self.user_id = f"anon:{anon_id}"
            self.user_data = {
                "type": "anonymous",
            }

        await self.accept()
        # ... rest of connect logic
```

**Note**: Anonymous users get a new ID per connection (page refresh = new anonymous entry). This is intentional - we can't reliably track anonymous users across connections without cookies/sessions.

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

**Checking if users are online (batch lookup):**

For showing online status on user lists, profiles, leaderboards - without invalidating user cache:

```python
# backend/app/presence/manager.py
def get_online_status_batch(user_ids: list[int]) -> dict[int, bool]:
    """Check online status for multiple users in one Redis call.

    SYNC function - use in REST API views (DRF).
    Uses django-redis sync client.
    """
    if not user_ids:
        return {}

    # Use sync redis client (from django.core.cache or redis-py)
    pipeline = redis_client.pipeline()
    for user_id in user_ids:
        pipeline.exists(f"presence:user:{user_id}")

    results = pipeline.execute()
    return {uid: bool(status) for uid, status in zip(user_ids, results)}


async def get_online_status_batch_async(user_ids: list[int]) -> dict[int, bool]:
    """Async version for WebSocket consumers."""
    if not user_ids:
        return {}

    pipe = redis.pipeline()
    for user_id in user_ids:
        pipe.exists(f"presence:user:{user_id}")

    results = await pipe.execute()
    return {uid: bool(status) for uid, status in zip(user_ids, results)}
```

**Usage in views (prefetch pattern):**

```python
class UserListView(APIView):
    def get(self, request):
        users = User.objects.all()[:50]  # Cached by cacheops

        # Single batched Redis call for all users
        online_status = get_online_status_batch([u.pk for u in users])

        # Pass to serializer context
        serializer = UserSerializer(
            users,
            many=True,
            context={'online_status': online_status}
        )
        return Response(serializer.data)
```

**Usage in serializers:**

```python
class UserSerializer(serializers.ModelSerializer):
    is_online = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['pk', 'username', 'avatar', 'is_online']

    def get_is_online(self, obj):
        # Use prefetched data from context (not cached with user model)
        online_status = self.context.get('online_status', {})
        return online_status.get(obj.pk, False)
```

**Key insight**: User model cache is never invalidated by online/offline changes. Online status is fetched fresh from Redis at serialization time.

**Querying page presence (with lazy cleanup):**

```python
async def get_page_users(url: str) -> dict:
    """Get all users on a page, separated by type.

    Performs lazy cleanup: removes stale user IDs from the page SET
    if their HASH has expired (handles ungraceful disconnects).
    """
    user_ids = await redis.smembers(f"presence:page:{url}")

    users = []
    anonymous_count = 0
    stale_ids = []  # Track expired users for cleanup

    for user_id in user_ids:
        data = await redis.hgetall(f"presence:{user_id}")
        if not data:
            # HASH expired (ungraceful disconnect) - mark for cleanup
            stale_ids.append(user_id)
            continue
        if data.get("type") == "user":
            users.append({
                "pk": int(data["pk"]),
                "username": data["username"],
                "avatar": data.get("avatar"),
            })
        else:
            anonymous_count += 1

    # Lazy cleanup: remove stale entries from page SET
    if stale_ids:
        await redis.srem(f"presence:page:{url}", *stale_ids)

    return {
        "users": users,              # [{pk: 123, username: "kettle", avatar: "..."}, ...]
        "anonymous_count": anonymous_count,  # 3
    }
```

**Why lazy cleanup?** Page SETs have no TTL. If a user's browser crashes or network drops, the HASH expires via TTL but the user ID remains in the SET. Lazy cleanup removes these stale entries on read.

### URL Grouping: Exact Path Match

Each URL path is its own room. Users only see others on the exact same page:

```
/tournament/5/players  →  Room A  →  [kettle, player2]
/tournament/5/games    →  Room B  →  [admin]
/tournament/5          →  Room C  →  [spectator1]
```

This means navigating between tabs on the same tournament shows different users.

### Message Flow

**No broadcasts** - presence is included in existing WebSocket responses.

```
Client                          Server                         Redis
   │                               │                              │
   │── connect to /api/tournament/5/ ▶│                           │
   │                               │── HSET presence:user:123 ───▶│
   │                               │── SADD presence:page:... ───▶│
   │                               │── SMEMBERS + HGETALL ───────▶│
   │◀── tournament_state + presence ─│◀─────────────────────────│
   │   {tournament: {...},         │                              │
   │    presence: {users: [...],   │                              │
   │               anonymous: 2}}  │                              │
   │                               │                              │
   │── heartbeat (every 30s) ─────▶│                              │
   │                               │── EXPIRE presence:user:123 ─▶│
   │                               │── SMEMBERS + HGETALL ───────▶│
   │◀── presence update ───────────│◀────────────────────────────│
   │   {presence: {users: [...],   │                              │
   │               anonymous: 2}}  │                              │
   │                               │                              │
   │     [tab hidden > 30s]        │                              │
   │     [stop heartbeats]         │                              │
   │                               │                              │
   │                               │   [TTL expires after 60s]    │
   │                               │   [user auto-removed]        │
   │                               │                              │
   │── disconnect ────────────────▶│                              │
   │                               │── SREM from page set ───────▶│
   │                               │── DEL presence:user:123 ────▶│
```

**Key difference**: Server never broadcasts. Each client gets presence data when:
1. They connect (included in initial state)
2. They send a heartbeat (server responds with fresh presence)

### Key Design Decisions

#### 1. URL Normalization

Normalize URLs for presence grouping:

```python
from urllib.parse import urlparse

def normalize_url(url: str) -> str:
    """Normalize URL for presence grouping."""
    # Remove query params and trailing slashes
    # /tournament/5/players?tab=1 → /tournament/5/players
    # /tournament/5/players/ → /tournament/5/players
    parsed = urlparse(url)
    return parsed.path.rstrip('/')
```

#### 2. No Broadcast Groups

Unlike typical presence systems, we don't use Django Channels groups for broadcasting.
Each client polls for presence on their heartbeat. This is simpler and more efficient:

- No group management overhead
- No broadcast fan-out CPU cost
- Presence data is slightly stale (up to 30s) but acceptable for this use case

#### 3. Tab Visibility Handling

| Tab State | Action | Result |
|-----------|--------|--------|
| Visible | Send heartbeats every 30s | TTL refreshed, stay in page set |
| Hidden | Stop heartbeats | TTL expires after 60s, removed from page |
| Visible again | Resume heartbeats | Re-add to page set if expired |

**Why TTL (60s) = 2 × heartbeat interval (30s)?**

This allows one missed heartbeat (network hiccup, browser lag) without removing the user. If two consecutive heartbeats are missed, the user is likely actually gone.

---

## Storage Design

### No Database Writes

This system is **purely Redis-based** with zero database writes:

| Storage | Used For | Persistence |
|---------|----------|-------------|
| Redis HASH | User presence data (`presence:user:123`) | Ephemeral, 60s TTL |
| Redis SET | Page membership (`presence:page:/tournament/5`) | Ephemeral, cleaned on disconnect |
| PostgreSQL/SQLite | **Nothing** | N/A |

**Why no database?**

- Presence is ephemeral by nature (who cares who was online yesterday?)
- High write frequency (heartbeats every 30s) would strain the DB
- Redis TTL handles cleanup automatically
- Server restart = users reconnect naturally, no stale data

**User metadata** (username, avatar, pk) is read from existing `User` model on connect, but nothing is written back.

---

## Resource Estimates

### Memory Breakdown

| Component | Per User | 1,000 Users | Notes |
|-----------|----------|-------------|-------|
| Redis presence HASH | ~100 bytes | ~100 KB | User data + URL |
| Redis page SET membership | ~20 bytes | ~20 KB | Just user ID reference |
| **Total Redis** | **~120 bytes** | **~120 KB** | |

**No additional WebSocket memory** - piggybacks on existing connections (Tournament, Draft, etc.).

### CPU Estimates

| Operation | Cost | Frequency | Impact |
|-----------|------|-----------|--------|
| Heartbeat processing | 0.1ms | Every 30s/user | Negligible |
| Redis HSET + EXPIRE | 0.05ms | Every 30s/user | Negligible |
| Redis SMEMBERS + HGETALL | 0.2ms | Every 30s/user | Negligible |
| Stale cleanup | 10-50ms | Every 60s | Low |

**Detailed calculation for 1,000 concurrent users:**

```
Heartbeats (includes presence read):
  - Rate: 1000 users / 30s = 33 heartbeats/second
  - Cost per heartbeat:
      0.1ms  (Python processing)
    + 0.05ms (Redis HSET + EXPIRE)
    + 0.2ms  (Redis SMEMBERS + HGETALL for presence)
    = 0.35ms
  - Total: 33 × 0.35ms = ~12ms/second

Cleanup (Redis TTL handles most, periodic SET cleanup):
  - Rate: 1 cleanup/60s
  - Cost: ~30ms
  - Amortized: 30ms / 60 = ~0.5ms/second

─────────────────────────────────────────
Total CPU time: ~12.5ms/second
As percentage: 12.5ms / 1000ms = 1.25% of one CPU core
```

**For 1,000 concurrent users**: ~1-2% single CPU core

**Note**: No broadcast overhead. Each client reads cached presence on their own heartbeat interval.

### API Request Costs (Online Status Lookups)

| Operation | Cost | Use Case |
|-----------|------|----------|
| Check 1 user online | ~0.05ms | User profile page |
| Check 50 users online (batched) | ~0.1ms | Team list, leaderboard |
| Check 100 users online (batched) | ~0.15ms | Large player list |

Batch lookups use Redis pipelining - single round-trip regardless of user count.

### Network Estimates

| Message Type | Size | Frequency |
|--------------|------|-----------|
| Heartbeat (client→server) | ~30 bytes | Every 30s |
| Heartbeat ack with presence (server→client) | ~200-500 bytes | Every 30s |

**Monthly data per user**: ~500 KB (with 30s heartbeats)

---

## Implementation Phases

### Phase 1: Core Infrastructure (Backend)

**Files to create:**

```
backend/app/presence/
├── __init__.py
├── manager.py       # PresenceManager - Redis operations
└── mixins.py        # PresenceMixin for existing consumers
```

**PresenceMixin for existing consumers:**

```python
# backend/app/presence/mixins.py
class PresenceMixin:
    """Add presence tracking to any WebSocket consumer."""

    async def register_presence(self, url: str):
        """Call in connect() after accept()."""
        self.presence_url = url
        self.presence_user_id = self._get_user_id()
        await presence_manager.add_user(self.presence_user_id, url, self._get_user_data())

    async def unregister_presence(self):
        """Call in disconnect()."""
        await presence_manager.remove_user(self.presence_user_id, self.presence_url)

    async def refresh_presence(self):
        """Call on heartbeat."""
        await presence_manager.refresh_ttl(self.presence_user_id)

    async def get_presence(self) -> dict:
        """Get current presence for this page."""
        return await presence_manager.get_page_presence(self.presence_url)
```

**PresenceManager with atomic operations:**

```python
# backend/app/presence/manager.py
class PresenceManager:
    """Handles Redis operations for presence tracking."""

    async def add_user(self, user_id: str, url: str, user_data: dict):
        """Add user to presence, handling page navigation atomically."""
        # Get old URL to clean up old page SET (handles navigation)
        old_url = await redis.hget(f"presence:{user_id}", "url")

        pipe = redis.pipeline()
        # Update user HASH with new URL
        pipe.hset(f"presence:{user_id}", mapping={**user_data, "url": url})
        pipe.expire(f"presence:{user_id}", 60)
        # Add to new page SET
        pipe.sadd(f"presence:page:{url}", user_id)
        # Remove from old page SET if different (atomic cleanup)
        if old_url and old_url != url:
            pipe.srem(f"presence:page:{old_url}", user_id)
        await pipe.execute()

    async def remove_user(self, user_id: str, url: str):
        """Remove user from presence on disconnect."""
        pipe = redis.pipeline()
        pipe.srem(f"presence:page:{url}", user_id)
        pipe.delete(f"presence:{user_id}")
        await pipe.execute()

    async def refresh_ttl(self, user_id: str):
        """Refresh TTL on heartbeat."""
        await redis.expire(f"presence:{user_id}", 60)
```

**Modify existing consumers:**

```python
# backend/app/consumers/tournament.py
class TournamentConsumer(PresenceMixin, AsyncWebsocketConsumer):
    async def connect(self):
        # ... existing connect logic ...
        await self.register_presence(f"/tournament/{self.tournament_id}")

    async def disconnect(self, code):
        await self.unregister_presence()
        # ... existing disconnect logic ...

    async def receive_json(self, content):
        if content.get("type") == "heartbeat":
            await self.refresh_presence()
            presence = await self.get_presence()
            await self.send_json({"type": "heartbeat_ack", "presence": presence})
            return
        # ... existing message handling ...
```

**No new WebSocket routes needed.**

### Phase 2: Frontend Hooks

**Files to create:**

```
frontend/app/hooks/
└── usePageVisibility.ts      # Tab visibility detection
```

**usePageVisibility hook:**

```typescript
export function usePageVisibility(): {
  isVisible: boolean;
  // Use to pause/resume heartbeats
};
```

**Modify existing WebSocket hooks to include heartbeat:**

```typescript
// Example: useTournamentSocket.ts
export function useTournamentSocket(tournamentId: number) {
  const { isVisible } = usePageVisibility();
  const [presence, setPresence] = useState<Presence | null>(null);

  useEffect(() => {
    if (!isVisible) return; // Stop heartbeats when tab hidden

    const interval = setInterval(() => {
      ws.send(JSON.stringify({ type: "heartbeat" }));
    }, 30_000);

    return () => clearInterval(interval);
  }, [isVisible]);

  // Handle heartbeat_ack messages
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "heartbeat_ack") {
      setPresence(data.presence);
    }
    // ... existing message handling
  };

  return {
    // ... existing return values
    presence,
  };
}
```

**No separate presence WebSocket connection needed.**

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

| Tab State | Action | Result |
|-----------|--------|--------|
| Hidden | Stop heartbeats immediately | TTL expires after 60s, removed from presence |
| Visible | Resume heartbeats | Back in presence on next heartbeat |

**Implementation:**

```typescript
// usePageVisibility.ts
export function usePageVisibility() {
  const [isVisible, setIsVisible] = useState(!document.hidden);

  useEffect(() => {
    const handler = () => setIsVisible(!document.hidden);
    document.addEventListener("visibilitychange", handler);
    return () => document.removeEventListener("visibilitychange", handler);
  }, []);

  return { isVisible };
}
```

Existing WebSocket hooks use `isVisible` to pause/resume heartbeats. No separate disconnect logic needed - Redis TTL handles cleanup automatically.

---

## API Specification

### No Separate Presence Endpoint

Presence is added to **existing WebSocket consumers**. No new endpoint needed.

### Modified Existing WebSocket Messages

**Client → Server (add heartbeat to existing consumers):**

```typescript
// Heartbeat (sent every 30s while tab visible)
// Add this message type to TournamentConsumer, DraftConsumer, HeroDraftConsumer
{ "type": "heartbeat" }
```

**Server → Client (add presence field to existing responses):**

```typescript
// Example: Tournament state now includes presence
{
  "type": "tournament_state",
  "tournament": { /* existing tournament data */ },
  "presence": {
    "users": [
      { "pk": 123, "username": "kettle" },
      { "pk": 456, "username": "player2" }
    ],
    "anonymous_count": 3
  }
}

// Heartbeat response includes updated presence
{
  "type": "heartbeat_ack",
  "presence": {
    "users": [
      { "pk": 123, "username": "kettle" },
      { "pk": 456, "username": "player2" }
    ],
    "anonymous_count": 3
  }
}
```

### Presence Data Structure

```typescript
interface PresenceUser {
  pk: number;
  username: string;
  avatar?: string;  // URL to avatar image, if available
}

interface Presence {
  users: PresenceUser[];
  anonymous_count: number;
}
```

### REST Endpoint (Optional - for pages without WebSocket)

For pages that don't have a WebSocket connection (e.g., user profiles, static pages):

```
GET /api/presence/?url=/tournament/5

Response:
{
  "url": "/tournament/5",
  "users": [
    { "pk": 123, "username": "kettle", "avatar": "..." }
  ],
  "anonymous_count": 3
}
```

**Implementation notes:**
- Authentication: Optional (public endpoint, presence is not private)
- Rate limiting: Consider 10 req/sec per IP to prevent abuse
- Uses same `get_page_users()` function as WebSocket consumers
- Returns empty list if no users on page (not 404)

---

## Configuration

### Backend Settings

```python
# backend/backend/settings.py

PRESENCE_CONFIG = {
    # Timing
    "ttl_seconds": 60,                    # Redis key TTL
    "cleanup_interval_seconds": 60,       # Periodic SET cleanup frequency

    # Redis
    "redis_key_prefix": "presence:",
}
```

### Frontend Settings

```typescript
// frontend/app/config/presence.ts

export const PRESENCE_CONFIG = {
  // Heartbeat
  heartbeatIntervalMs: 30_000,

  // Tab visibility - stop heartbeats when hidden
  stopHeartbeatsWhenHidden: true,
};
```

---

## Testing Plan

### Unit Tests

- [ ] PresenceManager Redis operations (HSET, SADD, SMEMBERS, EXPIRE)
- [ ] PresenceMixin methods (register, unregister, refresh, get)
- [ ] get_online_status_batch() batch lookup
- [ ] usePageVisibility hook
- [ ] URL normalization

### Integration Tests

- [ ] WebSocket connect registers presence in Redis
- [ ] WebSocket disconnect removes presence from Redis
- [ ] Heartbeat refreshes TTL
- [ ] TTL expiry removes user from page SET
- [ ] Presence included in heartbeat_ack response

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

5. **Architecture**: ✅ **No separate presence WebSocket** - Piggyback on existing consumers (Tournament, Draft, HeroDraft)

6. **No broadcasts**: ✅ **Pull-based** - Clients get presence on heartbeat response, no server push

7. **Caching strategy**: ✅ **Separate concerns**
   - User model data: Cached by cacheops (never invalidated by online status)
   - Online status: Fresh from Redis at serialization time (batch prefetch in views)

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

- [Page Visibility API](https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API)
- [Redis HASH](https://redis.io/docs/data-types/hashes/)
- [Redis SET](https://redis.io/docs/data-types/sets/)
- [Redis Pipelining](https://redis.io/docs/manual/pipelining/)

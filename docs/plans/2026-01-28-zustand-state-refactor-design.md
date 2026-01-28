# Zustand State Management Refactor Design

**Date**: 2026-01-28
**Status**: Approved (Revised after review)
**Scope**: Frontend state management + Backend API optimization
**Reviewed by**: Backend API, Frontend Zustand, Performance/Caching, Architecture specialists

## Problem Statement

Currently, `useUserStore` is a 440-line "god store" holding everything:
- User data (current user, all users, discord users)
- Tournament data (full recursive with nested draft/teams/games)
- Draft data (full draft with all rounds)
- Teams, Games, Organizations, Leagues
- Query states, hydration, auto-refresh flags

**Issues:**
1. `fetchTournament(pk)` returns entire nested structure (users, teams, games, draft with all rounds)
2. Team draft polling refetches full tournament every 3 seconds
3. No clear separation of concerns between domains
4. Excessive bandwidth usage for real-time updates

## Solution Overview

### Architecture (Revised)

```
┌─────────────────────────────────────────────────────────────────┐
│                        useUserStore (auth only)                  │
│  - currentUser, hasHydrated, isStaff()                          │
│  - Persisted to sessionStorage                                   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     WebSocketManager (singleton)                 │
│  - Reference-counted connections per draftId/tournamentId       │
│  - Reconnection with exponential backoff                        │
│  - Message sequence validation                                   │
└───────────────┬─────────────────────────────────┬───────────────┘
                │                                 │
        ┌───────▼───────┐                ┌───────▼───────┐
        │useTournamentStore│              │useHeroDraftStore│
        │ (source of truth)│              │ (enhanced)     │
        │                  │              │                │
        │- tournament      │◄────READ─────│- draft         │
        │- users[]         │              │- tick          │
        │- teams[]         │              │- isConnected   │
        │- games[]         │              │- connectionError│
        │- isLoadingX flags│              └────────────────┘
        │- error states    │
        └───────┬──────────┘
                │
        ┌───────▼───────┐   ┌─────────────────┐
        │useTeamDraftStore│  │ useBracketStore │
        │                │  │ (polling only)  │
        │- currentRound  │  │- matches[]      │
        │- pickOrder     │  │- 5s polling     │
        │- READ from     │  │- ETag support   │
        │  Tournament    │  └─────────────────┘
        │- isConnected   │
        │- connectionError│
        └────────────────┘
```

### Data Flow Principles (Revised)

1. **`useTournamentStore`** is source of truth for users/teams/games
2. **Unidirectional data flow only** - draft stores READ from tournament store, never write back
3. **Mutations go through API** - API broadcasts WebSocket event - both stores update independently
4. **WebSocketManager singleton** with reference counting for shared connections
5. **WebSocket-first for active drafts** (HeroDraft, TeamDraft)
6. **Polling for Bracket** - low-frequency updates don't justify WebSocket overhead
7. **HTTP fetch for initial page loads** with stale-while-revalidate pattern

---

## Backend API Changes

### New Selective Endpoints via ViewSet @action (Revised)

Use DRF's `@action` decorator on existing `TournamentViewSet` instead of separate views:

```python
class TournamentViewSet(viewsets.ModelViewSet):
    queryset = Tournament.objects.all()
    serializer_class = TournamentSerializer

    @action(detail=True, methods=['get'])
    def metadata(self, request, pk=None):
        """GET /api/tournaments/{pk}/metadata/
        Returns lightweight tournament info without nested objects."""
        tournament = self.get_object()
        return Response(TournamentMetadataSerializer(tournament).data)

    @action(detail=True, methods=['get'])
    def users(self, request, pk=None):
        """GET /api/tournaments/{pk}/users/
        Returns players in this tournament."""
        tournament = self.get_object()
        return Response(TournamentUserSerializer(tournament.users.all(), many=True).data)

    @action(detail=True, methods=['get'])
    def teams(self, request, pk=None):
        """GET /api/tournaments/{pk}/teams/
        Returns teams with player IDs."""
        tournament = self.get_object()
        return Response(TeamSerializerForTournament(tournament.teams.all(), many=True).data)

    @action(detail=True, methods=['get'])
    def games(self, request, pk=None):
        """GET /api/tournaments/{pk}/games/
        Returns games/matches."""
        tournament = self.get_object()
        return Response(GameSerializerForTournament(tournament.games.all(), many=True).data)

    @action(detail=True, methods=['get'])
    def draft_state(self, request, pk=None):
        """GET /api/tournaments/{pk}/draft_state/
        Returns current draft state (not full history)."""
        tournament = self.get_object()
        if not hasattr(tournament, 'draft') or not tournament.draft:
            return Response({'error': 'No draft'}, status=404)
        return Response(TeamDraftStateSerializer(tournament.draft).data)
```

| Endpoint | Returns | Used By |
|----------|---------|---------|
| `GET /tournaments/{pk}/metadata/` | Tournament metadata (name, status, dates, draft_id) | Initial page load |
| `GET /tournaments/{pk}/users/` | Players `[{id, username, avatar, mmr, positions}]` | useTournamentStore |
| `GET /tournaments/{pk}/teams/` | Teams `[{id, name, captain_id, player_ids[], mmr_sum}]` | useTournamentStore |
| `GET /tournaments/{pk}/games/` | Games `[{id, team1_id, team2_id, winner_id, scores}]` | useTournamentStore |
| `GET /tournaments/{pk}/draft_state/` | Current draft state | useTeamDraftStore |

### New Serializers Required

```python
class TournamentMetadataSerializer(serializers.ModelSerializer):
    """Lightweight tournament metadata without nested objects."""
    draft_id = serializers.IntegerField(source='draft.pk', allow_null=True)
    bracket_exists = serializers.SerializerMethodField()

    class Meta:
        model = Tournament
        fields = ('pk', 'name', 'state', 'date_played', 'timezone',
                  'tournament_type', 'draft_id', 'bracket_exists')

    def get_bracket_exists(self, obj):
        return obj.games.exists()

class TeamDraftStateSerializer(serializers.Serializer):
    """Current state of team draft for WebSocket/API."""
    current_round = DraftRoundForDraftSerializer(allow_null=True)
    available_players = TournamentUserSerializer(many=True)
    team_rosters = serializers.SerializerMethodField()
    pick_order = serializers.ListField(child=serializers.IntegerField())
    status = serializers.ChoiceField(choices=['pending', 'in_progress', 'completed'])
    sequence_number = serializers.IntegerField()  # For message ordering

    def get_team_rosters(self, draft):
        return {team.pk: [p.pk for p in team.players.all()] for team in draft.teams.all()}
```

### Caching Strategy (Revised - Use Existing Cacheops)

Keep using existing `cacheops` with `invalidate_obj()` pattern. Align all TTLs to 60 minutes (existing config):

| Endpoint | Cache | Invalidation |
|----------|-------|--------------|
| All `@action` endpoints | Via cacheops `@cached_as` | Automatic via `invalidate_obj()` on model save |

**Critical Fix**: Move WebSocket broadcasts to `on_commit` to prevent dirty reads:

```python
from django.db import transaction
from cacheops import invalidate_obj

def pick_player_for_round(request):
    with transaction.atomic():
        draft_round = DraftRound.objects.select_for_update().get(pk=request.data['draft_round_pk'])
        draft_round.pick_player(user)
        draft = draft_round.draft

        # cacheops handles cache invalidation automatically via model.save() -> invalidate_obj()

    # AFTER transaction commits - broadcast via WebSocket
    # This prevents dirty reads if transaction rolls back
    broadcast_draft_state(draft)

    return Response(DraftRoundSerializer(draft_round).data)
```

### Cascading Cache Invalidation

When a pick happens, multiple caches need invalidation. Add to model save methods:

```python
# In DraftRound.save()
def save(self, *args, **kwargs):
    super().save(*args, **kwargs)
    # Invalidate related caches
    invalidate_obj(self.draft)
    invalidate_obj(self.draft.tournament)
    for team in self.draft.teams.all():
        invalidate_obj(team)
```

### WebSocket Consumers (Revised)

| Consumer | Path | Purpose |
|----------|------|---------|
| `DraftConsumer` | `/api/draft/{draft_id}/` | Enhance with sequence numbers |
| `TournamentConsumer` | `/api/tournament/{tournament_id}/` | Already exists - no new BracketConsumer |

**Note**: No separate `BracketConsumer` - bracket updates are low-frequency. Use existing polling with ETag support.

### Authentication for Consumers

Add authentication check to existing consumers:

```python
class DraftConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return
        # ... rest of connect logic
```

### TeamDraft WebSocket Message Format (Revised)

```python
{
    "type": "draft_state",
    "sequence": 42,  # Monotonic counter for message ordering
    "current_round": {"pk": 5, "pick_number": 3, "captain": {...}},
    "available_players": [{"id": 1, "username": "...", "mmr": 5000}, ...],
    "team_rosters": {"team_1": [player_ids], "team_2": [player_ids]},
    "pick_order": [captain_id, captain_id, ...],
    "status": "in_progress",
    "timestamp": "2026-01-28T12:00:00Z"
}
```

---

## Frontend Store Specifications

### WebSocketManager (New - Singleton)

```typescript
// websocketManager.ts - Shared WebSocket connection manager
interface WebSocketManager {
  // Reference-counted connections
  connections: Map<string, { ws: WebSocket; refCount: number; sequence: number }>;

  // Connect with reference counting
  connect: (key: string, url: string, handlers: WebSocketHandlers) => void;
  disconnect: (key: string) => void;

  // Message handling with sequence validation
  send: (key: string, message: object) => void;

  // Get connection state
  isConnected: (key: string) => boolean;
  getSequence: (key: string) => number;
}

// Usage: Singleton instance
export const wsManager = createWebSocketManager();

// Implementation handles:
// - Reference counting (multiple components can connect to same draft)
// - Exponential backoff reconnection
// - Sequence number validation (ignore out-of-order messages)
// - Clean disconnect when refCount reaches 0
```

### `useUserStore` (Slimmed Down)

```typescript
// ~80 lines instead of ~440
interface UserStore {
  // Auth
  currentUser: UserType | null;
  hasHydrated: boolean;

  // User pool (global, not tournament-specific)
  users: UserType[];
  discordUsers: DiscordUserType[];

  // Actions
  getCurrentUser: () => Promise<void>;
  getUsers: () => Promise<void>;
  getDiscordUsers: (query: string) => Promise<void>;
  createUser: (data: UserCreateData) => Promise<void>;
  clearUser: () => void;
  isStaff: () => boolean;
}

// Persistence: sessionStorage (currentUser, users only)
```

### `useTournamentStore` (New - Source of Truth)

```typescript
interface TournamentStore {
  // Data (fetched progressively)
  tournament: TournamentType | null;
  users: UserType[];           // Players in THIS tournament
  teams: TeamType[];           // Teams in THIS tournament
  games: GameType[];           // Games in THIS tournament

  // Loading states - SEPARATE BOOLEANS (not object, avoids re-render storms)
  isLoadingTournament: boolean;
  isLoadingUsers: boolean;
  isLoadingTeams: boolean;
  isLoadingGames: boolean;

  // Error states
  loadError: { endpoint: string; error: Error } | null;

  // UI state (existing from current tournamentStore)
  activeTab: string;
  live: boolean;
  livePolling: boolean;
  autoAdvance: boolean;
  pendingDraftId: number | null;
  pendingMatchId: string | null;

  // Version tracking for HTTP/WebSocket sync
  dataVersion: number;

  // Actions - progressive fetch
  loadTournament: (pk: number) => Promise<void>;      // Metadata only
  loadUsers: (pk: number) => Promise<void>;           // Then users
  loadTeams: (pk: number) => Promise<void>;           // Then teams
  loadGames: (pk: number) => Promise<void>;           // Then games
  loadAll: (pk: number) => Promise<void>;             // Batch load with error handling

  // Called by WebSocket handlers to update state (with version check)
  updateFromWebSocket: (data: TournamentUpdate, version: number) => void;

  // Clear on navigation
  reset: () => void;
}

// Persistence: NONE (refetch on mount)
```

### `useTeamDraftStore` (New)

```typescript
interface TeamDraftStore {
  // Connection state
  isConnected: boolean;
  connectionError: Error | null;
  reconnectAttempts: number;

  // Live draft state (from WebSocket)
  currentRound: DraftRoundType | null;
  pickOrder: number[];                     // captain IDs in order
  status: 'pending' | 'in_progress' | 'completed';
  lastSequence: number;                    // For message ordering

  // UI state
  selectedPlayerId: number | null;

  // Derived data - READ from useTournamentStore (not stored here)
  // availablePlayers and teamRosters derived from tournament.users and tournament.teams

  // Actions
  connect: (draftId: number) => void;      // Uses wsManager
  disconnect: () => void;
  reconnect: () => void;
  pickPlayer: (playerId: number) => Promise<void>;   // API call only
  undoPick: () => Promise<void>;                      // API call only

  // NO syncToTournament - unidirectional flow
  // Tournament store updates independently via WebSocket

  reset: () => void;
}

// Persistence: NONE
```

### `useHeroDraftStore` (Enhanced)

```typescript
interface HeroDraftStore {
  // Existing
  draft: HeroDraftType | null;
  tick: HeroDraftTick | null;
  selectedHeroId: number | null;
  searchQuery: string;

  // Connection state (enhanced)
  isConnected: boolean;
  connectionError: Error | null;
  reconnectAttempts: number;
  connectionId: string | null;
  lastSequence: number;

  // Derived helpers
  getCurrentTeam: () => TeamType | null;
  getOtherTeam: () => TeamType | null;
  isMyTurn: (userId: number) => boolean;
  getUsedHeroIds: () => number[];
  getBannedHeroIds: () => number[];

  // Actions
  connect: (draftId: number) => void;      // Uses wsManager
  disconnect: () => void;
  reconnect: () => void;
  banHero: (heroId: number) => Promise<void>;
  pickHero: (heroId: number) => Promise<void>;

  // Setters
  setDraft: (draft: HeroDraftType) => void;
  setTick: (tick: HeroDraftTick) => void;
  setSelectedHeroId: (id: number | null) => void;
  setSearchQuery: (query: string) => void;
  reset: () => void;
}

// Persistence: NONE
```

### `useBracketStore` (Revised - Polling Only)

```typescript
interface BracketStore {
  // Existing
  matches: MatchType[];
  nodes: Node[];
  edges: Edge[];
  isDirty: boolean;
  isVirtual: boolean;
  isLoading: boolean;

  // Error state
  loadError: Error | null;

  // Polling state (NO WebSocket - low frequency updates)
  isPolling: boolean;
  lastETag: string | null;      // For conditional requests

  // Fetch from tournament endpoint
  loadBracket: (tournamentId: number) => Promise<void>;

  // Polling with ETag support
  startPolling: (tournamentId: number, intervalMs?: number) => void;
  stopPolling: () => void;

  // Existing operations
  generateBracket: (teams: TeamType[]) => void;
  assignTeamToSlot: (matchId: number, slot: 1 | 2, teamId: number) => void;
  setMatchWinner: (matchId: number, winnerId: number) => void;
  advanceWinner: (matchId: number) => void;
  saveBracket: (tournamentId: number) => Promise<void>;

  // NO syncToTournament - updates go through API
  // Tournament store refetches games after bracket save

  reset: () => void;
}

// Persistence: NONE
```

### Selector Patterns (New Section)

To prevent re-render storms, use these patterns consistently:

```typescript
// Pattern 1: Individual stable selectors for actions (no useShallow needed)
const loadTournament = useTournamentStore(s => s.loadTournament);

// Pattern 2: Grouped state with useShallow
const { tournament, isLoadingTournament } = useTournamentStore(
  useShallow(s => ({ tournament: s.tournament, isLoadingTournament: s.isLoadingTournament }))
);

// Pattern 3: Derived selectors (memoized outside component)
const selectTournamentUserIds = (s: TournamentStore) => s.users.map(u => u.pk);
const userIds = useTournamentStore(selectTournamentUserIds);

// Pattern 4: Cross-store derived data (compute in component, not store)
const tournamentUsers = useTournamentStore(s => s.users);
const teamRosters = useTournamentStore(s => s.teams.reduce(
  (acc, t) => ({ ...acc, [t.pk]: t.player_ids }), {}
));
const pickedIds = Object.values(teamRosters).flat();
const availablePlayers = tournamentUsers.filter(u => !pickedIds.includes(u.pk));
```

---

## Page-by-Page Store Usage

### Tournament Detail Page (`/tournament/{pk}`)

```typescript
// Current: loads full recursive tournament
const tournament = useUserStore(state => state.tournament);
useEffect(() => { getTournament(pk); }, [pk]);

// New: progressive loading
const { tournament, users, teams, isLoading, loadTournament, loadUsers, loadTeams } = useTournamentStore();

useEffect(() => {
  loadTournament(pk);     // Metadata first (fast)
  loadUsers(pk);          // Then players
  loadTeams(pk);          // Then teams
}, [pk]);
```

### Draft Tab (Team Drafts - Shuffle/Snake)

```typescript
// Current: polls full tournament every 3s
const { draft, curDraftRound, getCurrentTournament } = useUserStore();
useInterval(() => getCurrentTournament(), 3000);

// New: WebSocket-driven
const { tournament } = useTournamentStore();
const { currentRound, availablePlayers, teamRosters, connect, disconnect } = useTeamDraftStore();

useEffect(() => {
  if (tournament?.draft?.status === 'in_progress') {
    connect(tournament.draft.pk);  // WebSocket takes over
  }
  return () => disconnect();
}, [tournament?.draft?.pk, tournament?.draft?.status]);
```

### Bracket Tab

```typescript
// Current: polls bracket, reads tournament for context
const { tournament } = useUserStore();
const { matches, loadBracket, startPolling } = useBracketStore();

// New: Polling with ETag support (NOT WebSocket - low frequency updates)
const tournament = useTournamentStore(s => s.tournament);
const { matches, loadBracket, startPolling, stopPolling } = useBracketStore();

useEffect(() => {
  if (!tournament?.pk) return;

  loadBracket(tournament.pk);

  // Use polling, not WebSocket - bracket updates are infrequent
  if (tournament.state === 'in_progress') {
    startPolling(tournament.pk, 5000);  // 5s interval with ETag
  }

  return () => stopPolling();
}, [tournament?.pk, tournament?.state]);
```

### HeroDraft Modal

```typescript
// Current: WebSocket hook separate from store
const { draft, tick } = useHeroDraftStore();
const { sendMessage } = useHeroDraftWebSocket({ onStateUpdate: setDraft, onTick: setTick });

// New: WebSocket managed by store
const { draft, tick, connect, disconnect, pickHero, banHero, isConnected } = useHeroDraftStore();

useEffect(() => {
  connect(draftId);
  return () => disconnect();
}, [draftId]);
```

---

## Error Handling & Edge Cases

### WebSocket Reconnection (via WebSocketManager)

```typescript
// WebSocketManager handles reconnection with exponential backoff
const createWebSocketManager = () => {
  const connections = new Map<string, ConnectionState>();

  const connect = (key: string, url: string, handlers: WebSocketHandlers) => {
    const existing = connections.get(key);
    if (existing) {
      existing.refCount++;
      return;  // Reuse existing connection
    }

    const state: ConnectionState = {
      ws: null,
      refCount: 1,
      sequence: 0,
      retryCount: 0,
    };

    const doConnect = () => {
      const ws = new WebSocket(url);

      ws.onopen = () => {
        state.retryCount = 0;
        handlers.onConnect?.();
      };

      ws.onclose = (event) => {
        handlers.onDisconnect?.();
        if (!event.wasClean && state.retryCount < MAX_RETRIES && state.refCount > 0) {
          const delay = Math.min(1000 * Math.pow(2, state.retryCount), 30000);
          state.retryCount++;
          setTimeout(doConnect, delay);
        }
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        // Validate sequence number
        if (data.sequence && data.sequence <= state.sequence) {
          console.warn('Out-of-order message ignored', data.sequence);
          return;
        }
        state.sequence = data.sequence || state.sequence;
        handlers.onMessage?.(data);
      };

      state.ws = ws;
    };

    connections.set(key, state);
    doConnect();
  };

  const disconnect = (key: string) => {
    const state = connections.get(key);
    if (!state) return;

    state.refCount--;
    if (state.refCount <= 0) {
      state.ws?.close(1000, 'Client disconnect');
      connections.delete(key);
    }
  };

  return { connect, disconnect, isConnected, send };
};
```

### HTTP/WebSocket Desync Prevention

```typescript
// Store tracks data version to prevent HTTP overwriting fresher WebSocket data
interface TournamentStore {
  dataVersion: number;

  updateFromWebSocket: (data: TournamentUpdate, version: number) => void;
  updateFromHttp: (data: TournamentData, version: number) => void;
}

const updateFromWebSocket = (data, version) => {
  // WebSocket always wins - update version
  set({ ...data, dataVersion: version });
};

const updateFromHttp = (data, version) => {
  // Only apply if version is newer than current
  if (version > get().dataVersion) {
    set({ ...data, dataVersion: version });
  }
};
```

### Stale Data Prevention (Enhanced)

```typescript
// Store tracks current tournament/draft ID AND connection ID
// Ignores messages for old IDs after navigation
let activeConnectionId = 0;

const connect = (draftId: number) => {
  const thisConnectionId = ++activeConnectionId;

  wsManager.connect(`draft:${draftId}`, url, {
    onMessage: (data) => {
      // Ignore if navigation happened
      if (activeConnectionId !== thisConnectionId) return;
      // Ignore if for different draft
      if (data.draft_id !== draftId) return;
      // Process message
      handleDraftUpdate(data);
    }
  });
};

const reset = () => {
  activeConnectionId++;  // Invalidate in-flight handlers
  // Reset state...
};
```

### Progressive Loading with Partial Failure Handling

```typescript
// Track load request IDs AND handle partial failures
let loadId = 0;

const loadAll = async (pk: number) => {
  const thisLoadId = ++loadId;
  const currentPk = pk;

  set({
    isLoadingTournament: true,
    isLoadingUsers: true,
    isLoadingTeams: true,
    isLoadingGames: true,
    loadError: null,
  });

  try {
    const [tournament, users, teams, games] = await Promise.all([
      api.getTournamentMetadata(pk),
      api.getTournamentUsers(pk),
      api.getTournamentTeams(pk),
      api.getTournamentGames(pk),
    ]);

    // Check for stale response (navigation happened)
    if (thisLoadId !== loadId || get().tournament?.pk !== currentPk) return;

    set({
      tournament,
      users,
      teams,
      games,
      isLoadingTournament: false,
      isLoadingUsers: false,
      isLoadingTeams: false,
      isLoadingGames: false,
      dataVersion: Date.now(),
    });
  } catch (error) {
    if (thisLoadId !== loadId) return;  // Ignore stale errors

    set({
      loadError: { endpoint: 'batch', error },
      isLoadingTournament: false,
      isLoadingUsers: false,
      isLoadingTeams: false,
      isLoadingGames: false,
    });
  }
};
```

### Store Reset on Navigation

```typescript
// In TournamentDetailPage
useEffect(() => {
  return () => {
    useTournamentStore.getState().reset();
    useTeamDraftStore.getState().reset();
    useBracketStore.getState().reset();
    // Note: reset() increments activeConnectionId to invalidate in-flight handlers
  };
}, []);
```

---

## Migration Plan (Revised)

### Phase 1A: Backend Preparation

| Task | Description |
|------|-------------|
| 1A.1 | Add `@action` methods to `TournamentViewSet`: `metadata`, `users`, `teams`, `games`, `draft_state` |
| 1A.2 | Create `TournamentMetadataSerializer` and `TeamDraftStateSerializer` |
| 1A.3 | Add authentication check to `DraftConsumer` and `TournamentConsumer` |
| 1A.4 | Implement cascading `invalidate_obj()` calls in model save methods |
| 1A.5 | Add `sequence` field to WebSocket broadcast messages |
| 1A.6 | Move WebSocket broadcasts to `transaction.on_commit()` |

### Phase 1B: Frontend Infrastructure

| Task | Description |
|------|-------------|
| 1B.1 | Create `WebSocketManager` singleton with reference counting |
| 1B.2 | Create `useTournamentStore` with separate loading flags and error states |
| 1B.3 | Create `useTeamDraftStore` (NO syncToTournament, reads from tournament) |
| 1B.4 | Enhance `useHeroDraftStore` with WebSocketManager integration |
| 1B.5 | Revise `useBracketStore` to use polling with ETag (remove WebSocket) |
| 1B.6 | Add integration tests for store synchronization |

### Phase 2: Migration with Adapter

Create a facade/adapter to safely transition without data divergence:

```typescript
// transition/useTournamentData.ts
export function useTournamentData() {
  const legacyTournament = useUserStore(s => s.tournament);
  const newTournament = useTournamentStore(s => s.tournament);

  // During migration: prefer new store when populated
  const tournament = newTournament ?? legacyTournament;

  // Development warning for divergence
  if (process.env.NODE_ENV === 'development' && newTournament && legacyTournament) {
    if (newTournament.pk !== legacyTournament.pk) {
      console.warn('Tournament data divergence detected');
    }
  }

  return tournament;
}
```

Track each file's `useUserStore` usage and migrate to appropriate store:

| Current Access | Migrate To | Files Affected |
|----------------|------------|----------------|
| `useUserStore.tournament` | `useTournamentStore.tournament` | ~15 files |
| `useUserStore.teams` | `useTournamentStore.teams` | ~12 files |
| `useUserStore.draft` | `useTeamDraftStore.*` | ~10 files |
| `useUserStore.curDraftRound` | `useTeamDraftStore.currentRound` | ~8 files |
| `useUserStore.games` | `useTournamentStore.games` | ~6 files |
| `useUserStore.currentUser` | `useUserStore.currentUser` (stays) | ~25 files |
| `useUserStore.users` (global) | `useUserStore.users` (stays) | ~10 files |

### Phase 3: Cleanup

| Task | Description |
|------|-------------|
| 3.1 | Remove migration adapter after all components migrated |
| 3.2 | Remove tournament/draft/team data from `useUserStore` |
| 3.3 | Remove old full-recursive `fetchTournament` calls |
| 3.4 | Remove polling-based draft updates (replaced by WebSocket) |
| 3.5 | Update TypeScript types to enforce new patterns |
| 3.6 | Add DevTools middleware to all stores for debugging |

---

## Success Criteria

1. **Reduced bandwidth**: No more full tournament fetches during live drafts
2. **Clear separation**: Each store owns its domain
3. **Real-time updates**: WebSocket-first for active drafts
4. **No regressions**: All existing functionality preserved
5. **Type safety**: TypeScript enforces correct store usage
6. **No dirty reads**: Cache updates happen after transaction commit
7. **No circular dependencies**: Unidirectional data flow only

---

## Appendix: Review Findings

This design was reviewed by 4 specialist agents and synthesized by a 5th reviewer. Below are the key findings that shaped the revised design.

### Critical Issues Fixed

| Issue | Original Design | Fix Applied |
|-------|-----------------|-------------|
| **Cache inside transaction** | `cache.set()` inside `transaction.atomic()` | Moved to `transaction.on_commit()` |
| **Bidirectional sync** | `syncToTournament()` in draft/bracket stores | Removed - unidirectional flow only |
| **HTTP/WebSocket desync** | No sequence validation | Added `sequence` field and version tracking |

### High Priority Changes

| Issue | Change |
|-------|--------|
| Missing error states | Added `connectionError`, `reconnectAttempts`, `reconnect()` to all WebSocket stores |
| WebSocket reference counting | Created `WebSocketManager` singleton |
| `isLoading` object re-renders | Changed to separate boolean flags |
| Missing migration adapter | Added `useTournamentData()` facade for Phase 2 |
| No cascading invalidation | Added `invalidate_obj()` calls in model save methods |
| Partial load failures | Added batch loading with error state |
| WebSocket proliferation | Shared `WebSocketManager` with reference counting |
| Missing consumer auth | Added authentication check to `DraftConsumer`/`TournamentConsumer` |

### Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Use ViewSet `@action`** | Keeps API consistent, inherits permissions, reduces code |
| **Keep cacheops** | Existing pattern works, don't add manual caching complexity |
| **Polling for bracket** | Low-frequency updates don't justify WebSocket overhead |
| **Unidirectional data flow** | Prevents circular dependencies and state divergence |
| **Separate loading booleans** | Prevents re-render storms when any flag changes |

### Rejected Proposals

| Proposal | Reason |
|----------|--------|
| Separate BracketConsumer | Low-frequency updates - polling with ETag is sufficient |
| New standalone endpoints | ViewSet `@action` is cleaner, less code |
| Single multiplexed WebSocket | Reference counting solves immediate problem; multiplexing is optimization |
| Store proliferation concern | 5 well-scoped stores is appropriate for this domain |

### Testing Strategy

1. **Unit tests**: Each store testable via `store.getState()` without React
2. **Integration tests**: Use `createTestStores()` helper for store sync testing
3. **WebSocket tests**: Inject mock WebSocket via `WebSocketManager` config
4. **Race condition tests**: Simulate out-of-order messages with sequence numbers

### Critical Files for Implementation

| File | Purpose |
|------|---------|
| `backend/app/views_main.py` | Add `@action` methods to `TournamentViewSet` |
| `backend/app/serializers.py` | Add `TournamentMetadataSerializer`, `TeamDraftStateSerializer` |
| `backend/app/consumers.py` | Add auth checks, sequence numbers |
| `frontend/app/lib/websocketManager.ts` | New singleton with reference counting |
| `frontend/app/store/tournamentStore.ts` | Merge existing UI state with new data state |
| `frontend/app/store/userStore.ts` | Slim down to auth-only (~80 lines) |

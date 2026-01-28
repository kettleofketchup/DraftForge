# Zustand State Migration Plan

## Overview

This document details the migration from the monolithic `useUserStore` (440 lines, 87 files) to domain-specific stores created in Phase 1. The migration must be incremental, maintaining backward compatibility during the transition.

## Current State Analysis

### Files by Category

| Category | File Count | Target Store |
|----------|------------|--------------|
| User Data | 22 files | `useUserStore` (keep) |
| Tournament Data | 23 files | `useTournamentDataStore` |
| Draft Data | 28 files | `useTeamDraftStore` |
| Teams Data | 7 files | `useTournamentDataStore` |
| Games Data | 4 files | `useTournamentDataStore` |
| Organizations | 4 files | `useUserStore` (keep for now) |
| Leagues | 4 files | `useUserStore` (keep for now) |
| Bracket | 5 files | `useBracketStore` (already separate) |
| HeroDraft | 2 files | `useHeroDraftStore` (enhanced) |

### WebSocket Hooks to Replace

| Hook | Used In | Replace With |
|------|---------|--------------|
| `useHeroDraftWebSocket` | HeroDraftModal.tsx | `useHeroDraftStore.setDraftId()` |
| `useDraftWebSocket` | draftModal.tsx | `useTeamDraftStore.setDraftId()` |

---

## Migration Phases

### Phase 2A: Create Compatibility Layer (Week 1)

**Goal**: Allow gradual migration without breaking existing code.

#### Task 2A.1: Add Forwarding Methods to useUserStore

Add methods that delegate to new stores while maintaining API compatibility:

```typescript
// In useUserStore - add forwarding for tournament data
getTournamentFromNewStore: () => {
  return useTournamentDataStore.getState().tournament;
},
```

**Files to Modify**:
- `frontend/app/store/userStore.ts`

#### Task 2A.2: Create Migration Helper Hooks

Create hooks that provide unified access during migration:

```typescript
// frontend/app/hooks/useTournament.ts
export function useTournament(tournamentId: number) {
  // Phase 1: Use new store
  const newStore = useTournamentDataStore();

  // Phase 2: Fallback to old store if needed
  const oldStore = useUserStore();

  useEffect(() => {
    if (tournamentId) {
      newStore.setTournamentId(tournamentId);
    }
  }, [tournamentId]);

  return {
    tournament: newStore.tournament ?? oldStore.tournament,
    users: newStore.users.length > 0 ? newStore.users : (oldStore.tournament?.users ?? []),
    teams: newStore.teams.length > 0 ? newStore.teams : (oldStore.tournament?.teams ?? []),
    loading: newStore.loading.full,
    error: newStore.errors.full,
  };
}
```

**Files to Create**:
- `frontend/app/hooks/useTournament.ts`
- `frontend/app/hooks/useTeamDraft.ts`
- `frontend/app/hooks/useHeroDraft.ts`

---

### Phase 2B: Migrate Tournament Pages (Week 2)

**Goal**: Update tournament-related pages to use new stores.

#### Task 2B.1: TournamentDetailPage.tsx

**Current Usage**:
```typescript
const { tournament, setTournament } = useUserStore();
const { setLive, setActiveTab } = useTournamentStore();
```

**Migration**:
```typescript
const tournamentData = useTournamentDataStore();
const tournamentUI = useTournamentStore();

useEffect(() => {
  if (tournamentPk) {
    tournamentData.setTournamentId(tournamentPk);
  }
  return () => tournamentData.reset();
}, [tournamentPk]);
```

**File**: `frontend/app/pages/tournament/TournamentDetailPage.tsx`

#### Task 2B.2: PlayersTab.tsx

**Current Usage**:
```typescript
const { tournament, setTournament } = useUserStore();
```

**Migration**:
```typescript
const { users, loading, updateUsers } = useTournamentDataStore();
// Use tournament.users from new store instead of old
```

**File**: `frontend/app/pages/tournament/tabs/PlayersTab.tsx`

#### Task 2B.3: TeamsTab.tsx

**Current Usage**:
```typescript
const { tournament } = useUserStore();
const teams = tournament?.teams ?? [];
```

**Migration**:
```typescript
const { teams, loading } = useTournamentDataStore();
```

**File**: `frontend/app/pages/tournament/tabs/TeamsTab.tsx`

#### Task 2B.4: GamesTab.tsx

**Current Usage**:
```typescript
const { tournament } = useUserStore();
```

**Migration**:
```typescript
const { games, loading } = useTournamentDataStore();
```

**File**: `frontend/app/pages/tournament/tabs/GamesTab.tsx`

#### Task 2B.5: Tournament Modals

Update these files to use new store:
- `frontend/app/pages/tournament/modals/addUser.tsx`
- `frontend/app/pages/tournament/tabs/players/addPlayerDropdown.tsx`
- `frontend/app/pages/tournament/tabs/players/addPlayerModal.tsx`
- `frontend/app/pages/tournament/tabs/players/playerRemoveButton.tsx`
- `frontend/app/pages/tournament/tabs/teams/createTeamsButton.tsx`
- `frontend/app/pages/tournament/tabs/teams/randomTeamsModal.tsx`

---

### Phase 2C: Migrate Draft Components (Week 3)

**Goal**: Update team draft components to use `useTeamDraftStore`.

#### Task 2C.1: draftModal.tsx (Critical Path)

This is the most complex migration - 515 lines, uses 3 stores.

**Current Usage**:
```typescript
const {
  tournament, draft, setDraft, curDraftRound,
  setCurDraftRound, draftIndex, setDraftIndex, setAutoRefreshDraft
} = useUserStore();
const { live, livePolling, autoAdvance } = useTournamentStore();
const { events, isConnected, hasNewEvent } = useDraftWebSocket({...});
```

**Migration Strategy**:
1. Replace `useDraftWebSocket` with `useTeamDraftStore.setDraftId()`
2. Get draft state from `useTeamDraftStore` instead of `useUserStore`
3. Keep tournament UI flags in `useTournamentStore`

```typescript
const teamDraft = useTeamDraftStore();
const tournamentUI = useTournamentStore();

useEffect(() => {
  if (draft?.pk && tournament?.pk) {
    teamDraft.setDraftId(draft.pk, tournament.pk);
  }
  return () => teamDraft.reset();
}, [draft?.pk, tournament?.pk]);

// Use teamDraft.draft, teamDraft.events, teamDraft.wsState
// instead of useDraftWebSocket hook
```

**File**: `frontend/app/components/draft/draftModal.tsx`

#### Task 2C.2: Draft Round Components

Update these to use `useTeamDraftStore`:
- `frontend/app/components/draft/draftRoundView.tsx`
- `frontend/app/components/draft/roundView/TurnIndicator.tsx`
- `frontend/app/components/draft/roundView/captainCards.tsx`
- `frontend/app/components/draft/roundView/draftTable.tsx`
- `frontend/app/components/draft/roundView/choiceCard.tsx`
- `frontend/app/components/draft/roundView/draftRoundCard.tsx`
- `frontend/app/components/draft/roundView/currentTeam.tsx`

#### Task 2C.3: Draft Buttons/Controls

Update these files:
- `frontend/app/components/draft/buttons/DraftModerationDropdown.tsx`
- `frontend/app/components/draft/buttons/undoPickButton.tsx`
- `frontend/app/components/draft/buttons/initDraftDialog.tsx`
- `frontend/app/components/draft/buttons/draftStyleModal.tsx`
- `frontend/app/components/draft/buttons/choosePlayerButtons.tsx`

#### Task 2C.4: Draft Live/Polling

**Current**: `useDraftLive.ts` hook with polling

**Migration**: Remove polling, rely on WebSocket via store

```typescript
// OLD: useDraftLive.ts with setInterval polling
// NEW: useTeamDraftStore handles WebSocket automatically

// Components just subscribe to store state
const { draft, wsState } = useTeamDraftStore();
```

**Files**:
- `frontend/app/components/draft/hooks/useDraftLive.ts` (deprecate)
- `frontend/app/components/draft/liveView.tsx`

#### Task 2C.5: Remove useDraftWebSocket Hook

After all consumers migrated:
- Delete `frontend/app/components/draft/hooks/useDraftWebSocket.ts`
- Remove exports from any index files

---

### Phase 2D: Migrate HeroDraft Components (Week 4)

**Goal**: Update HeroDraft to use enhanced `useHeroDraftStore`.

#### Task 2D.1: HeroDraftModal.tsx

**Current Usage**:
```typescript
const { draft, tick, setDraft, setTick } = useHeroDraftStore();
const { isConnected, connectionError, reconnect } = useHeroDraftWebSocket({
  draftId,
  enabled: open,
  onStateUpdate: handleStateUpdate,
  onTick: handleTick,
  onEvent: handleEvent,
});
```

**Migration**:
```typescript
const heroDraft = useHeroDraftStore();

useEffect(() => {
  if (open && draftId) {
    heroDraft.setDraftId(draftId);
  } else {
    heroDraft.setDraftId(null);
  }
}, [open, draftId]);

// Store handles WebSocket internally
// Use heroDraft.wsState, heroDraft.draft, heroDraft.tick
```

**File**: `frontend/app/components/herodraft/HeroDraftModal.tsx`

#### Task 2D.2: HeroGrid.tsx

Already uses `useHeroDraftStore` - minimal changes needed.

**File**: `frontend/app/components/herodraft/HeroGrid.tsx`

#### Task 2D.3: Remove useHeroDraftWebSocket Hook

After HeroDraftModal migrated:
- Delete `frontend/app/components/herodraft/hooks/useHeroDraftWebSocket.ts`
- Remove exports

---

### Phase 2E: Update Bracket Integration (Week 4)

**Goal**: Ensure bracket store integrates with new tournament store.

#### Task 2E.1: BracketView.tsx

**Current Usage**:
```typescript
const { matches, isDirty, isLoading } = useBracketStore();
const { tournament } = useUserStore();
```

**Migration**:
```typescript
const bracket = useBracketStore();
const { tournamentId } = useTournamentDataStore();

useEffect(() => {
  if (tournamentId) {
    bracket.setTournamentId(tournamentId);
  }
}, [tournamentId]);
```

**File**: `frontend/app/components/bracket/BracketView.tsx`

#### Task 2E.2: Bracket Modals

Update to get tournament from new store:
- `frontend/app/components/bracket/modals/MatchStatsModal.tsx`
- `frontend/app/components/bracket/modals/LinkSteamMatchModal.tsx`

---

### Phase 2F: Cleanup useUserStore (Week 5)

**Goal**: Remove migrated state from useUserStore.

#### Task 2F.1: Remove Tournament State

Remove from `useUserStore`:
```typescript
// REMOVE these properties and methods:
tournament: TournamentType;
tournaments: TournamentType[];
tournamentPK: number | null;
setTournament: (tournament: TournamentType) => void;
setTournaments: (tournaments: TournamentType[]) => void;
getTournaments: () => Promise<void>;
getTournamentsBasic: () => Promise<void>;
getCurrentTournament: () => Promise<void>;
tournamentsByUser: (user: UserType) => TournamentType[];
addTournament: (tourn: TournamentType) => void;
delTournament: (tourn: TournamentType) => void;
```

#### Task 2F.2: Remove Draft State

Remove from `useUserStore`:
```typescript
// REMOVE these properties and methods:
draft: DraftType;
curDraftRound: DraftRoundType;
draftIndex: number;
autoRefreshDraft: (() => Promise<void>) | null;
setDraft: (draft: DraftType) => void;
setCurDraftRound: (round: DraftRoundType) => void;
setDraftIndex: (index: number) => void;
getDraft: () => Promise<void>;
getCurrentDraftRound: () => Promise<void>;
setAutoRefreshDraft: (refresh: (() => Promise<void>) | null) => void;
updateCurrentDraft: () => Promise<void>;
```

#### Task 2F.3: Remove Teams/Games State

Remove from `useUserStore`:
```typescript
// REMOVE these properties and methods:
team: TeamType;
teams: TeamType[];
game: GameType;
games: GameType[];
setTeam: (team: TeamType) => void;
setTeams: (teams: TeamType[]) => void;
getTeams: () => Promise<void>;
setGames: (games: GameType[]) => void;
getGames: () => Promise<void>;
```

#### Task 2F.4: Keep User-Specific State

**Keep** in `useUserStore`:
```typescript
// User authentication
currentUser: UserType;
setCurrentUser: (user: UserType) => void;
clearUser: () => void;
isStaff: () => boolean;
getCurrentUser: () => Promise<void>;
hasHydrated: boolean;
setHasHydrated: (hydrated: boolean) => void;

// Users list
users: UserType[];
selectedUser: UserType;
setUsers: (users: UserType[]) => void;
setUser: (user: UserType) => void;
addUser: (user: UserType) => void;
delUser: (user: UserType) => void;
getUsers: () => Promise<void>;
createUser: (user: UserType) => Promise<void>;
clearUsers: () => void;

// User search
userQuery: string;
addUserQuery: string;
setUserQuery: (query: string) => void;
setAddUserQuery: (query: string) => void;

// Discord users
discordUsers: GuildMembers;
selectedDiscordUser: GuildMember;
discordUserQuery: string;
setDiscordUser: (discordUser: GuildMember) => void;
setDiscordUsers: (users: GuildMembers) => void;
getDiscordUsers: () => Promise<void>;
setDiscordUserQuery: (query: string) => void;

// Selection
resetSelection: () => void;

// Error state
userAPIError: any;

// Organizations (keep for now)
organizations: OrganizationType[];
organization: OrganizationType | null;
setOrganizations, setOrganization, getOrganizations, getOrganization

// Leagues (keep for now)
leagues: LeagueType[];
league: LeagueType | null;
setLeagues, setLeague, getLeagues
```

---

## Migration Checklist

### Pre-Migration
- [ ] All Phase 1 stores created and tested
- [ ] Backend @action endpoints deployed
- [ ] WebSocketManager tested

### Phase 2A: Compatibility Layer
- [ ] Task 2A.1: Add forwarding methods to useUserStore
- [ ] Task 2A.2: Create migration helper hooks

### Phase 2B: Tournament Pages
- [ ] Task 2B.1: TournamentDetailPage.tsx
- [ ] Task 2B.2: PlayersTab.tsx
- [ ] Task 2B.3: TeamsTab.tsx
- [ ] Task 2B.4: GamesTab.tsx
- [ ] Task 2B.5: Tournament modals (6 files)

### Phase 2C: Draft Components
- [ ] Task 2C.1: draftModal.tsx
- [ ] Task 2C.2: Draft round components (7 files)
- [ ] Task 2C.3: Draft buttons/controls (5 files)
- [ ] Task 2C.4: Draft live/polling
- [ ] Task 2C.5: Remove useDraftWebSocket hook

### Phase 2D: HeroDraft Components
- [ ] Task 2D.1: HeroDraftModal.tsx
- [ ] Task 2D.2: HeroGrid.tsx
- [ ] Task 2D.3: Remove useHeroDraftWebSocket hook

### Phase 2E: Bracket Integration
- [ ] Task 2E.1: BracketView.tsx
- [ ] Task 2E.2: Bracket modals (2 files)

### Phase 2F: Cleanup
- [ ] Task 2F.1: Remove tournament state from useUserStore
- [ ] Task 2F.2: Remove draft state from useUserStore
- [ ] Task 2F.3: Remove teams/games state from useUserStore
- [ ] Task 2F.4: Verify user-specific state retained

---

## Testing Strategy

### Unit Tests
- Test each new store in isolation
- Test WebSocketManager subscription/unsubscription
- Test sequence number handling

### Integration Tests
- Test store interactions (tournament → team draft)
- Test WebSocket reconnection scenarios
- Test progressive loading flow

### E2E Tests (Playwright)
- Tournament page load with progressive data
- Draft flow with WebSocket updates
- HeroDraft ban/pick flow
- Bracket updates and polling

### Regression Tests
- Run full Playwright suite after each phase
- Focus on tournament, draft, and bracket tests

---

## Rollback Plan

Each phase can be rolled back independently:

1. **Phase 2A**: Remove forwarding methods and hooks
2. **Phase 2B-2E**: Revert component changes, keep using old store
3. **Phase 2F**: Cannot rollback after cleanup - ensure all tests pass first

**Recommendation**: Keep old code commented (not deleted) during Phase 2B-2E until Phase 2F.

---

## Risk Assessment

### High Risk
- **draftModal.tsx**: Complex multi-store orchestration, WebSocket timing
- **HeroDraftModal.tsx**: Real-time tick handling, captain connection states

### Medium Risk
- **TournamentDetailPage.tsx**: Deep-linking, URL sync
- **BracketView.tsx**: Polling coordination, ReactFlow integration

### Low Risk
- Tab components (PlayersTab, TeamsTab, GamesTab)
- Button/control components
- Modal components

---

## Success Metrics

1. **Bundle Size**: useUserStore reduced from 440 lines to ~150 lines
2. **Re-renders**: Measured reduction in component re-renders
3. **WebSocket Connections**: Single connection per channel (not per component)
4. **Load Time**: Progressive loading reduces initial page load
5. **Test Coverage**: All E2E tests passing

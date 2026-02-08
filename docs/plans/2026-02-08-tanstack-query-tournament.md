# TanStack Query Migration: Tournament + Bracket — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace manual axios + setInterval polling for tournament and bracket data with TanStack Query hooks, using the existing WebSocketManager singleton for real-time cache invalidation.

**Architecture:** TanStack Query owns server state (fetching, caching, polling, background refetch). Zustand keeps only client-side state — UI toggles in `tournamentStore`, bracket edits in `bracketStore`. A compatibility shim syncs query data to `userStore.setTournament()` so ~35 existing consumers keep working without changes.

**Tech Stack:** TanStack Query (already in project), WebSocketManager singleton (`~/lib/websocket`), Zustand (kept for client state)

---

## Important Context

- **Existing TanStack Query patterns**: See `frontend/app/hooks/useHeroDraft.ts` for the exact pattern to follow (query keys, mutations, `queryClient.setQueryData()`)
- **WebSocketManager**: Singleton at `frontend/app/lib/websocket/WebSocketManager.ts` — handles reconnection, exponential backoff, subscriber pattern, HMR cleanup
- **TournamentConsumer** (`backend/app/consumers.py`): Currently sends `initial_events` on connect and `draft_event` on channel messages. No `bracket_update` event type exists yet — WebSocket will invalidate tournament query on any message; bracket relies on `refetchInterval` for now
- **`livePolling` in tournamentStore**: Used by team draft (`draftModal.tsx`, `liveView.tsx`), NOT by bracket/tournament polling. **Do not remove.**
- **`mapApiMatchToMatch`**: Currently a private function inside `bracketStore.ts` (line 31). Must be exported or moved so the bracket query hook can use it.
- **TypeScript check**: Pre-existing errors exist in bracketAPI, editForm, heroDraftStore, dotaconstants, playwright configs. Only verify our new/modified files are clean.
- **`BracketResponse` type lie**: `bracketAPI.tsx` declares return type `BracketResponse` (with `matches: BracketMatch[]` camelCase), but `BracketResponseSchema.parse()` actually produces `BracketMatchDTO[]` (snake_case). The `as BracketMatchDTO[]` casts in `useBracket.ts` are intentional workarounds for this pre-existing mismatch.
- **Direct `fetchTournament` callers**: ~7 files (refreshTournamentHook, createTeamsButton, initDraftHook, etc.) call `fetchTournament()` directly and write to `userStore.setTournament()`. These bypass the query cache. The one-way shim (query -> userStore) means there can be a ~10s stale window in the query cache after these mutations. Acceptable for Phase 1; Phase 2 should migrate these to use `queryClient.setQueryData()`.

---

### Task 1: Create `useTournament` query hook

**Files:**
- Create: `frontend/app/hooks/useTournament.ts`

**Step 1: Create the hook file**

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchTournament, getTournaments, updateTournament } from '~/components/api/api';
import type { TournamentType, TournamentsType } from '~/components/tournament/types';

export function useTournament(pk: number | null) {
  return useQuery({
    queryKey: ['tournament', pk],
    queryFn: () => fetchTournament(pk!),
    enabled: !!pk,
    staleTime: 0, // Override global 5min default so invalidateQueries() triggers immediate refetch
    refetchInterval: 10_000,
  });
}

export function useTournaments(filters?: { organizationId?: number; leagueId?: number }) {
  return useQuery({
    queryKey: ['tournaments', filters],
    queryFn: () => getTournaments(filters),
  });
}

export function useUpdateTournament(pk: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<TournamentType>) => updateTournament(pk, data),
    onSuccess: (updated) => {
      queryClient.setQueryData(['tournament', pk], updated);
    },
  });
}
```

**Step 2: Verify types compile**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | grep -E "useTournament|hooks/useTournament"`
Expected: No errors from this file (pre-existing errors in other files are fine)

**Step 3: Commit**

```bash
git add frontend/app/hooks/useTournament.ts
git commit -m "feat: add useTournament TanStack Query hook"
```

---

### Task 2: Create `useTournamentSocket` WebSocket hook

**Files:**
- Create: `frontend/app/hooks/useTournamentSocket.ts`

**Step 1: Create the hook file**

```typescript
import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getWebSocketManager } from '~/lib/websocket';
import { getLogger } from '~/lib/logger';

const log = getLogger('useTournamentSocket');

/**
 * Connects to the TournamentConsumer WebSocket and invalidates
 * TanStack Query cache on server events. The refetchInterval on
 * each query acts as a fallback if the WebSocket disconnects.
 */
export function useTournamentSocket(tournamentId: number | null) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!tournamentId) return;

    const manager = getWebSocketManager();
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/api/tournament/${tournamentId}/`;
    const connId = manager.connect(url);

    const unsub = manager.subscribe(connId, (message) => {
      const msg = message as { type: string };
      log.debug('Tournament WS event', msg.type);

      // Skip initial_events — no state change on connect
      if (msg.type === 'initial_events') return;

      // Invalidate tournament query on any event
      queryClient.invalidateQueries({ queryKey: ['tournament', tournamentId] });

      // Future: when backend sends bracket_update events, also invalidate bracket
      if (msg.type === 'bracket_update') {
        queryClient.invalidateQueries({ queryKey: ['bracket', tournamentId] });
      }
    });

    return () => unsub(); // auto-disconnects when no subscribers remain
  }, [tournamentId, queryClient]);
}
```

**Step 2: Verify types compile**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | grep -E "useTournamentSocket|hooks/useTournamentSocket"`
Expected: No errors from this file

**Step 3: Commit**

```bash
git add frontend/app/hooks/useTournamentSocket.ts
git commit -m "feat: add useTournamentSocket WebSocket-to-query bridge"
```

---

### Task 3: Migrate `TournamentDetailPage` to `useTournament`

**Files:**
- Modify: `frontend/app/pages/tournament/TournamentDetailPage.tsx`

**Step 1: Replace manual fetch/poll with query hook + compatibility shim**

Remove these imports:
- `useState` (no longer needed for loading/error)
- `axios` import (`~/components/api/axios`)

Add these imports:
- `import { useTournament } from '~/hooks/useTournament';`
- `import { useTournamentSocket } from '~/hooks/useTournamentSocket';`

Replace the component body. The full updated file:

```typescript
import React, { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { useTournamentStore } from '~/store/tournamentStore';
import { useUserStore } from '~/store/userStore';
import { useTournament } from '~/hooks/useTournament';
import { useTournamentSocket } from '~/hooks/useTournamentSocket';
import type { TournamentType } from '~/components/tournament/types';
import TournamentTabs from './tabs/TournamentTabs';

import { getLogger } from '~/lib/logger';
const log = getLogger('TournamentDetailPage');

export const TournamentDetailPage: React.FC = () => {
  const { pk, '*': slug } = useParams<{ pk: string; '*': string }>();
  const navigate = useNavigate();
  const pkNum = pk ? parseInt(pk, 10) : null;

  // TanStack Query for tournament data
  const { data: tournament, isLoading, error } = useTournament(
    pkNum && !Number.isNaN(pkNum) ? pkNum : null,
  );

  // WebSocket for real-time cache invalidation
  useTournamentSocket(pkNum && !Number.isNaN(pkNum) ? pkNum : null);

  // Compatibility shim: sync query data to userStore for ~35 existing consumers
  // NOTE: This is one-way (query -> userStore). Files that call fetchTournament()
  // directly and write to userStore will be overwritten on next refetch (~10s).
  useEffect(() => {
    if (tournament) {
      useUserStore.getState().setTournament(tournament);
    }
    return () => {
      // Clear stale tournament when navigating away so children don't see old data
      useUserStore.getState().setTournament(null as unknown as TournamentType);
    };
  }, [tournament]);

  // UI state from tournamentStore
  const setLive = useTournamentStore((state) => state.setLive);
  const setActiveTab = useTournamentStore((state) => state.setActiveTab);
  const setAutoAdvance = useTournamentStore((state) => state.setAutoAdvance);
  const setPendingDraftId = useTournamentStore((state) => state.setPendingDraftId);
  const setPendingMatchId = useTournamentStore((state) => state.setPendingMatchId);

  // Parse URL slug for tabs and deep-linking
  useEffect(() => {
    const parts = slug?.split('/') || [];
    let tab = parts[0] || 'players';
    if (tab === 'games') {
      tab = 'bracket';
    }
    const isLive = parts[1] === 'draft';
    const draftId = parts[1] === 'draft' && parts[2] ? parseInt(parts[2], 10) : null;
    const matchId = parts[1] === 'match' && parts[2] ? parts[2] : null;

    // Redirect /tournament/:pk/bracket/draft/:draftId to /herodraft/:draftId
    if (draftId && !Number.isNaN(draftId)) {
      navigate(`/herodraft/${draftId}`, { replace: true });
      return;
    }

    setActiveTab(tab);
    setPendingDraftId(Number.isNaN(draftId) ? null : draftId);
    setPendingMatchId(matchId);
    setLive(isLive);
    if (isLive) {
      setAutoAdvance(true);
    }
  }, [slug, setActiveTab, setLive, setAutoAdvance, setPendingDraftId, setPendingMatchId, navigate]);

  // Set org context from tournament
  useEffect(() => {
    if (tournament?.organization_pk) {
      useOrgStore.getState().getOrganization(tournament.organization_pk);
    } else {
      useOrgStore.getState().setCurrentOrg(null);
    }
    return () => {
      useOrgStore.getState().reset();
    };
  }, [tournament?.organization_pk]);

  // Set league context from tournament
  useEffect(() => {
    if (tournament?.league_pk) {
      useLeagueStore.getState().getLeague(tournament.league_pk);
    } else {
      useLeagueStore.getState().setCurrentLeague(null);
    }
    return () => {
      useLeagueStore.getState().reset();
    };
  }, [tournament?.league_pk]);

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-screen">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex justify-center items-center h-screen">
        <div role="alert" className="alert alert-error">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="stroke-current shrink-0 h-6 w-6"
            fill="none"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span>Failed to load tournament details. Please try again later.</span>
        </div>
      </div>
    );
  }

  if (!tournament) {
    return (
      <div className="flex justify-center items-center h-screen">
        Tournament not found.
      </div>
    );
  }

  const getDate = () => {
    let date = tournament.date_played
      ? (() => {
          const [year, month, day] = tournament.date_played.split('-');
          return `${month}-${day}`;
        })()
      : '';
    return `${date || ''}`;
  };

  const tournamentName = () => {
    if (!tournament.name) {
      return <></>;
    }
    return (
      <h1 className="text-3xl font-bold mb-4" data-testid="tournamentTitle">
        {tournament.name}
      </h1>
    );
  };

  const title = () => {
    return (
      <>
        <div className="flex flex-row items-center mb-2">
          {tournamentName()}
          <span className="ml-4 text-base text-base-content/50 font-normal">
            played on {getDate()}
          </span>
        </div>
      </>
    );
  };

  return (
    <div
      className="container px-1 sm:mx-auto sm:p-4"
      data-testid="tournamentDetailPage"
    >
      {title()}
      <TournamentTabs />
    </div>
  );
};

export default TournamentDetailPage;
```

**Step 2: Verify types compile**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | grep "TournamentDetailPage"`
Expected: No errors from this file

**Step 3: Smoke test — tournament page loads**

Run: `just test::pw::spec tournament`
Expected: Existing tournament tests pass (page loads, tabs work, data displays)

**Step 4: Commit**

```bash
git add frontend/app/pages/tournament/TournamentDetailPage.tsx
git commit -m "feat: migrate TournamentDetailPage to useTournament query hook"
```

---

### Task 4: Export `mapApiMatchToMatch` from bracketStore

The bracket query hook needs to map API responses to frontend types. This function is currently private in `bracketStore.ts`.

**Files:**
- Modify: `frontend/app/store/bracketStore.ts` (lines 31-83)

**Step 1: Export the function and its helper**

Add `export` to the `mapApiMatchToMatch` function (line 31) and `generateMatchId` function (line 16):

Change:
```typescript
function generateMatchId(bracketType: string, round: number, position: number): string {
```
To:
```typescript
export function generateMatchId(bracketType: string, round: number, position: number): string {
```

Change:
```typescript
function mapApiMatchToMatch(apiMatch: ApiBracketMatch, allMatches: ApiBracketMatch[]): BracketMatch {
```
To:
```typescript
export function mapApiMatchToMatch(apiMatch: ApiBracketMatch, allMatches: ApiBracketMatch[]): BracketMatch {
```

**Step 2: Verify types compile**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | grep "bracketStore"`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/app/store/bracketStore.ts
git commit -m "refactor: export mapApiMatchToMatch from bracketStore"
```

---

### Task 5: Create `useBracket` query hook

**Files:**
- Create: `frontend/app/hooks/useBracket.ts`

**Step 1: Create the hook file**

```typescript
import { useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { loadBracket as loadBracketAPI, saveBracket as saveBracketAPI } from '~/components/api/bracketAPI';
import { useBracketStore, mapApiMatchToMatch } from '~/store/bracketStore';
import type { BracketMatch } from '~/components/bracket/types';
import type { BracketMatchDTO } from '~/components/bracket/schemas';
import { getLogger } from '~/lib/logger';

const log = getLogger('useBracket');

/**
 * Fetches bracket data via TanStack Query and seeds the Zustand bracketStore.
 * Polling pauses automatically when the bracket has unsaved edits (isDirty).
 */
export function useBracketQuery(tournamentId: number | null) {
  const isDirty = useBracketStore((state) => state.isDirty);
  const previousDataRef = useRef<string | null>(null);

  const query = useQuery({
    queryKey: ['bracket', tournamentId],
    queryFn: () => loadBracketAPI(tournamentId!),
    enabled: !!tournamentId,
    staleTime: 0, // Override global 5min default so invalidateQueries() triggers immediate refetch
    refetchInterval: isDirty ? false : 5_000,
  });

  // Seed Zustand store from query data (replaces bracketStore.loadBracket logic)
  useEffect(() => {
    if (!query.data || isDirty) return;

    // NOTE: BracketResponse.matches is typed as BracketMatch[] but at runtime
    // is actually BracketMatchDTO[] (snake_case) due to Zod schema parsing.
    // This cast is a workaround for a pre-existing type mismatch in bracketAPI.tsx.
    const apiMatches = query.data.matches as BracketMatchDTO[];

    // Handle empty bracket — use getState() to avoid subscribing to matches
    if (apiMatches.length === 0) {
      if (useBracketStore.getState().matches.length > 0) {
        useBracketStore.setState({
          matches: [],
          nodes: [],
          edges: [],
          isDirty: false,
          isVirtual: true,
        });
        log.debug('Bracket cleared (no matches from backend)');
      }
      previousDataRef.current = null;
      return;
    }

    // Map API matches to frontend format
    const mappedMatches = apiMatches.map((m) => mapApiMatchToMatch(m, apiMatches));

    // Compare to avoid unnecessary rerenders (same logic as old bracketStore.loadBracket)
    const newKey = mappedMatches
      .map((m) => `${m.id}-${m.winner}-${m.status}-${m.radiantTeam?.pk}-${m.direTeam?.pk}`)
      .join('|');

    if (newKey === previousDataRef.current) return;
    previousDataRef.current = newKey;

    useBracketStore.setState({
      matches: mappedMatches,
      isDirty: false,
      isVirtual: false,
    });
    log.debug('Bracket updated from query', { matchCount: mappedMatches.length });
  }, [query.data, isDirty]);

  return query;
}

/**
 * Mutation for saving bracket. Invalidates the bracket query cache on success.
 */
export function useSaveBracket(tournamentId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (matches: BracketMatch[]) => saveBracketAPI(tournamentId, matches),
    onSuccess: (data) => {
      // Update Zustand store with saved matches (they now have backend PKs)
      const apiMatches = data.matches as BracketMatchDTO[];
      const savedMatches = apiMatches.map((m) => mapApiMatchToMatch(m, apiMatches));
      useBracketStore.setState({
        matches: savedMatches,
        isDirty: false,
        isVirtual: false,
      });
      // Invalidate to ensure cache is fresh
      queryClient.invalidateQueries({ queryKey: ['bracket', tournamentId] });
      log.debug('Bracket saved', { matchCount: savedMatches.length });
    },
    onError: (error) => {
      log.error('Failed to save bracket', error);
    },
  });
}
```

**Step 2: Verify types compile**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | grep -E "useBracket|hooks/useBracket"`
Expected: No errors from this file

**Step 3: Commit**

```bash
git add frontend/app/hooks/useBracket.ts
git commit -m "feat: add useBracketQuery and useSaveBracket TanStack Query hooks"
```

---

### Task 6: Slim down `bracketStore` — remove fetch/poll/loading

**Files:**
- Modify: `frontend/app/store/bracketStore.ts`

**Step 1: Remove server-state concerns from the store**

Remove from the `BracketStore` interface:
- `isLoading: boolean;`
- `pollInterval: ReturnType<typeof setInterval> | null;`
- `loadBracket: (tournamentId: number) => Promise<void>;`
- `saveBracket: (tournamentId: number) => Promise<void>;` (replaced by `useSaveBracket` mutation in Task 9)
- `startPolling: (tournamentId: number, intervalMs?: number) => void;`
- `stopPolling: () => void;`

Remove from the store implementation:
- `isLoading: false,`
- `pollInterval: null,`
- The entire `loadBracket` method (lines 271-343)
- The entire `saveBracket` method (lines 250-269) — replaced by `useSaveBracket` mutation
- The entire `startPolling` method (lines 358-369)
- The entire `stopPolling` method (lines 371-379)

Update `resetBracket` — remove `stopPolling()` call, set `isDirty: true` to prevent the query from re-seeding backend data before the user generates a new bracket:

```typescript
resetBracket: () => {
  log.debug('Resetting bracket');
  set({
    matches: [],
    nodes: [],
    edges: [],
    isDirty: true, // Prevents useBracketQuery from re-seeding until user saves or generates
    isVirtual: true,
  });
},
```

**Step 2: Verify types compile**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | grep "bracketStore"`
Expected: Errors will appear in `BracketView.tsx`, `GamesTab.tsx`, `MatchStatsModal.tsx`, and `BracketToolbar.tsx` referencing removed methods — that's expected and fixed in Tasks 7-10

**Step 3: Commit**

```bash
git add frontend/app/store/bracketStore.ts
git commit -m "refactor: remove fetch/poll/loading from bracketStore (moved to TanStack Query)"
```

---

### Task 7: Migrate `BracketView` to use bracket query

**Files:**
- Modify: `frontend/app/components/bracket/BracketView.tsx`

**Step 1: Replace polling setup with query hook**

Add import at top:
```typescript
import { useBracketQuery } from '~/hooks/useBracket';
```

In `BracketFlowInner`, replace the `isLoading` selector:
```typescript
// OLD:
const isLoading = useBracketStore((state) => state.isLoading);

// NEW:
// Note: TanStack Query isLoading is only true on initial fetch (no cached data).
// Use isFetching if you need to know about background refetches too.
const { isLoading, data: bracketData } = useBracketQuery(tournamentId);
```

Also update the empty-bracket guard to prevent a flash of "No bracket generated yet" between query resolution and Zustand seeding:
```typescript
// OLD:
{matches.length === 0 && !isLoading && (
  <div>No bracket generated yet.</div>
)}

// NEW — also check if query data has matches (useEffect hasn't seeded Zustand yet):
{matches.length === 0 && !isLoading && !bracketData?.matches?.length && (
  <div>No bracket generated yet.</div>
)}
```

Remove these two `useEffect` blocks entirely (lines ~210-234):
```typescript
// DELETE: Load bracket on mount effect
// Track current tournament to prevent unnecessary reloads
const currentTournamentRef = useRef<number | null>(null);

useEffect(() => {
  if (currentTournamentRef.current === tournamentId) return;
  currentTournamentRef.current = tournamentId;
  useBracketStore.getState().loadBracket(tournamentId);
  return () => useBracketStore.getState().stopPolling();
}, [tournamentId]);

// DELETE: Start polling effect
useEffect(() => {
  const store = useBracketStore.getState();
  if (!isDirty) {
    if (!store.pollInterval) {
      store.startPolling(tournamentId, 5000);
    }
  } else {
    store.stopPolling();
  }
  return () => useBracketStore.getState().stopPolling();
}, [isDirty, tournamentId]);
```

Also remove `currentTournamentRef` since it's no longer needed.

The `useBracketQuery` hook (from Task 5) handles both fetching and seeding the Zustand store.

**Step 2: Verify types compile**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | grep "BracketView"`
Expected: No errors from this file

**Step 3: Commit**

```bash
git add frontend/app/components/bracket/BracketView.tsx
git commit -m "feat: migrate BracketView from manual polling to useBracketQuery"
```

---

### Task 8: Migrate `GamesTab` bracket reload

**Files:**
- Modify: `frontend/app/pages/tournament/tabs/GamesTab.tsx`

**Step 1: Replace `loadBracket` call with query invalidation**

Remove import:
```typescript
import { useBracketStore } from '~/store/bracketStore';
```

Add imports:
```typescript
import { useQueryClient } from '@tanstack/react-query';
```

In the component, add:
```typescript
const queryClient = useQueryClient();
```

Replace `handleAutoAssignComplete`:
```typescript
// OLD:
const handleAutoAssignComplete = useCallback(() => {
  if (tournament?.pk) {
    useBracketStore.getState().loadBracket(tournament.pk);
  }
}, [tournament?.pk]);

// NEW:
const handleAutoAssignComplete = useCallback(() => {
  if (tournament?.pk) {
    queryClient.invalidateQueries({ queryKey: ['bracket', tournament.pk] });
  }
}, [tournament?.pk, queryClient]);
```

**Step 2: Verify types compile**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | grep "GamesTab"`
Expected: No errors from this file

**Step 3: Commit**

```bash
git add frontend/app/pages/tournament/tabs/GamesTab.tsx
git commit -m "feat: migrate GamesTab to invalidate bracket query instead of direct store call"
```

---

### Task 9: Migrate `MatchStatsModal` to use query invalidation

**Files:**
- Modify: `frontend/app/components/bracket/modals/MatchStatsModal.tsx`

**Step 1: Replace `loadBracket` calls with query invalidation**

Add import:
```typescript
import { useQueryClient } from '@tanstack/react-query';
```

In the component, add:
```typescript
const queryClient = useQueryClient();
```

Remove the `loadBracket` selector:
```typescript
// DELETE:
const loadBracket = useBracketStore((state) => state.loadBracket);
```

Replace both call sites:
```typescript
// OLD (line 87, handleLinkUpdated):
loadBracket(tournament.pk);

// NEW:
queryClient.invalidateQueries({ queryKey: ['bracket', tournament.pk] });

// OLD (line 133, after createDraftMutation):
loadBracket(tournament.pk);

// NEW:
queryClient.invalidateQueries({ queryKey: ['bracket', tournament.pk] });
```

**Step 2: Verify types compile**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | grep "MatchStatsModal"`
Expected: No errors from this file

**Step 3: Commit**

```bash
git add frontend/app/components/bracket/modals/MatchStatsModal.tsx
git commit -m "feat: migrate MatchStatsModal to invalidate bracket query"
```

---

### Task 10: Migrate `BracketToolbar` save to mutation

**Files:**
- Modify: `frontend/app/components/bracket/controls/BracketToolbar.tsx`

**Step 1: Replace `saveBracket` store action with mutation**

Add import:
```typescript
import { useSaveBracket } from '~/hooks/useBracket';
```

In the component, destructure `saveBracket` from the mutation instead of from the store:

```typescript
// OLD:
const { generateBracket, reseedBracket, saveBracket, resetBracket, isLoading, isDirty, isVirtual } =
  useBracketStore();

// NEW:
const { generateBracket, reseedBracket, resetBracket, isDirty, isVirtual } =
  useBracketStore();
const saveMutation = useSaveBracket(tournamentId);
```

Replace `handleSave`:
```typescript
// OLD:
const handleSave = () => {
  saveBracket(tournamentId);
};

// NEW:
const handleSave = () => {
  saveMutation.mutate(useBracketStore.getState().matches);
};
```

In the JSX, replace the save button's loading prop:
```typescript
// OLD (line ~117):
loading={isLoading}

// NEW:
loading={saveMutation.isPending}
```

**Step 2: Verify types compile**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | grep "BracketToolbar"`
Expected: No errors from this file

**Step 3: Commit**

```bash
git add frontend/app/components/bracket/controls/BracketToolbar.tsx
git commit -m "feat: migrate BracketToolbar save to useSaveBracket mutation"
```

---

### Task 11: Run full E2E test suite

**Step 1: Run Playwright tests**

Run: `just test::pw::headless`
Expected: All tournament and bracket tests pass

**Step 2: If tests fail, debug and fix**

Common issues to watch for:
- Timing: TanStack Query may refetch faster/slower than the old `setInterval` — adjust `refetchInterval` if needed
- Data shape: Ensure `useTournament` returns the same `TournamentType` that `useUserStore(s => s.tournament)` provided
- Bracket seeding: Ensure `useBracketQuery` seeds the Zustand store before components try to read `matches`

**Step 3: Final commit**

```bash
git add -A
git commit -m "fix: address E2E test issues from TanStack Query migration"
```

---

## Summary

| Task | Description | New/Modify | Status |
|------|-------------|------------|--------|
| 1 | Create `useTournament` query hook | Create | Done |
| 2 | Create `useTournamentSocket` WebSocket hook | Create | Done |
| 3 | Migrate `TournamentDetailPage` | Modify | Done |
| 4 | Export `mapApiMatchToMatch` | Modify | Done |
| 5 | Create `useBracket` query hook | Create | Done |
| 6 | Slim down `bracketStore` (remove fetch/poll/loading/save) | Modify | Done |
| 7 | Migrate `BracketView` | Modify | Done |
| 8 | Migrate `GamesTab` | Modify | Done |
| 9 | Migrate `MatchStatsModal` | Modify | Done |
| 10 | Migrate `BracketToolbar` | Modify | Done |
| 11 | Run full E2E tests | Verify | Done |

**Not changed (Phase 1):** ~35 files reading `useUserStore(s => s.tournament)`, `userStore.ts`, `tournamentStore.ts` `livePolling`

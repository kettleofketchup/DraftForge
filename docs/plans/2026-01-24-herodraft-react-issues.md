# HeroDraft React Issues and Gotchas

Date: 2026-01-24

## Summary

Analysis of React patterns in the HeroDraft components for the tournament bracket page. This documents potential issues, anti-patterns, and areas that could cause bugs.

---

## Critical Issues

### 1. Race Condition in `toast.promise` with `.finally()`

**File:** `MatchStatsModal.tsx:72-107`

**Problem:** The `toast.promise()` returns a promise, but `.finally()` is chained on the outer `toast.promise()` call, not on the inner async function. This means `setIsCreatingDraft(false)` may execute before the promise completes.

```typescript
toast.promise(
  (async () => { ... })(),  // Inner promise
  { loading, success, error }
).finally(() => {
  setIsCreatingDraft(false);  // This runs when toast.promise resolves, not inner promise
});
```

**Impact:** The loading state may be cleared prematurely, allowing double-clicks.

**Fix:** Move the `finally` inside the async IIFE or use try/finally within it.

---

### 2. Stale Closure in `handleEvent` Callback

**File:** `HeroDraftModal.tsx:70-106`

**Problem:** `handleEvent` is memoized with an empty dependency array `[]`, but it uses `heroes` from `dotaconstants`. If `heroes` were to change (unlikely but possible with dynamic imports), the callback would use stale data.

```typescript
const handleEvent = useCallback((event: HeroDraftEvent) => {
  const getHeroName = (heroId: number | undefined): string => {
    const hero = Object.values(heroes).find(...);  // Captured at mount time
    ...
  };
}, []);  // Empty deps - never updates
```

**Impact:** Minor - `heroes` is a static import so this is unlikely to cause issues.

**Recommendation:** Add `heroes` to deps if it ever becomes dynamic.

---

### 3. Conditional Hook-like Pattern in `DraftTopBar`

**File:** `DraftTopBar.tsx:52-54`

**Problem:** Computing `activeTeamId` differently based on `draft.state` could cause inconsistent behavior:

```typescript
const activeTeamId = draft.state === "drafting"
  ? (tick?.active_team_id ?? currentRound?.draft_team ?? null)
  : null;
```

**Impact:** Minor - This is actually fine as it's not a hook, but the fallback chain `tick?.active_team_id ?? currentRound?.draft_team` mixes data sources which could cause UI flickering if tick and round data temporarily disagree.

---

## Medium Issues

### 4. Missing `useCallback` for `onHeroClick` Handler

**File:** `HeroGrid.tsx:112-124`

**Problem:** The inline `onClick` handler creates a new function on every render, which could cause unnecessary re-renders of child components if they're memoized.

```typescript
onClick={() => {
  if (!disabled && available) {
    setSelectedHeroId(hero.id);
    onHeroClick(hero.id);
  }
}}
```

**Impact:** Performance - causes new function reference on every render for ~120+ hero buttons.

**Recommendation:** Extract to a memoized handler or use `useCallback`.

---

### 5. Polling Not Cancelled When User Makes Changes

**File:** `BracketView.tsx:206-214`

**Problem:** The polling effect checks `isDirty` but if a poll request is already in-flight when `isDirty` becomes true, the response will still arrive and could overwrite state.

```typescript
useEffect(() => {
  if (!isDirty) {
    startPolling(tournamentId, 5000);
  } else {
    stopPolling();  // Stops interval, but doesn't cancel in-flight request
  }
}, [isDirty, ...]);
```

**Impact:** Already fixed in `bracketStore.ts` - the `loadBracket` function now checks if `isDirty` changed during fetch.

---

### 6. Missing Error Boundary Around HeroDraftModal

**File:** `BracketView.tsx:554-566`

**Problem:** If `HeroDraftModal` throws during render (e.g., malformed data), it will crash the entire bracket view.

```typescript
{heroDraftId && (
  <HeroDraftModal
    draftId={heroDraftId}
    open={showHeroDraftModal}
    onClose={...}
  />
)}
```

**Recommendation:** Wrap in an error boundary to isolate failures.

---

### 7. WebSocket Reconnect Could Cause State Desync

**File:** `useHeroDraftWebSocket.ts:192-198`

**Problem:** On reconnect after unexpected close, the WebSocket reconnects after 3 seconds. During this time, events are missed. The `initial_state` message on reconnect should reset state, but if the reconnect happens during a user action, there could be a race.

```typescript
if (closeEvent.code !== 1000 && shouldConnectRef.current) {
  reconnectTimeoutRef.current = setTimeout(() => {
    connect();
  }, 3000);
}
```

**Impact:** Medium - User could submit a pick, WebSocket disconnects, reconnects with stale state showing pick not submitted.

**Recommendation:** Track pending operations and reconcile after reconnect.

---

## Minor Issues

### 8. Duplicate State Between `heroDraftStore` and `HeroDraftModal`

**Problem:** `confirmHeroId` and `isSubmitting` are local state in `HeroDraftModal`, while `selectedHeroId` is in the store. This split makes state management harder to reason about.

**Files:**
- `HeroDraftModal.tsx:51-52` - local state
- `heroDraftStore.ts:8` - store state

**Recommendation:** Move all related state to one location (preferably the store).

---

### 9. Potential Memory Leak in Hero Map Creation

**File:** `DraftPanel.tsx:19-26`

**Problem:** The hero map is created at module load time, which is fine, but if this module is ever dynamically imported multiple times, it would create duplicate maps.

```typescript
const heroByIdMap = new Map<number, {...}>();
Object.values(heroes).forEach((hero: any) => {
  heroByIdMap.set(hero.id, {...});
});
```

**Impact:** Minor - unlikely with current setup.

---

### 10. `useMemo` Dependencies Could Be More Granular

**File:** `DraftTopBar.tsx:72-86`

**Problem:** `teamAProgress` and `teamBProgress` depend on `draft.rounds`, which changes on every round completion. This causes re-computation even when the specific team's progress hasn't changed.

```typescript
const teamAProgress = useMemo(() => {
  const completed = draft.rounds.filter(r => r.draft_team === teamA?.id && r.state === "completed").length;
  ...
}, [draft.rounds, teamA?.id]);  // draft.rounds changes frequently
```

**Recommendation:** Consider deriving from a more stable source or using a selector pattern.

---

### 11. Missing Key Prop Warning Potential

**File:** `HeroDraftModal.tsx:291-305`

**Problem:** Using `team.id` as key in map is fine, but if `draft.draft_teams` ever contains duplicates (shouldn't happen), it would cause React warnings.

---

### 12. Unnecessary Re-renders from Store Selectors

**Files:** Multiple

**Good Pattern (already used):**
```typescript
const draft = useHeroDraftStore((state) => state.draft);
const tick = useHeroDraftStore((state) => state.tick);
```

**Potential Issue:** Some components select the entire `draft` object, causing re-renders on any draft change even if only using a subset of fields.

---

## Recommendations Summary

| Priority | Issue | Action |
|----------|-------|--------|
| High | Race condition in toast.promise | Fix `.finally()` placement |
| High | Missing error boundary | Add around HeroDraftModal |
| Medium | WebSocket reconnect state desync | Add pending operation tracking |
| Medium | Inline onClick handlers | Extract to useCallback |
| Low | Duplicate state locations | Consolidate to store |
| Low | useMemo granularity | Use selectors for derived state |

---

## Testing Implications

The test failures (`two-captains-full-draft` and `timeout-auto-random`) are likely related to:

1. **Pause state handling** - Draft gets stuck in "paused" when it shouldn't
2. **WebSocket state sync** - UI not updating when backend state changes
3. **Race between tick and state updates** - Timer data and draft state temporarily inconsistent

These are likely backend/WebSocket issues rather than pure React problems.

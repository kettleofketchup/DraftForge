---
applyTo: "frontend/app/store/**/*.ts"
---

# Zustand stores

Canonical: global `zustand` skill. DraftForge stores live in `frontend/app/store/` (`userStore`, `orgStore`, `leagueStore`, `tournamentStore`, `bracketStore`, `heroDraftStore`, `draftWebSocketStore`, `pageNavStore`, `gameTypeStore`, `userCacheStore`).

## Store definition

- **Typed via a state interface, created with `create<State>()`**. Untyped `create(...)` defeats the type system for every consumer.
- **One concern per store.** Don't conflate user identity with tournament navigation — that's why we have multiple stores. If a new piece of state doesn't fit any existing store, add a new file in `store/` rather than expanding an existing one.
- **Async actions live on the store**, not in components. The component calls `useStore.getState().fetchX()`; the store handles fetch + error + loading state.
- **Persisted state uses the `persist` middleware** with an explicit `name` and `partialize` so we don't serialize huge derived blobs into localStorage.

## Consuming from components

- **Always select specific state**: `useStore((s) => s.user)` — never `useStore()` (the whole store), which re-renders the component on every state change.
- **Multi-field selectors must use `useShallow`** from `zustand/react/shallow`:
  ```ts
  import { useShallow } from 'zustand/react/shallow';
  const { user, org } = useStore(useShallow((s) => ({ user: s.user, org: s.org })));
  ```
  Otherwise the returned object identity changes every render and you get an infinite loop.
- **Reading state outside React (event handlers, async callbacks) uses `useStore.getState()`** — don't call the hook outside a component.

## Outside the `frontend/app/store/` folder

Components that *consume* stores live outside this `applyTo` scope; the React / shadcn / brand instructions cover them. Rules in this file are scoped to the store definitions themselves.

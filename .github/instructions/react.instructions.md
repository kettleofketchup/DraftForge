---
applyTo: "frontend/**/*.{ts,tsx}"
---

# React patterns

Canonical: global `react` skill. DraftForge frontend is **Vite + React Router v7** — there are no Server Components and no `'use client'` directive. Every component is a Client Component.

## Hooks

- **No conditional hooks.** Hook calls must run in the same order on every render — never call inside `if` / loops / early returns.
- **`useEffect` must return a cleanup when it subscribes / opens a timer / opens a WebSocket.** Memory leaks here cause flaky tests and stale state on hot-reload.
- **`useMemo` / `useCallback` only when there's a measured reason** — referenced as a stable dep elsewhere, expensive computation, or to satisfy a child's memoization contract. Don't wrap every value.
- **Prefer React 19 hooks where applicable**: `useTransition` for non-urgent state updates, `useOptimistic` for optimistic UI, `use()` for unwrapping context or a promise passed as a prop.

## Components

- **Functional components only.** No class components in new code.
- **Component files export the component as a named export** matching the filename (PascalCase). Default-exporting components makes them harder to grep and refactor.
- **Keep components small and single-purpose.** If a component has more than ~3 distinct concerns (data fetch + form + dialog + side effects), split it.
- **Error boundaries belong at route / feature boundaries**, not on every leaf component.

## TypeScript

- **No `any`.** If a value's type is genuinely unknown, use `unknown` and narrow.
- **Prefer `interface` for object shapes, `type` for unions / mapped types.** Pick one and stay consistent within a file.
- **Use `as const` for literal-typed config objects** so downstream code can discriminate on string literal unions.

## Data / async

- **Don't fetch in `useEffect` when there's a route loader / data hook available.** React Router v7 loaders are the canonical place to fetch.
- **AbortControllers on in-component fetches.** Abort on unmount so cancelled responses don't `setState` on a dead component.

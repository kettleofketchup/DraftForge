import { useShallow } from 'zustand/react/shallow';

import { useUserCacheStore } from '~/store/userCacheStore';
import type { UserEntry } from '~/store/userCacheTypes';

/**
 * Resolve an array of user pks to UserEntry objects.
 * Uses useShallow for element-by-element reference comparison —
 * only re-renders when an individual user entry changes.
 *
 * Invariant: pks must always resolve to entities in the cache.
 * During dual-write, pks are populated alongside the cache upsert,
 * so filter(Boolean) should be a no-op. It exists as a safety net.
 *
 * WARNING: Do NOT use selectAll (Object.values) in React selectors.
 * Always use this hook with a pk array instead.
 */
export function useResolvedUsers(pks: number[]): UserEntry[] {
  return useUserCacheStore(
    useShallow((state) =>
      pks.map((pk) => state.entities[pk]).filter(Boolean) as UserEntry[],
    ),
  );
}

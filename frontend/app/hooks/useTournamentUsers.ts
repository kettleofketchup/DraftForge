import { useEffect, useMemo } from 'react';

import type { UserType } from '~/components/user/types';
import { useUserCacheStore } from '~/store/userCacheStore';
import type { UserEntry } from '~/store/userCacheTypes';

import { useResolvedUsers } from './useResolvedUsers';

/**
 * Tournament players resolved from the user cache.
 *
 * Unlike useOrgUsers/useLeagueUsers, the tournament payload is not fetched
 * through a pk-array store — hydrateTournament inlines whole user objects on
 * `tournament.users`. So seed the cache from that array, then read back
 * through it. Being cache-backed is what lets an edit's upsert re-render the
 * card, matching the org and league Users tabs.
 *
 * For an org-backed tournament `_users` carries orgUserPk + mmr, so the seeded
 * entries get orgData and stay scope-aware; a non-org tournament carries core
 * only and resolves to global scope, same as the un-cached array did.
 */
export function useTournamentUsers(
  users: UserType[],
  context: { orgId?: number; leagueId?: number },
): UserType[] {
  const { orgId, leagueId } = context;

  const pks = useMemo(
    () => users.map((u) => u.pk).filter((pk): pk is number => pk != null),
    [users],
  );

  useEffect(() => {
    if (users.length > 0) {
      useUserCacheStore.getState().upsert(users, { orgId, leagueId });
    }
  }, [users, orgId, leagueId]);

  const resolved: UserEntry[] = useResolvedUsers(pks);

  // The seeding effect runs after the first render, so fall back to the raw
  // array until every pk is present. Prevents an empty-state flash and keeps
  // pk-less users (which useResolvedUsers drops) visible.
  return resolved.length === pks.length && pks.length === users.length
    ? resolved
    : users;
}

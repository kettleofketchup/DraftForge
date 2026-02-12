import { useOrgStore } from '~/store/orgStore';
import type { UserEntry } from '~/store/userCacheTypes';

import { useResolvedUsers } from './useResolvedUsers';

/**
 * Get org users as UserEntry[] resolved from the cache.
 * Hooks are called unconditionally to respect Rules of Hooks.
 * Guard is applied after to prevent wrong-org flash during navigation.
 */
export function useOrgUsers(orgId: number): UserEntry[] {
  const pks = useOrgStore((state) => state.orgUserPks);
  const loadedOrgId = useOrgStore((state) => state.orgUsersOrgId);
  const users = useResolvedUsers(pks); // always call unconditionally

  if (loadedOrgId !== orgId) return [];
  return users;
}

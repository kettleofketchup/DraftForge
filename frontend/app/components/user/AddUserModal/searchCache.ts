import type { UserType } from '~/components/user/types';
import { useUserCacheStore } from '~/store/userCacheStore';

import type { EntityContext } from './types';

/** Cache search hits so their org server nicknames reach the resolver. */
export function cacheSearchResults<T extends UserType>(
  results: T[],
  entityContext: EntityContext,
): T[] {
  const { orgId } = entityContext;
  useUserCacheStore.getState().upsert(results, orgId ? { orgId } : undefined);
  return results;
}

import { useOrgUsersQuery } from '~/components/organization/hooks/useOrgUsersQuery';
import type { UserEntry } from '~/store/userCacheTypes';

import { useResolvedUsers } from './useResolvedUsers';

const NO_PKS: number[] = [];

export function useOrgUsers(
  orgId: number,
  { enabled = true }: { enabled?: boolean } = {},
) {
  const query = useOrgUsersQuery(orgId, { enabled });
  const pks = query.data ?? NO_PKS;
  const users: UserEntry[] = useResolvedUsers(pks);
  return {
    users,
    pks,
    isLoading: query.isLoading,
    isLoaded: query.isSuccess,
  };
}

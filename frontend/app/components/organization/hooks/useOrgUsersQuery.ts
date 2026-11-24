import { useQuery } from '@tanstack/react-query';
import { getOrganizationUsers } from '~/components/api/api';
import { organizationQueryKey } from '~/components/organization/hooks/useOrganization';
import { useUserCacheStore } from '~/store/userCacheStore';

// Nested under the org key so invalidating the org also refetches its members.
export const orgUsersQueryKey = (orgId: number) =>
  [...organizationQueryKey(orgId), 'users'] as const;

export async function fetchOrgUserPks(orgId: number): Promise<number[]> {
  const users = await getOrganizationUsers(orgId);
  useUserCacheStore.getState().upsert(users, { orgId });
  return users.flatMap((u) => (u.pk != null ? [u.pk] : []));
}

export function useOrgUsersQuery(
  orgId: number | null | undefined,
  { enabled = true }: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: orgUsersQueryKey(orgId ?? 0),
    queryFn: () => fetchOrgUserPks(orgId!),
    enabled: enabled && !!orgId,
  });
}

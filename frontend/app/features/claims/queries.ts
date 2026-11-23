import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import { useUserStore } from '~/store/userStore';
import { getClaimRequests } from './api';
import { claimKeys } from './queryKeys';
import type { ClaimStatus, ProfileClaimRequest } from './schemas';

function useViewerPk(): number | null {
  return useUserStore((s) => s.currentUser?.pk ?? null);
}

export function useClaimRequests(
  orgId: number,
  status: ClaimStatus,
  enabled = true,
) {
  const viewerPk = useViewerPk();
  return useQuery<ProfileClaimRequest[]>({
    queryKey: claimKeys.list(orgId, viewerPk, status),
    queryFn: () => getClaimRequests({ organizationId: orgId, status }),
    enabled,
  });
}

// Shares the pending list's cache entry, so the count is independent of the
// status filter the tab is showing.
export function usePendingClaimsCount(
  orgId: number | undefined,
  enabled: boolean,
): number {
  const viewerPk = useViewerPk();
  const { data } = useQuery({
    queryKey: claimKeys.list(orgId ?? 0, viewerPk, 'pending'),
    queryFn: () =>
      getClaimRequests({ organizationId: orgId as number, status: 'pending' }),
    enabled: enabled && orgId != null,
    select: (claims) => claims.length,
  });
  return data ?? 0;
}

export function useInvalidateClaims(orgId: number): () => Promise<void> {
  const queryClient = useQueryClient();
  const viewerPk = useViewerPk();
  return useCallback(
    () =>
      queryClient.invalidateQueries({
        queryKey: claimKeys.all(orgId, viewerPk),
      }),
    [queryClient, orgId, viewerPk],
  );
}

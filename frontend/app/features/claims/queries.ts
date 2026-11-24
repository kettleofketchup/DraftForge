import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import { organizationQueryKey } from '~/components/organization/hooks/useOrganization';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';
import { approveClaimRequest, getClaimRequests } from './api';
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

export type ApproveClaimInput = Pick<
  ProfileClaimRequest,
  'id' | 'claimer' | 'target_user'
>;

// Approval merges target_user into claimer and deletes target_user.
export function useApproveClaim(orgId: number) {
  const queryClient = useQueryClient();
  const viewerPk = useViewerPk();
  return useMutation({
    mutationFn: (claim: ApproveClaimInput) => approveClaimRequest(claim.id),
    onSuccess: async (_message, claim) => {
      if (claim.target_user != null) {
        useUserCacheStore.getState().remove(claim.target_user);
        queryClient.removeQueries({ queryKey: ['user', claim.target_user] });
      }
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: claimKeys.all(orgId, viewerPk),
        }),
        queryClient.invalidateQueries({
          queryKey: organizationQueryKey(orgId),
        }),
        queryClient.invalidateQueries({ queryKey: ['user', claim.claimer] }),
      ]);
    },
  });
}

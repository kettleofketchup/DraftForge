import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import { apiTokenKeys, type OrgFeatureAccess } from '~/features/org-features';
import {
  createApiToken,
  getApiLimits,
  getApiUsage,
  listApiTokens,
  putApiLimits,
  revokeApiToken,
} from './api';
import type {
  ApiLimits,
  ApiToken,
  ApiUsage,
  CreateApiTokenInput,
  CreatedApiToken,
} from './schemas';

function canUse(access: OrgFeatureAccess): boolean {
  return access.settled && access.canUseApiTokens;
}

export function useApiTokens(
  orgId: number,
  access: OrgFeatureAccess,
  enabled = true,
): UseQueryResult<ApiToken[]> {
  return useQuery({
    queryKey: apiTokenKeys.tokens(orgId, access.viewerPk),
    queryFn: () => listApiTokens(orgId),
    enabled: enabled && canUse(access),
  });
}

export function useApiUsage(
  orgId: number,
  access: OrgFeatureAccess,
  days: number,
  enabled = true,
): UseQueryResult<ApiUsage> {
  return useQuery({
    queryKey: apiTokenKeys.usage(orgId, access.viewerPk, days),
    queryFn: () => getApiUsage(orgId, days),
    enabled: enabled && canUse(access),
  });
}

export function useApiLimits(
  orgId: number,
  access: OrgFeatureAccess,
  enabled = true,
): UseQueryResult<ApiLimits> {
  return useQuery({
    queryKey: apiTokenKeys.limits(orgId, access.viewerPk),
    queryFn: () => getApiLimits(orgId),
    enabled: enabled && canUse(access),
  });
}

export function useCreateApiToken(
  orgId: number,
  access: OrgFeatureAccess,
): UseMutationResult<CreatedApiToken, unknown, CreateApiTokenInput> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input) => createApiToken(orgId, input),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: apiTokenKeys.tokens(orgId, access.viewerPk),
      }),
  });
}

export function useRevokeApiToken(
  orgId: number,
  access: OrgFeatureAccess,
): UseMutationResult<ApiToken, unknown, number> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tokenId) => revokeApiToken(orgId, tokenId),
    onSuccess: (revoked) => {
      queryClient.setQueryData<ApiToken[]>(
        apiTokenKeys.tokens(orgId, access.viewerPk),
        (rows) => rows?.map((row) => (row.id === revoked.id ? revoked : row)),
      );
      return queryClient.invalidateQueries({
        queryKey: apiTokenKeys.tokens(orgId, access.viewerPk),
      });
    },
  });
}

export function useSetApiLimits(
  orgId: number,
  access: OrgFeatureAccess,
): UseMutationResult<ApiLimits, unknown, ApiLimits> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (limits) => putApiLimits(orgId, limits),
    onSuccess: (saved) => {
      queryClient.setQueryData(
        apiTokenKeys.limits(orgId, access.viewerPk),
        saved,
      );
      return queryClient.invalidateQueries({
        queryKey: apiTokenKeys.all(orgId, access.viewerPk),
      });
    },
  });
}

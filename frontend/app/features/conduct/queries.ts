import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import {
  conductKeys,
  standingKeys,
  type OrgFeatureAccess,
} from '~/features/org-features';
import {
  getConductSettings,
  getMemberConduct,
  patchConductSettings,
} from './api';
import type {
  ConductSettings,
  ConductSettingsForm,
  HistoryPage,
  MemberConduct,
} from './schemas';

function canView(access: OrgFeatureAccess): boolean {
  return access.settled && (access.canViewConduct || access.canViewOwnConduct);
}

function canManage(access: OrgFeatureAccess): boolean {
  return access.settled && access.canManageConduct;
}

export function useMemberConduct(
  orgId: number,
  access: OrgFeatureAccess,
  orgUserPk: number | null,
  page: HistoryPage,
): UseQueryResult<MemberConduct> {
  return useQuery({
    queryKey: conductKeys.member(orgId, access.viewerPk, orgUserPk ?? 0, page),
    queryFn: () => getMemberConduct(orgId, orgUserPk!, page),
    enabled: canView(access) && orgUserPk != null,
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[1] === orgId &&
      previousQuery.queryKey[2] === access.viewerPk &&
      previousQuery.queryKey[3] === 'member' &&
      previousQuery.queryKey[4] === orgUserPk
        ? previous
        : undefined,
  });
}

export function useConductSettings(
  orgId: number,
  access: OrgFeatureAccess,
  enabled = true,
): UseQueryResult<ConductSettings> {
  return useQuery({
    queryKey: conductKeys.settings(orgId, access.viewerPk),
    queryFn: () => getConductSettings(orgId),
    enabled: enabled && canManage(access),
  });
}

export function usePatchConductSettings(
  orgId: number,
  access: OrgFeatureAccess,
): UseMutationResult<ConductSettings, unknown, Partial<ConductSettingsForm>> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body) => patchConductSettings(orgId, body),
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({
          queryKey: conductKeys.all(orgId, access.viewerPk),
        }),
        queryClient.invalidateQueries({
          queryKey: standingKeys.track(orgId, access.viewerPk, 'conduct'),
        }),
      ]),
  });
}

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import {
  contributionsKeys,
  invalidateContributionQueries,
  type OrgFeatureAccess,
} from '~/features/org-features';
import {
  createManualAward,
  deleteManualAward,
  getEntries,
  getMemberBreakdown,
  getPointValues,
  setPointValue,
  updateManualAward,
  type ManualAwardUpdate,
} from './api';
import type {
  AdminEntry,
  EntriesFilters,
  EntriesPage,
  ManualAwardInput,
  MemberBreakdown,
  PointValueRow,
  PointValueUpdate,
  PointValueUpdateResult,
  RatedKind,
} from './schemas';

export function useMemberBreakdown(
  orgId: number,
  access: OrgFeatureAccess,
  orgUserPk: number | null,
  period: string,
): UseQueryResult<MemberBreakdown> {
  return useQuery({
    queryKey: contributionsKeys.member(
      orgId,
      access.viewerPk,
      orgUserPk ?? 0,
      period,
    ),
    queryFn: () => getMemberBreakdown(orgId, orgUserPk!, period),
    enabled: access.settled && access.canViewContributions && orgUserPk != null,
  });
}

function canManage(access: OrgFeatureAccess): boolean {
  return access.settled && access.canManageContributions;
}

export function usePointValues(
  orgId: number,
  access: OrgFeatureAccess,
): UseQueryResult<PointValueRow[]> {
  return useQuery({
    queryKey: contributionsKeys.pointValues(orgId, access.viewerPk),
    queryFn: () => getPointValues(orgId),
    enabled: canManage(access),
  });
}

export function useLedgerEntries(
  orgId: number,
  access: OrgFeatureAccess,
  filters: EntriesFilters,
): UseQueryResult<EntriesPage> {
  return useQuery({
    queryKey: contributionsKeys.entries(orgId, access.viewerPk, filters),
    queryFn: () => getEntries(orgId, filters),
    enabled: canManage(access),
    placeholderData: keepPreviousData,
  });
}

function useInvalidateContributions(
  orgId: number,
  access: OrgFeatureAccess,
): () => Promise<void> {
  const queryClient = useQueryClient();
  return () =>
    invalidateContributionQueries(queryClient, orgId, access.viewerPk);
}

export function useSetPointValue(
  orgId: number,
  access: OrgFeatureAccess,
): UseMutationResult<
  PointValueUpdateResult,
  unknown,
  { kind: RatedKind; update: PointValueUpdate }
> {
  const invalidate = useInvalidateContributions(orgId, access);
  return useMutation({
    mutationFn: ({ kind, update }) => setPointValue(orgId, kind, update),
    onSettled: invalidate,
  });
}

export function useCreateManualAward(
  orgId: number,
  access: OrgFeatureAccess,
): UseMutationResult<AdminEntry, unknown, ManualAwardInput> {
  const invalidate = useInvalidateContributions(orgId, access);
  return useMutation({
    mutationFn: (input) => createManualAward(orgId, input),
    onSettled: invalidate,
  });
}

export function useUpdateManualAward(
  orgId: number,
  access: OrgFeatureAccess,
): UseMutationResult<
  AdminEntry,
  unknown,
  { entryPk: number; changes: ManualAwardUpdate }
> {
  const invalidate = useInvalidateContributions(orgId, access);
  return useMutation({
    mutationFn: ({ entryPk, changes }) =>
      updateManualAward(orgId, entryPk, changes),
    onSettled: invalidate,
  });
}

export function useDeleteManualAward(
  orgId: number,
  access: OrgFeatureAccess,
): UseMutationResult<void, unknown, number> {
  const invalidate = useInvalidateContributions(orgId, access);
  return useMutation({
    mutationFn: (entryPk) => deleteManualAward(orgId, entryPk),
    onSettled: invalidate,
  });
}

import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import { getLeagueUsers } from '~/components/api/leagueAPI';
import { getOrganizationUsers } from '~/components/api/orgAPI';
import { getLogger } from '~/lib/logger';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';
import {
  approveMmrRequest,
  cancelMmrRequest,
  createMmrRequest,
  fetchMmrPendingCount,
  fetchMmrQueue,
  fetchUserMmrSummary,
  rejectMmrRequest,
  staffSetMmr,
} from './api';
import { mmrKeys, type MmrScope } from './queryKeys';
import type {
  CreateMmrRequestInput,
  MmrChangeRequest,
  MmrQueueStatus,
  PendingCount,
  StaffSetMmrInput,
  UserMmrSummary,
} from './schemas';

const log = getLogger('MmrRequests');

export interface ApproveMmrVariables {
  request: MmrChangeRequest;
  mmr?: number;
}

export interface RejectMmrVariables {
  request: MmrChangeRequest;
  reason: string;
}

export type StaffSetMmrVariables = StaffSetMmrInput & { subjectPk: number };

interface MemberScope {
  orgId: number | null;
  leagueId: number | null;
}

function useViewerPk(): number | null {
  return useUserStore((state) => state.currentUser?.pk ?? null);
}

function invalidateFor(
  queryClient: QueryClient,
  subjectPk: number | null,
): void {
  void queryClient.invalidateQueries({ queryKey: mmrKeys.all });
  if (subjectPk != null) {
    void queryClient.invalidateQueries({ queryKey: ['user', subjectPk] });
  }
}

async function refreshMemberCaches(
  subjectPk: number,
  { orgId, leagueId }: MemberScope,
): Promise<void> {
  const cache = useUserCacheStore.getState();
  if (orgId != null && useOrgStore.getState().orgUsersOrgId === orgId) {
    const users = await getOrganizationUsers(orgId);
    const mine = users.filter((u) => u.pk === subjectPk);
    if (mine.length > 0) cache.upsert(mine, { orgId });
  }
  if (
    leagueId != null &&
    useLeagueStore.getState().leagueUsersLeagueId === leagueId
  ) {
    const users = await getLeagueUsers(leagueId);
    const mine = users.filter((u) => u.pk === subjectPk);
    if (mine.length > 0) cache.upsert(mine, { leagueId });
  }
}

function settleStaffWrite(
  queryClient: QueryClient,
  subjectPk: number,
  scope: MemberScope,
): void {
  invalidateFor(queryClient, subjectPk);
  refreshMemberCaches(subjectPk, scope).catch((error: unknown) =>
    log.error('Failed to refresh member MMR caches', error),
  );
}

function rowScope(row: MmrChangeRequest): MemberScope {
  return { orgId: row.organization.pk, leagueId: row.league?.pk ?? null };
}

function scopeIds(scope: MmrScope): MemberScope {
  return 'org' in scope
    ? { orgId: scope.org, leagueId: null }
    : { orgId: null, leagueId: scope.league };
}

export function useUserMmrSummary(
  userPk: number | null | undefined,
): UseQueryResult<UserMmrSummary> {
  const viewerPk = useViewerPk();
  return useQuery({
    queryKey: mmrKeys.summary(userPk ?? 0, viewerPk),
    queryFn: () => fetchUserMmrSummary(userPk!),
    enabled: userPk != null,
  });
}

export function useMmrQueue(
  scope: MmrScope,
  status: MmrQueueStatus,
  enabled = true,
): UseQueryResult<MmrChangeRequest[]> {
  const viewerPk = useViewerPk();
  return useQuery({
    queryKey: mmrKeys.queue(scope, viewerPk, status),
    queryFn: () => fetchMmrQueue(scope, status),
    enabled: enabled && viewerPk != null,
  });
}

export function useMmrPendingCount(
  scope: MmrScope,
  enabled = true,
): UseQueryResult<PendingCount> {
  const viewerPk = useViewerPk();
  return useQuery({
    queryKey: mmrKeys.pendingCount(scope, viewerPk),
    queryFn: () => fetchMmrPendingCount(scope),
    enabled: enabled && viewerPk != null,
    refetchInterval: 60_000,
  });
}

export function useCreateMmrRequest(
  subjectPk: number,
): UseMutationResult<MmrChangeRequest, unknown, CreateMmrRequestInput> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createMmrRequest,
    onError: (error) => log.error('Failed to create MMR request', error),
    onSettled: () => invalidateFor(queryClient, subjectPk),
  });
}

export function useCancelMmrRequest(
  subjectPk: number,
): UseMutationResult<MmrChangeRequest, unknown, number> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: cancelMmrRequest,
    onError: (error) => log.error('Failed to cancel MMR request', error),
    onSettled: () => invalidateFor(queryClient, subjectPk),
  });
}

export function useApproveMmrRequest(): UseMutationResult<
  MmrChangeRequest,
  unknown,
  ApproveMmrVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ request, mmr }) => approveMmrRequest(request.id, mmr),
    onError: (error) => log.error('Failed to approve MMR request', error),
    onSettled: (_row, _error, { request }) =>
      settleStaffWrite(queryClient, request.subject.pk, rowScope(request)),
  });
}

export function useRejectMmrRequest(): UseMutationResult<
  MmrChangeRequest,
  unknown,
  RejectMmrVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ request, reason }) => rejectMmrRequest(request.id, reason),
    onError: (error) => log.error('Failed to reject MMR request', error),
    onSettled: (_row, _error, { request }) =>
      invalidateFor(queryClient, request.subject.pk),
  });
}

export function useStaffSetMmr(
  scope: MmrScope,
): UseMutationResult<MmrChangeRequest, unknown, StaffSetMmrVariables> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables) => staffSetMmr(scope, variables),
    onError: (error) => log.error('Failed to set official MMR', error),
    onSettled: (row, _error, { subjectPk }) =>
      settleStaffWrite(
        queryClient,
        subjectPk,
        row ? rowScope(row) : scopeIds(scope),
      ),
  });
}

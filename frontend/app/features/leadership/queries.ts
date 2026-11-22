import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import {
  invalidateLeadershipQueries,
  leadershipKeys,
  type OrgFeatureAccess,
} from '~/features/org-features';
import {
  deleteReview,
  deleteTrait,
  getEventReviews,
  getLeadershipSettings,
  getMemberLeadership,
  getMyReviews,
  getPendingReviews,
  getTraits,
  patchLeadershipSettings,
  putReview,
  putTraits,
  unvoidReview,
  voidReview,
  type TraitPutItem,
} from './api';
import type {
  EventReviews,
  LeadershipSettings,
  LeadershipSettingsPatch,
  MemberLeadership,
  ModerationReview,
  MyReview,
  PendingReview,
  ReviewResult,
  Scores,
  Trait,
} from './schemas';

function unlocked(access: OrgFeatureAccess): boolean {
  return access.settled && access.leadershipUnlocked;
}

function isMember(access: OrgFeatureAccess): boolean {
  return unlocked(access) && access.leadershipMember;
}

function canManage(access: OrgFeatureAccess): boolean {
  return unlocked(access) && access.canManageLeadership;
}

export function useMemberLeadership(
  orgId: number,
  access: OrgFeatureAccess,
  orgUserPk: number | null,
): UseQueryResult<MemberLeadership> {
  return useQuery({
    queryKey: leadershipKeys.member(orgId, access.viewerPk, orgUserPk ?? 0),
    queryFn: () => getMemberLeadership(orgId, orgUserPk!),
    enabled: unlocked(access) && orgUserPk != null,
  });
}

export function usePendingReviews(
  orgId: number,
  access: OrgFeatureAccess,
  eventId: number | null,
  enabled = true,
): UseQueryResult<PendingReview[]> {
  return useQuery({
    queryKey: leadershipKeys.pending(orgId, access.viewerPk, eventId),
    queryFn: () => getPendingReviews(orgId, eventId),
    enabled: enabled && isMember(access),
  });
}

export function useMyReviews(
  orgId: number,
  access: OrgFeatureAccess,
  enabled = true,
): UseQueryResult<MyReview[]> {
  return useQuery({
    queryKey: leadershipKeys.mine(orgId, access.viewerPk),
    queryFn: () => getMyReviews(orgId),
    enabled: enabled && isMember(access),
  });
}

export type SubmitReviewVars = {
  eventId: number;
  captainOrgUserId: number;
  scores: Scores;
};

export type WithdrawReviewVars = {
  eventId: number;
  captainOrgUserId: number;
};

export function useSubmitReview(
  orgId: number,
  _access: OrgFeatureAccess,
): UseMutationResult<ReviewResult, unknown, SubmitReviewVars> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ eventId, captainOrgUserId, scores }) =>
      putReview(orgId, eventId, captainOrgUserId, scores),
    onSettled: (_result, _error, { eventId }) =>
      invalidateLeadershipQueries(queryClient, orgId, { eventId }),
  });
}

export function useWithdrawReview(
  orgId: number,
  _access: OrgFeatureAccess,
): UseMutationResult<void, unknown, WithdrawReviewVars> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ eventId, captainOrgUserId }) =>
      deleteReview(orgId, eventId, captainOrgUserId),
    onSettled: (_result, _error, { eventId }) =>
      invalidateLeadershipQueries(queryClient, orgId, { eventId }),
  });
}

export function useEventReviews(
  orgId: number,
  access: OrgFeatureAccess,
  eventId: number,
  enabled: boolean,
): UseQueryResult<EventReviews> {
  return useQuery({
    queryKey: leadershipKeys.eventReviews(orgId, access.viewerPk, eventId),
    queryFn: () => getEventReviews(orgId, eventId),
    enabled: enabled && canManage(access),
  });
}

export function useVoidReview(
  orgId: number,
  _access: OrgFeatureAccess,
  eventId: number,
): UseMutationResult<
  ModerationReview,
  unknown,
  { reviewPk: number; reason: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ reviewPk, reason }) => voidReview(orgId, reviewPk, reason),
    onSettled: () =>
      invalidateLeadershipQueries(queryClient, orgId, { eventId }),
  });
}

export function useUnvoidReview(
  orgId: number,
  _access: OrgFeatureAccess,
  eventId: number,
): UseMutationResult<ModerationReview, unknown, { reviewPk: number }> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ reviewPk }) => unvoidReview(orgId, reviewPk),
    onSettled: () =>
      invalidateLeadershipQueries(queryClient, orgId, { eventId }),
  });
}

export function useLeadershipSettings(
  orgId: number,
  access: OrgFeatureAccess,
  enabled = true,
): UseQueryResult<LeadershipSettings> {
  return useQuery({
    queryKey: leadershipKeys.settings(orgId, access.viewerPk),
    queryFn: () => getLeadershipSettings(orgId),
    enabled: enabled && canManage(access),
  });
}

export function usePatchLeadershipSettings(
  orgId: number,
  access: OrgFeatureAccess,
): UseMutationResult<LeadershipSettings, unknown, LeadershipSettingsPatch> {
  const queryClient = useQueryClient();
  const key = leadershipKeys.settings(orgId, access.viewerPk);
  return useMutation({
    mutationFn: (body) => patchLeadershipSettings(orgId, body),
    onSuccess: (saved) => {
      queryClient.setQueryData(key, saved);
    },
    onSettled: (_saved, error) =>
      invalidateLeadershipQueries(queryClient, orgId, {
        except: error == null ? key : undefined,
        org: true,
      }),
  });
}

export function useLeadershipTraits(
  orgId: number,
  access: OrgFeatureAccess,
  enabled = true,
): UseQueryResult<Trait[]> {
  return useQuery({
    queryKey: leadershipKeys.traits(orgId, access.viewerPk),
    queryFn: () => getTraits(orgId),
    enabled: enabled && canManage(access),
  });
}

export function usePutTraits(
  orgId: number,
  access: OrgFeatureAccess,
): UseMutationResult<Trait[], unknown, TraitPutItem[]> {
  const queryClient = useQueryClient();
  const key = leadershipKeys.traits(orgId, access.viewerPk);
  return useMutation({
    mutationFn: (items) => putTraits(orgId, items),
    onSuccess: (saved) => {
      queryClient.setQueryData(key, saved);
    },
    onSettled: (_saved, error) =>
      invalidateLeadershipQueries(queryClient, orgId, {
        except: error == null ? key : undefined,
        org: true,
      }),
  });
}

export function useDeleteTrait(
  orgId: number,
  _access: OrgFeatureAccess,
): UseMutationResult<void, unknown, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (key) => deleteTrait(orgId, key),
    onSuccess: () =>
      invalidateLeadershipQueries(queryClient, orgId, { org: true }),
  });
}

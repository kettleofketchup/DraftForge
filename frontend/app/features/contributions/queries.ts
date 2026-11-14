import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { contributionsKeys, type OrgFeatureAccess } from '~/features/org-features';
import { getLeaderboard, getMemberBreakdown } from './api';
import type { LeaderboardResponse, MemberBreakdown } from './schemas';

export function useLeaderboard(
  orgId: number,
  access: OrgFeatureAccess,
  period: string,
): UseQueryResult<LeaderboardResponse> {
  return useQuery({
    queryKey: contributionsKeys.leaderboard(orgId, access.viewerPk, period),
    queryFn: () => getLeaderboard(orgId, period),
    enabled: access.settled && access.canViewContributions,
  });
}

export function useMemberBreakdown(
  orgId: number,
  access: OrgFeatureAccess,
  orgUserPk: number | null,
  period: string,
): UseQueryResult<MemberBreakdown> {
  return useQuery({
    queryKey: contributionsKeys.member(orgId, access.viewerPk, orgUserPk ?? 0, period),
    queryFn: () => getMemberBreakdown(orgId, orgUserPk!, period),
    enabled: access.settled && access.canViewContributions && orgUserPk != null,
  });
}

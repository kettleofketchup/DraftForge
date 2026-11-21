import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { standingKeys, type OrgFeatureAccess } from '~/features/org-features';
import { getStandingLeaderboard } from './api';
import type { Metric, StandingLeaderboard, TrackInfo } from './schemas';

const NON_PERIODIC = 'current';

export function useStandingLeaderboard(
  orgId: number,
  access: OrgFeatureAccess,
  track: TrackInfo,
  metric: Metric,
  period: string,
): UseQueryResult<StandingLeaderboard> {
  return useQuery({
    queryKey: standingKeys.leaderboard(
      orgId,
      access.viewerPk,
      track.key,
      metric.key,
      metric.periodic ? period : NON_PERIODIC,
    ),
    queryFn: () => getStandingLeaderboard(orgId, track.key, metric, period),
    enabled: access.settled && (track.board_open || track.can_view_own),
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[1] === orgId &&
      previousQuery.queryKey[2] === access.viewerPk &&
      previousQuery.queryKey[3] === track.key
        ? previous
        : undefined,
  });
}

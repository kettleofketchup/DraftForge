import api from '~/components/api/axios';
import { ALL_TIME } from '~/features/contributions/schemas';
import {
  StandingLeaderboardSchema,
  type Metric,
  type StandingLeaderboard,
  type TrackKey,
} from './schemas';

export async function getStandingLeaderboard(
  orgId: number,
  track: TrackKey,
  metric: Metric,
  period: string,
): Promise<StandingLeaderboard> {
  const response = await api.get(
    `/organizations/${orgId}/standing/${track}/leaderboard/`,
    {
      params: {
        metric: metric.key,
        ...(metric.periodic && period && period !== ALL_TIME ? { period } : {}),
      },
    },
  );
  return StandingLeaderboardSchema.parse(response.data);
}

import api from '~/components/api/axios';
import {
  ALL_TIME,
  LeaderboardResponseSchema,
  MemberBreakdownSchema,
  type LeaderboardResponse,
  type MemberBreakdown,
} from './schemas';

function periodParams(period: string): { period?: string } {
  return period && period !== ALL_TIME ? { period } : {};
}

export async function getLeaderboard(orgId: number, period: string): Promise<LeaderboardResponse> {
  const response = await api.get(`/organizations/${orgId}/contributions/leaderboard/`, {
    params: periodParams(period),
  });
  return LeaderboardResponseSchema.parse(response.data);
}

export async function getMemberBreakdown(
  orgId: number,
  orgUserPk: number,
  period: string,
): Promise<MemberBreakdown> {
  const response = await api.get(`/organizations/${orgId}/contributions/members/${orgUserPk}/`, {
    params: periodParams(period),
  });
  return MemberBreakdownSchema.parse(response.data);
}

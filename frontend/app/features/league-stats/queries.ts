import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { useCallback } from 'react';
import { getLogger } from '~/lib/logger';
import {
  LeaguePlayerSummariesSchema,
  type LeagueDistribution,
  type LeaguePlayerSummaries,
  type PlayerLeagueSummary,
} from './schemas';

const log = getLogger('league-stats');

export const leaguePlayerSummariesKey = (leaguePk: number) =>
  ['league-player-summaries', leaguePk] as const;

async function fetchLeaguePlayerSummaries(
  leaguePk: number,
): Promise<LeaguePlayerSummaries> {
  const response = await fetch(`/api/steam/leagues/${leaguePk}/player-summaries/`);
  if (!response.ok) {
    throw new Error(`Failed to fetch league player summaries: ${response.status}`);
  }
  const parsed = LeaguePlayerSummariesSchema.safeParse(await response.json());
  if (!parsed.success) {
    log.error('league player summaries failed to parse', {
      leaguePk,
      issues: parsed.error.issues,
    });
    throw parsed.error;
  }
  return parsed.data;
}

function useSummariesQuery<T>(
  leaguePk: number | null | undefined,
  select: (data: LeaguePlayerSummaries) => T,
): UseQueryResult<T> {
  return useQuery({
    queryKey: leaguePlayerSummariesKey(leaguePk ?? 0),
    queryFn: () => fetchLeaguePlayerSummaries(leaguePk!),
    enabled: !!leaguePk,
    staleTime: 60_000,
    select,
  });
}

export function useLeaguePlayerSummaries(
  leaguePk: number | null | undefined,
): UseQueryResult<LeaguePlayerSummaries> {
  return useSummariesQuery(leaguePk, identity);
}

function identity(data: LeaguePlayerSummaries): LeaguePlayerSummaries {
  return data;
}

export interface PlayerLeagueSummarySlice {
  summary: PlayerLeagueSummary | undefined;
  population: number;
  minGames: number;
}

export function usePlayerLeagueSummary(
  leaguePk: number | null | undefined,
  userId: number,
): UseQueryResult<PlayerLeagueSummarySlice> {
  const select = useCallback(
    (data: LeaguePlayerSummaries): PlayerLeagueSummarySlice => ({
      summary: data.players[String(userId)],
      population: data.population,
      minGames: data.min_games,
    }),
    [userId],
  );
  return useSummariesQuery(leaguePk, select);
}

export interface LeagueDistributionSlice {
  distribution: LeagueDistribution;
  population: number;
  minGames: number;
}

function selectDistribution(data: LeaguePlayerSummaries): LeagueDistributionSlice {
  return {
    distribution: data.distribution,
    population: data.population,
    minGames: data.min_games,
  };
}

export function useLeagueDistribution(
  leaguePk: number | null | undefined,
): UseQueryResult<LeagueDistributionSlice> {
  return useSummariesQuery(leaguePk, selectDistribution);
}

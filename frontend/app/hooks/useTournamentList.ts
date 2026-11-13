import {
  keepPreviousData,
  useInfiniteQuery,
  useQuery,
  type InfiniteData,
  type UseInfiniteQueryResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import { getTournaments, getTournamentsPage } from '~/components/api/api';
import {
  cutoffDayKey,
  dedupeByPk,
  normalizeSearch,
} from '~/components/tournament/tournamentBuckets';
import type {
  PaginatedTournaments,
  TournamentsType,
} from '~/components/tournament/types';

const STALE_TIME_MS = 5 * 60_000;

export interface TournamentListQuery {
  organization?: number;
  organizations?: number[];
  openSignups?: boolean;
  league?: number;
  search?: string;
}

export interface NormalizedListKeyParams {
  organization?: number;
  organizations?: number[];
  openSignups?: boolean;
  league?: number;
  search?: string;
  day: string;
}

const all = ['tournaments', 'list'] as const;

export const tournamentListKeys = {
  all,
  upcoming: (p: NormalizedListKeyParams) => [...all, 'upcoming', p] as const,
  archived: (p: NormalizedListKeyParams) => [...all, 'archived', p] as const,
};

function normalizeParams(params: TournamentListQuery): NormalizedListKeyParams {
  return {
    organization: params.organization,
    organizations:
      params.organizations === undefined
        ? undefined
        : [...params.organizations].sort((a, b) => a - b),
    openSignups: params.openSignups || undefined,
    league: params.league,
    search: params.search === undefined ? undefined : normalizeSearch(params.search),
    day: cutoffDayKey(new Date()),
  };
}

export function useUpcomingTournaments(
  params: TournamentListQuery,
  opts: { enabled: boolean },
): UseQueryResult<TournamentsType> {
  const key = normalizeParams(params);
  return useQuery({
    queryKey: tournamentListKeys.upcoming(key),
    queryFn: () =>
      getTournaments({
        bucket: 'upcoming',
        organizationId: key.organization,
        organizationIds: key.organizations,
        openSignups: key.openSignups,
        leagueId: key.league,
        search: key.search,
      }),
    enabled: opts.enabled,
    placeholderData: keepPreviousData,
    staleTime: STALE_TIME_MS,
  });
}

export type ArchivedTournamentsResult = UseInfiniteQueryResult<
  InfiniteData<PaginatedTournaments>
> & { tournaments: TournamentsType };

export function useArchivedTournaments(
  params: TournamentListQuery,
  opts: { enabled: boolean },
): ArchivedTournamentsResult {
  const key = normalizeParams(params);
  const query = useInfiniteQuery({
    queryKey: tournamentListKeys.archived(key),
    queryFn: ({ pageParam }) =>
      getTournamentsPage({
        bucket: 'archived',
        organizationId: key.organization,
        organizationIds: key.organizations,
        openSignups: key.openSignups,
        leagueId: key.league,
        search: key.search,
        page: pageParam,
      }),
    initialPageParam: 1,
    getNextPageParam: (last, _all, lastParam) =>
      last.next !== null ? lastParam + 1 : undefined,
    enabled: opts.enabled,
    placeholderData: keepPreviousData,
    staleTime: STALE_TIME_MS,
    refetchOnWindowFocus: false,
  });
  const tournaments = dedupeByPk(query.data?.pages.flatMap((p) => p.results) ?? []);
  return { ...query, tournaments };
}

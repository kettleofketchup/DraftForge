import {
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
  /** The viewer's organizations, resolved by the server (`organizations=mine`). */
  mine?: boolean;
  /** Keys a `mine` query to the membership it was fetched for; never sent. */
  memberOrgIds?: number[];
  openSignups?: boolean;
  league?: number;
  search?: string;
}

export interface NormalizedListKeyParams {
  organization?: number;
  mine?: true;
  memberOrgIds?: number[];
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
    mine: params.mine || undefined,
    memberOrgIds: params.mine
      ? [...(params.memberOrgIds ?? [])].sort((a, b) => a - b)
      : undefined,
    openSignups: params.openSignups || undefined,
    league: params.league,
    search: params.search === undefined ? undefined : normalizeSearch(params.search),
    day: cutoffDayKey(new Date()),
  };
}

type ScopeKind = 'org' | 'mine' | 'all';

function scopeKind(key: NormalizedListKeyParams): ScopeKind {
  if (key.organization !== undefined) return 'org';
  return key.mine ? 'mine' : 'all';
}

/** Previous data stands in only while the scope kind is unchanged: a list from
 * another kind would get this kind's badges and layout. */
function sameScopePlaceholder<T>(key: NormalizedListKeyParams) {
  return (
    previous: T | undefined,
    previousQuery: { queryKey: readonly unknown[] } | undefined,
  ): T | undefined => {
    const previousKey = previousQuery?.queryKey[3] as NormalizedListKeyParams | undefined;
    if (previousKey === undefined) return undefined;
    return scopeKind(previousKey) === scopeKind(key) ? previous : undefined;
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
        mine: key.mine,
        openSignups: key.openSignups,
        leagueId: key.league,
        search: key.search,
      }),
    enabled: opts.enabled,
    placeholderData: sameScopePlaceholder<TournamentsType>(key),
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
        mine: key.mine,
        openSignups: key.openSignups,
        leagueId: key.league,
        search: key.search,
        page: pageParam,
      }),
    initialPageParam: 1,
    getNextPageParam: (last, _all, lastParam) =>
      last.next !== null ? lastParam + 1 : undefined,
    enabled: opts.enabled,
    placeholderData: sameScopePlaceholder<InfiniteData<PaginatedTournaments, number>>(key),
    staleTime: STALE_TIME_MS,
    refetchOnWindowFocus: false,
  });
  const tournaments = dedupeByPk(query.data?.pages.flatMap((p) => p.results) ?? []);
  return { ...query, tournaments };
}

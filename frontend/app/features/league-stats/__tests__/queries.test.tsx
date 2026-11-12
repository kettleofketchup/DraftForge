// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  LeagueStatsHttpError,
  useUserLeagueStatsByLeague,
} from '~/features/leaderboard/queries';
import {
  leaguePlayerSummariesKey,
  useLeagueDistribution,
  usePlayerLeagueSummary,
} from '../queries';

const buckets = Array.from({ length: 10 }, (_, i) => ({
  min: i * 10,
  max: (i + 1) * 10,
  count: i === 5 ? 1 : 0,
}));

const summaries = {
  league_pk: 3,
  steam_league_id: 17929,
  min_games: 3,
  population: 1,
  players: {
    '42': {
      rank: 1,
      top_percent: 100,
      games: 7,
      wins: 4,
      losses: 3,
      win_rate: 0.5714,
      bucket: 5,
      recent: ['W', 'L', 'W', 'L', 'W', 'L', 'W'],
      streak: { result: 'W', count: 1 },
    },
    '43': {
      rank: null,
      top_percent: null,
      games: 1,
      wins: 0,
      losses: 1,
      win_rate: 0,
      bucket: null,
      recent: ['L'],
      streak: { result: 'L', count: 1 },
    },
  },
  distribution: { bucket_size: 10, buckets },
};

const leagueStats = {
  user_id: 42,
  username: 'alice',
  avatar: null,
  base_mmr: 4000,
  league_mmr: 4100,
  league_id: 17929,
  games_played: 7,
  wins: 4,
  losses: 3,
  win_rate: 0.5714,
  avg_kills: 6.1,
  avg_deaths: 4.2,
  avg_assists: 10.3,
  avg_gpm: 480.5,
  avg_xpm: 560.2,
  mmr_adjustment: 25,
  last_updated: '2026-11-06T12:00:00Z',
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: 1, retryDelay: 0 } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

let fetchSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  fetchSpy = vi.spyOn(globalThis, 'fetch');
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('league player summaries', () => {
  it('usePlayerLeagueSummary returns the user slice, population, minGames', async () => {
    fetchSpy.mockImplementation(async () => jsonResponse(summaries));
    const { wrapper } = setup();
    const { result } = renderHook(() => usePlayerLeagueSummary(3, 42), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchSpy).toHaveBeenCalledWith('/api/steam/leagues/3/player-summaries/');
    expect(result.current.data).toEqual({
      summary: summaries.players['42'],
      population: 1,
      minGames: 3,
    });
  });

  it('slice reference is stable across a refetch with identical data', async () => {
    fetchSpy.mockImplementation(async () => jsonResponse(summaries));
    const { client, wrapper } = setup();
    const { result } = renderHook(() => usePlayerLeagueSummary(3, 42), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const first = result.current.data;
    await client.invalidateQueries({ queryKey: leaguePlayerSummariesKey(3) });
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.isFetching).toBe(false));
    expect(result.current.data).toBe(first);
  });

  it('missing user yields summary undefined', async () => {
    fetchSpy.mockImplementation(async () => jsonResponse(summaries));
    const { wrapper } = setup();
    const { result } = renderHook(() => usePlayerLeagueSummary(3, 999), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.summary).toBeUndefined();
    expect(result.current.data?.population).toBe(1);
  });

  it('useLeagueDistribution shares the query and returns the distribution', async () => {
    fetchSpy.mockImplementation(async () => jsonResponse(summaries));
    const { wrapper } = setup();
    const { result } = renderHook(
      () => ({ dist: useLeagueDistribution(3), slice: usePlayerLeagueSummary(3, 42) }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.dist.isSuccess).toBe(true));
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(result.current.dist.data).toEqual({
      distribution: summaries.distribution,
      population: 1,
      minGames: 3,
    });
  });

  it.each([null, undefined, 0])('no fetch when leaguePk is %s', async (pk) => {
    fetchSpy.mockImplementation(async () => jsonResponse(summaries));
    const { wrapper } = setup();
    const { result } = renderHook(
      () => ({ slice: usePlayerLeagueSummary(pk, 42), dist: useLeagueDistribution(pk) }),
      { wrapper },
    );

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result.current.slice.fetchStatus).toBe('idle');
    expect(result.current.dist.fetchStatus).toBe('idle');
  });

  it('parse failure surfaces isError', async () => {
    fetchSpy.mockImplementation(async () =>
      jsonResponse({ ...summaries, population: 'many' }),
    );
    const { wrapper } = setup();
    const { result } = renderHook(() => usePlayerLeagueSummary(3, 42), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useUserLeagueStatsByLeague', () => {
  it('sends ?league=<pk> and parses the body', async () => {
    fetchSpy.mockImplementation(async () => jsonResponse(leagueStats));
    const { wrapper } = setup();
    const { result } = renderHook(() => useUserLeagueStatsByLeague(42, 3), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchSpy).toHaveBeenCalledWith('/api/steam/league-stats/42/?league=3');
    expect(result.current.data).toEqual(leagueStats);
  });

  it('resolves null on 404 without retry', async () => {
    fetchSpy.mockImplementation(async () => jsonResponse({ error: 'nope' }, 404));
    const { wrapper } = setup();
    const { result } = renderHook(() => useUserLeagueStatsByLeague(42, 3), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeNull();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it('throws LeagueStatsHttpError with status 500', async () => {
    fetchSpy.mockImplementation(async () => jsonResponse({ error: 'boom' }, 500));
    const { wrapper } = setup();
    const { result } = renderHook(() => useUserLeagueStatsByLeague(42, 3), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(LeagueStatsHttpError);
    expect((result.current.error as LeagueStatsHttpError).status).toBe(500);
  });

  it('malformed 200 body surfaces a non-HTTP error without retry', async () => {
    fetchSpy.mockImplementation(async () => jsonResponse({ user_id: 'x' }));
    const { wrapper } = setup();
    const { result } = renderHook(() => useUserLeagueStatsByLeague(42, 3), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).not.toBeInstanceOf(LeagueStatsHttpError);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it.each([
    [undefined, 3],
    [42, null],
    [42, 0],
  ])('no fetch when userId=%s leaguePk=%s', async (userId, pk) => {
    fetchSpy.mockImplementation(async () => jsonResponse(leagueStats));
    const { wrapper } = setup();
    const { result } = renderHook(() => useUserLeagueStatsByLeague(userId, pk), { wrapper });

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe('idle');
  });
});

// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { TournamentType } from '~/components/tournament/types';
import type { PaginatedTournaments } from '~/components/tournament/types';
import { cutoffDayKey } from '~/components/tournament/tournamentBuckets';

vi.mock('~/components/api/api', () => ({
  getTournaments: vi.fn(),
  getTournamentsPage: vi.fn(),
}));

import { getTournaments, getTournamentsPage } from '~/components/api/api';
import {
  tournamentListKeys,
  useArchivedTournaments,
  useUpcomingTournaments,
} from '../useTournamentList';

const getTournamentsMock = vi.mocked(getTournaments);
const getTournamentsPageMock = vi.mocked(getTournamentsPage);

function tournament(pk: number): TournamentType {
  return { pk, name: `T${pk}` } as TournamentType;
}

function page(pks: number[], next: string | null): PaginatedTournaments {
  return { count: pks.length, next, previous: null, results: pks.map(tournament) };
}

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, wrapper };
}

beforeEach(() => {
  getTournamentsMock.mockReset();
  getTournamentsPageMock.mockReset();
  getTournamentsMock.mockResolvedValue([]);
});

describe('useUpcomingTournaments', () => {
  it('keys raw search " ab " the same as normalized "ab"', async () => {
    const { queryClient, wrapper } = setup();
    const { result } = renderHook(
      () => useUpcomingTournaments({ search: ' ab ' }, { enabled: true }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const keys = queryClient.getQueryCache().getAll().map((q) => q.queryKey);
    expect(keys).toHaveLength(1);
    expect(keys[0]).toEqual(
      tournamentListKeys.upcoming({ search: 'ab', day: cutoffDayKey(new Date()) }),
    );
    expect(getTournamentsMock).toHaveBeenCalledWith(expect.objectContaining({ search: 'ab' }));
  });

  it('drops a one-character search', async () => {
    const { wrapper } = setup();
    const { result } = renderHook(
      () => useUpcomingTournaments({ search: 'a' }, { enabled: true }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getTournamentsMock).toHaveBeenCalledWith(expect.objectContaining({ search: undefined }));
  });

  it('does not fetch while disabled', async () => {
    const { wrapper } = setup();
    renderHook(() => useUpcomingTournaments({}, { enabled: false }), { wrapper });
    await new Promise((r) => setTimeout(r, 20));
    expect(getTournamentsMock).not.toHaveBeenCalled();
  });

  it('maps filters to the upcoming bucket request', async () => {
    const { wrapper } = setup();
    const { result } = renderHook(
      () => useUpcomingTournaments({ organization: 30, league: 31 }, { enabled: true }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getTournamentsMock).toHaveBeenCalledWith({
      bucket: 'upcoming',
      organizationId: 30,
      leagueId: 31,
      search: undefined,
    });
  });
});

describe('organization scope', () => {
  it('maps member organizations and open signups to the request and key', async () => {
    const { queryClient, wrapper } = setup();
    const { result } = renderHook(
      () =>
        useUpcomingTournaments(
          { organizations: [32, 30], openSignups: true },
          { enabled: true },
        ),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getTournamentsMock).toHaveBeenCalledWith({
      bucket: 'upcoming',
      organizationIds: [30, 32],
      openSignups: true,
    });
    const [key] = queryClient.getQueryCache().getAll().map((q) => q.queryKey);
    expect(key).toEqual(
      tournamentListKeys.upcoming({
        organizations: [30, 32],
        openSignups: true,
        day: cutoffDayKey(new Date()),
      }),
    );
  });

  it('keys the empty member list apart from no organization filter', async () => {
    const { queryClient, wrapper } = setup();
    renderHook(() => useUpcomingTournaments({ organizations: [] }, { enabled: true }), {
      wrapper,
    });
    renderHook(() => useUpcomingTournaments({}, { enabled: true }), { wrapper });
    await waitFor(() => expect(getTournamentsMock).toHaveBeenCalledTimes(2));
    expect(queryClient.getQueryCache().getAll()).toHaveLength(2);
  });

  it('passes member organizations to archived pages', async () => {
    getTournamentsPageMock.mockResolvedValueOnce(page([1], null));
    const { wrapper } = setup();
    const { result } = renderHook(
      () => useArchivedTournaments({ organizations: [30] }, { enabled: true }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getTournamentsPageMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ organizationIds: [30], page: 1 }),
    );
  });
});

describe('useArchivedTournaments', () => {
  it('does not fetch while disabled', async () => {
    const { wrapper } = setup();
    renderHook(() => useArchivedTournaments({}, { enabled: false }), { wrapper });
    await new Promise((r) => setTimeout(r, 20));
    expect(getTournamentsPageMock).not.toHaveBeenCalled();
  });

  it('requests page numbers, never the next URL, and dedupes across pages', async () => {
    getTournamentsPageMock
      .mockResolvedValueOnce(page([1, 2], 'http://other/x?page=2'))
      .mockResolvedValueOnce(page([2, 3], null));
    const { wrapper } = setup();
    const { result } = renderHook(
      () => useArchivedTournaments({ organization: 30 }, { enabled: true }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.hasNextPage).toBe(true);
    expect(getTournamentsPageMock).toHaveBeenLastCalledWith({
      bucket: 'archived',
      organizationId: 30,
      leagueId: undefined,
      search: undefined,
      page: 1,
    });

    await act(async () => {
      await result.current.fetchNextPage();
    });

    await waitFor(() => expect(result.current.hasNextPage).toBe(false));
    expect(getTournamentsPageMock).toHaveBeenCalledTimes(2);
    expect(getTournamentsPageMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 2 }),
    );
    for (const call of getTournamentsPageMock.mock.calls) {
      expect(JSON.stringify(call)).not.toContain('http://other');
    }
    expect(result.current.tournaments.map((t) => t.pk)).toEqual([1, 2, 3]);
  });

  it('has no next page when the first page is the last', async () => {
    getTournamentsPageMock.mockResolvedValueOnce(page([1], null));
    const { wrapper } = setup();
    const { result } = renderHook(
      () => useArchivedTournaments({}, { enabled: true }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.hasNextPage).toBe(false);
    expect(result.current.tournaments.map((t) => t.pk)).toEqual([1]);
  });
});

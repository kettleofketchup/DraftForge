// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { TournamentType } from '~/components/tournament/types';
import type { TournamentListQuery } from '../useTournamentList';
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
  it('sends mine without member ids and keys by the membership', async () => {
    const { queryClient, wrapper } = setup();
    const { result } = renderHook(
      () =>
        useUpcomingTournaments(
          { mine: true, memberOrgIds: [32, 30], openSignups: true },
          { enabled: true },
        ),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getTournamentsMock).toHaveBeenCalledWith({
      bucket: 'upcoming',
      mine: true,
      openSignups: true,
    });
    expect(JSON.stringify(getTournamentsMock.mock.calls[0])).not.toContain('30');
    const [key] = queryClient.getQueryCache().getAll().map((q) => q.queryKey);
    expect(key).toEqual(
      tournamentListKeys.upcoming({
        mine: true,
        memberOrgIds: [30, 32],
        openSignups: true,
        day: cutoffDayKey(new Date()),
      }),
    );
  });

  it('keys mine for different memberships apart', async () => {
    const { queryClient, wrapper } = setup();
    renderHook(
      () => useUpcomingTournaments({ mine: true, memberOrgIds: [30] }, { enabled: true }),
      { wrapper },
    );
    renderHook(
      () => useUpcomingTournaments({ mine: true, memberOrgIds: [31] }, { enabled: true }),
      { wrapper },
    );
    await waitFor(() => expect(getTournamentsMock).toHaveBeenCalledTimes(2));
    expect(queryClient.getQueryCache().getAll()).toHaveLength(2);
  });

  it('keys mine without memberships apart from no organization filter', async () => {
    const { queryClient, wrapper } = setup();
    renderHook(() => useUpcomingTournaments({ mine: true, memberOrgIds: [] }, { enabled: true }), {
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
      () => useArchivedTournaments({ mine: true, memberOrgIds: [30] }, { enabled: true }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getTournamentsPageMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ mine: true, page: 1 }),
    );
  });
});

describe('placeholder data across scopes', () => {
  function pending<T>(): Promise<T> {
    return new Promise<T>(() => {});
  }

  async function switchUpcoming(from: TournamentListQuery, to: TournamentListQuery) {
    getTournamentsMock.mockResolvedValueOnce([tournament(1)]);
    const { wrapper } = setup();
    const { result, rerender } = renderHook(
      ({ params }: { params: TournamentListQuery }) =>
        useUpcomingTournaments(params, { enabled: true }),
      { wrapper, initialProps: { params: from } },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    getTournamentsMock.mockReturnValueOnce(pending());
    rerender({ params: to });
    await waitFor(() => expect(getTournamentsMock).toHaveBeenCalledTimes(2));
    return result;
  }

  it('drops the previous list when switching all to mine', async () => {
    const result = await switchUpcoming({}, { mine: true, memberOrgIds: [30], openSignups: true });
    expect(result.current.data).toBeUndefined();
    expect(result.current.isPlaceholderData).toBe(false);
  });

  it('drops the previous list when switching mine to all', async () => {
    const result = await switchUpcoming({ mine: true, memberOrgIds: [30] }, {});
    expect(result.current.data).toBeUndefined();
  });

  it('keeps the previous list while a filter changes within the same scope', async () => {
    const result = await switchUpcoming(
      { mine: true, memberOrgIds: [30] },
      { mine: true, memberOrgIds: [30], league: 31 },
    );
    expect(result.current.isPlaceholderData).toBe(true);
    expect(result.current.data?.map((t) => t.pk)).toEqual([1]);
  });

  it('drops archived pages when the scope kind changes', async () => {
    getTournamentsPageMock.mockResolvedValueOnce(page([1], null));
    const { wrapper } = setup();
    const { result, rerender } = renderHook(
      ({ params }: { params: TournamentListQuery }) =>
        useArchivedTournaments(params, { enabled: true }),
      { wrapper, initialProps: { params: { organization: 30 } as TournamentListQuery } },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    getTournamentsPageMock.mockReturnValueOnce(pending());
    rerender({ params: { mine: true, memberOrgIds: [30] } });
    await waitFor(() => expect(getTournamentsPageMock).toHaveBeenCalledTimes(2));
    expect(result.current.data).toBeUndefined();
    expect(result.current.tournaments).toEqual([]);
  });
});

describe('useArchivedTournaments', () => {
  it('does not fetch while disabled', async () => {
    const { wrapper } = setup();
    renderHook(() => useArchivedTournaments({}, { enabled: false }), { wrapper });
    await new Promise((r) => setTimeout(r, 20));
    expect(getTournamentsPageMock).not.toHaveBeenCalled();
  });

  it('follows the cursor in next on its own origin and dedupes across pages', async () => {
    getTournamentsPageMock
      .mockResolvedValueOnce(
        page([1, 2], 'http://other/api/tournaments-list/?bucket=archived&cursor=tok%2D2'),
      )
      .mockResolvedValueOnce(page([2, 3], 'http://other/api/tournaments-list/?cursor=tok-3'))
      .mockResolvedValueOnce(page([4], null));
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
    expect(getTournamentsPageMock).toHaveBeenLastCalledWith({
      bucket: 'archived',
      organizationId: 30,
      leagueId: undefined,
      search: undefined,
      cursor: 'tok-2',
    });
    await act(async () => {
      await result.current.fetchNextPage();
    });

    await waitFor(() => expect(result.current.hasNextPage).toBe(false));
    expect(getTournamentsPageMock).toHaveBeenCalledTimes(3);
    expect(getTournamentsPageMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ cursor: 'tok-3' }),
    );
    for (const call of getTournamentsPageMock.mock.calls) {
      expect(JSON.stringify(call)).not.toContain('http://other');
      expect(call[0]).not.toHaveProperty('page', 2);
    }
    expect(result.current.tournaments.map((t) => t.pk)).toEqual([1, 2, 3, 4]);
  });

  it('stops when next carries no cursor', async () => {
    getTournamentsPageMock.mockResolvedValueOnce(page([1], 'http://other/x?page=2'));
    const { wrapper } = setup();
    const { result } = renderHook(
      () => useArchivedTournaments({}, { enabled: true }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.hasNextPage).toBe(false);
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

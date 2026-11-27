// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, render, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useTournamentStore } from '~/store/tournamentStore';
import { useUserStore } from '~/store/userStore';
import TournamentDetailPage from '../TournamentDetailPage';

vi.mock('~/hooks/useTournament', () => ({
  useTournament: () => ({
    data: { pk: 7, name: 'Cup', teams: [] },
    isLoading: false,
    error: null,
  }),
}));
vi.mock('~/hooks/useTournamentSocket', () => ({
  useTournamentSocket: () => undefined,
}));
vi.mock('../tabs/TournamentTabs', () => ({ default: () => null }));

const routers: ReturnType<typeof createMemoryRouter>[] = [];
const queryClients: QueryClient[] = [];
const matchPath = '/tournament/7/bracket/match/42';
let routeGate: Promise<void> = Promise.resolve();
const ownMatchState = {
  bracketMatchSelection: { tournamentId: 7, matchId: '42' },
};

async function mount(
  pathname = '/tournament/7/bracket',
  state: unknown = null,
) {
  const router = createMemoryRouter(
    [
      {
        path: '/tournament/:pk/*',
        loader: async () => {
          await routeGate;
          return null;
        },
        element: <TournamentDetailPage />,
        HydrateFallback: () => null,
      },
    ],
    { initialEntries: [{ pathname, state }] },
  );
  routers.push(router);
  const queryClient = new QueryClient();
  queryClients.push(queryClient);
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await waitFor(() =>
    expect(useTournamentStore.getState().activeTab).toBe(
      pathname.split('/')[3],
    ),
  );
  return router;
}

beforeEach(() => {
  routeGate = Promise.resolve();
  useTournamentStore.setState({
    activeTab: 'players',
    pendingMatchId: null,
    pendingDraftId: null,
  });
  useUserStore.setState({ currentUser: undefined });
});

afterEach(() => {
  cleanup();
  routers.splice(0).forEach((router) => router.dispose());
  queryClients.splice(0).forEach((client) => client.clear());
});

describe('tournament match deep-link handoff', () => {
  it('does not reopen a locally closed match when its replace navigation completes', async () => {
    const router = await mount();
    let releaseRoute!: () => void;
    routeGate = new Promise<void>((resolve) => {
      releaseRoute = resolve;
    });

    let navigation!: Promise<void>;
    act(() => {
      navigation = router.navigate(matchPath, {
        replace: true,
        state: ownMatchState,
      });
    });
    expect(router.state.navigation.state).toBe('loading');
    await act(async () => {
      releaseRoute();
      await navigation;
    });

    expect(router.state.historyAction).toBe('REPLACE');
    expect(useTournamentStore.getState().pendingMatchId).toBeNull();
  });

  it('opens an initial deep link even when history retains the local-selection marker', async () => {
    const router = await mount(matchPath, ownMatchState);

    expect(router.state.historyAction).toBe('POP');
    expect(useTournamentStore.getState().pendingMatchId).toBe('42');
  });

  it('opens unmarked replace links to the same match', async () => {
    const router = await mount();
    await act(() => router.navigate(matchPath, { replace: true }));

    expect(useTournamentStore.getState().pendingMatchId).toBe('42');
  });

  it.each([
    { tournamentId: 7, matchId: '43' },
    { tournamentId: 8, matchId: '42' },
  ])('does not suppress a marker for another target: %j', async (selection) => {
    const router = await mount();
    await act(() =>
      router.navigate(matchPath, {
        replace: true,
        state: { bracketMatchSelection: selection },
      }),
    );

    expect(useTournamentStore.getState().pendingMatchId).toBe('42');
  });

  it('opens a different match after a locally selected match', async () => {
    const router = await mount();
    await act(() =>
      router.navigate(matchPath, { replace: true, state: ownMatchState }),
    );
    await act(() => router.navigate('/tournament/7/bracket/match/43'));

    expect(useTournamentStore.getState().pendingMatchId).toBe('43');
  });

  it('opens marked history entries on browser back and forward', async () => {
    const router = await mount('/tournament/7/players');
    await act(() => router.navigate('/tournament/7/bracket'));
    await act(() =>
      router.navigate(matchPath, { replace: true, state: ownMatchState }),
    );
    await act(() => router.navigate(-1));
    expect(useTournamentStore.getState().pendingMatchId).toBeNull();
    await act(() => router.navigate(1));
    expect(router.state.historyAction).toBe('POP');
    expect(useTournamentStore.getState().pendingMatchId).toBe('42');

    await act(() => router.navigate('/tournament/7/bracket'));
    await act(() => router.navigate(-1));
    expect(router.state.historyAction).toBe('POP');
    expect(useTournamentStore.getState().pendingMatchId).toBe('42');
  });
});

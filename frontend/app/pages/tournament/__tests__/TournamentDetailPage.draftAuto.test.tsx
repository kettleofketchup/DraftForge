// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { DraftRoundType, DraftType } from '~/components/teamdraft/types';
import type { TournamentType } from '~/components/tournament/types';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import { useDraftWebSocketStore } from '~/store/draftWebSocketStore';
import { useTournamentStore } from '~/store/tournamentStore';
import { useUserStore } from '~/store/userStore';
import TournamentDetailPage from '../TournamentDetailPage';

vi.mock('~/hooks/useTournament', () => ({
  useTournament: () => ({ data: tournament, isLoading: false, error: null }),
}));
vi.mock('~/hooks/useTournamentSocket', () => ({
  useTournamentSocket: () => undefined,
}));
vi.mock('../tabs/TournamentTabs', async () => {
  const { DraftModal } = await import('~/components/teamdraft/draftModal');
  return { default: DraftModal };
});
vi.mock('~/components/teamdraft/draftRoundView', async () => {
  const { TurnIndicator } =
    await import('~/components/teamdraft/roundView/TurnIndicator');
  return { DraftRoundView: TurnIndicator };
});
vi.mock('~/components/teamdraft/hooks/useDraftLive', () => ({
  useDraftLive: () => ({ isPolling: false, forceRefresh: vi.fn() }),
}));
vi.mock('~/components/teamdraft/hooks/useAutoRefreshDraft', () => ({
  useAutoRefreshDraft: () => ({ refresh: vi.fn() }),
}));

const captainA = { pk: 7, username: 'Captain A' } as UserType;
const captainB = { pk: 8, username: 'Captain B' } as UserType;
const rounds = [
  { pk: 303, pick_number: 1, captain: captainB, choice: null, skip_count: 0 },
  { pk: 301, pick_number: 2, captain: captainA, choice: null, skip_count: 1 },
] as DraftRoundType[];
const draft = {
  pk: 21,
  state: 'drafting',
  latest_round: 303,
  draft_rounds: rounds,
  draft_options: { timer_enabled: true },
} as DraftType;
const tournament = {
  pk: 952,
  name: 'Timer cup',
  draft,
  teams: [
    { pk: 1, captain: captainA, members: [captainA] },
    { pk: 2, captain: captainB, members: [captainB] },
  ],
} as TournamentType;

const routers: ReturnType<typeof createMemoryRouter>[] = [];
const queryClients: QueryClient[] = [];

async function mount(initialPath = '/tournament/952/teams') {
  let releaseDraftRoute!: () => void;
  const draftRouteReady = new Promise<void>((resolve) => {
    releaseDraftRoute = resolve;
  });
  const router = createMemoryRouter(
    [
      {
        path: '/tournament/:pk/*',
        loader: async ({ params }) => {
          if (params['*'] === 'teams/draft') await draftRouteReady;
          return null;
        },
        element: <TournamentDetailPage />,
        HydrateFallback: () => null,
      },
    ],
    { initialEntries: [initialPath] },
  );
  routers.push(router);
  const queryClient = new QueryClient();
  queryClients.push(queryClient);
  render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <RouterProvider router={router} />
      </TooltipProvider>
    </QueryClientProvider>,
  );
  if (initialPath.endsWith('/draft')) {
    await act(async () => releaseDraftRoute());
  }
  await screen.findByTestId('liveTeamDraftButton');
  return { router, releaseDraftRoute };
}

beforeEach(() => {
  useTournamentStore.setState({ live: false, autoAdvance: false });
  useUserStore.setState({
    tournament,
    draft,
    curDraftRound: rounds[0],
    currentUser: captainA,
  });
  useDraftWebSocketStore.setState({
    draftState: { ...draft, tournament } as never,
    forceJumpToRoundPk: null,
    connect: vi.fn(),
    disconnect: vi.fn(),
  });
});

afterEach(() => {
  cleanup();
  routers.splice(0).forEach((router) => router.dispose());
  queryClients.splice(0).forEach((client) => client.clear());
});

describe('team draft Auto initialization', () => {
  it('enables Auto before a locally opened modal can be used', async () => {
    const { router } = await mount();
    fireEvent.click(screen.getByTestId('liveTeamDraftButton'));

    expect(router.state.location.pathname).toBe('/tournament/952/teams');
    expect(
      screen.getByRole('dialog', { name: 'Tournament Draft' }),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Auto' })).toHaveClass(
      'bg-info/15',
    );
  });

  it('keeps manual browsing when the delayed draft route finishes opening', async () => {
    const { router, releaseDraftRoute } = await mount();
    fireEvent.click(screen.getByTestId('liveTeamDraftButton'));
    expect(screen.getByRole('button', { name: 'Auto' })).toHaveClass(
      'bg-info/15',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Auto' }));
    fireEvent.click(screen.getAllByTestId('nextRoundButton')[0]);
    expect(screen.getByTestId('turn-indicator-deferred')).toHaveTextContent(
      'Pick #2 — deferred, Captain A picks after #1',
    );

    await act(async () => releaseDraftRoute());

    expect(router.state.location.pathname).toBe('/tournament/952/teams/draft');
    expect(screen.getByRole('button', { name: 'Auto' })).toHaveClass(
      'bg-muted/50',
    );
    expect(screen.getByTestId('turn-indicator-deferred')).toHaveTextContent(
      'Pick #2 — deferred, Captain A picks after #1',
    );
  });

  it('reinitializes Auto when explicitly reopening the modal', async () => {
    const { router } = await mount('/tournament/952/teams/draft');
    fireEvent.click(screen.getByRole('button', { name: 'Auto' }));
    await act(async () =>
      fireEvent.click(screen.getByTestId('close-draft-modal')),
    );
    expect(router.state.location.pathname).toBe('/tournament/952/teams');

    fireEvent.click(screen.getByTestId('liveTeamDraftButton'));

    expect(screen.getByRole('button', { name: 'Auto' })).toHaveClass(
      'bg-info/15',
    );
  });

  it('enables Auto when opening a draft URL directly', async () => {
    await mount('/tournament/952/teams/draft');

    expect(
      screen.getByRole('dialog', { name: 'Tournament Draft' }),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Auto' })).toHaveClass(
      'bg-info/15',
    );
    expect(useUserStore.getState().curDraftRound.pk).toBe(303);
  });
});

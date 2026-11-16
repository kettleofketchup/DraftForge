// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useBracketStore } from '~/store/bracketStore';
import { useTournamentStore } from '~/store/tournamentStore';
import { BracketView } from '../BracketView';
import type { BracketMatch } from '../types';

const { navigate, getLayoutedElements } = vi.hoisted(() => ({
  navigate: vi.fn(),
  getLayoutedElements: vi.fn(),
}));

vi.mock('react-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router')>()),
  useNavigate: () => navigate,
}));

vi.mock('@xyflow/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@xyflow/react')>();
  type StubProps = {
    nodes: { id: string; type?: string }[];
    nodesDraggable?: boolean;
    onNodeClick?: (event: unknown, node: { id: string }) => void;
  };
  return {
    ...actual,
    ReactFlow: ({ nodes, nodesDraggable, onNodeClick }: StubProps) => (
      <div data-testid="flow" data-draggable={String(nodesDraggable)}>
        {nodes
          .filter((n) => n.type === 'match')
          .map((n) => (
            <div
              key={n.id}
              role="button"
              data-testid={`node-${n.id}`}
              onClick={(e) => onNodeClick?.(e, n)}
            />
          ))}
      </div>
    ),
    Background: () => null,
    Panel: () => null,
  };
});

vi.mock('~/store/userStore', async () => {
  const { create } = await import('zustand');
  const store = create(() => ({
    currentUser: { pk: 1 },
    tournament: { pk: 7, teams: [] },
    isStaff: () => true,
  }));
  return { useUserStore: store };
});
vi.mock('~/store/bracketStore', async () => {
  const { create } = await import('zustand');
  const store = create(() => ({
    matches: [] as BracketMatch[],
    isDirty: false,
    setMatchWinner: () => {},
    advanceWinner: () => {},
    unsetMatchWinner: () => {},
  }));
  return { useBracketStore: store };
});
vi.mock('~/store/tournamentStore', async () => {
  const { create } = await import('zustand');
  const store = create<{
    pendingDraftId: number | null;
    pendingMatchId: string | null;
    setPendingDraftId: (id: number | null) => void;
    setPendingMatchId: (id: string | null) => void;
  }>((set) => ({
    pendingDraftId: null,
    pendingMatchId: null,
    setPendingDraftId: (pendingDraftId) => set({ pendingDraftId }),
    setPendingMatchId: (pendingMatchId) => set({ pendingMatchId }),
  }));
  return { useTournamentStore: store };
});
vi.mock('~/components/organization', () => ({
  useOrganization: () => ({ organization: undefined }),
}));
vi.mock('~/hooks/usePermissions', () => ({
  useCanEditTournament: () => true,
  useIsLeagueStaff: () => true,
}));
vi.mock('~/hooks/useBracket', () => ({
  useBracketQuery: () => ({ isLoading: false, data: { matches: [] } }),
  usePersistMatchResult: () => ({ isPending: false, mutate: vi.fn() }),
}));
vi.mock('~/hooks/useHeroDraft', () => ({
  useCreateHeroDraft: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useResetHeroDraft: () => ({ isPending: false, mutateAsync: vi.fn() }),
}));
vi.mock('~/hooks/useGameLobby', () => ({
  useGameLobby: () => ({ data: undefined }),
}));
vi.mock('~/components/bracket/hooks/useElkLayout', () => ({
  useElkLayout: () => ({ getLayoutedElements }),
}));
vi.mock('~/components/bracket/controls/BracketToolbar', () => ({
  BracketToolbar: () => <div data-testid="bracket-toolbar" />,
}));
vi.mock('~/components/herodraft/HeroDraftModal', () => ({
  HeroDraftModal: () => <div data-testid="nested-herodraft-modal" />,
}));
vi.mock('~/components/lobby/LobbyPanel', () => ({
  LobbyPanel: () => <div data-testid="lobby-panel" />,
}));
vi.mock('~/components/bracket/modals/DotaMatchStatsModal', () => ({
  DotaMatchStatsModal: () => null,
}));
vi.mock('~/components/bracket/modals/LinkSteamMatchModal', () => ({
  LinkSteamMatchModal: () => null,
}));

const team = (pk: number, name: string) =>
  ({
    pk,
    name,
    captain: { pk: pk * 10, username: name },
  }) as unknown as BracketMatch['radiantTeam'];

const match: BracketMatch = {
  id: 'w-1-0',
  gameId: 42,
  round: 1,
  position: 0,
  bracketType: 'winners',
  eliminationType: 'double',
  radiantTeam: team(1, 'Ember Lynx'),
  direTeam: team(2, 'Cinder'),
  status: 'live',
  herodraft_id: 156,
};

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient();
  return (
    <MemoryRouter initialEntries={['/activity']}>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
}

describe('BracketView embedded in the Activity', () => {
  beforeEach(() => {
    navigate.mockReset();
    useBracketStore.setState({ matches: [match], isDirty: false });
    useTournamentStore.setState({ pendingDraftId: null, pendingMatchId: null });
  });

  it('opens an openable hero draft from a bracket node without navigating', async () => {
    const onOpenHeroDraft = vi.fn();
    render(
      <BracketView
        tournamentId={7}
        embedded
        openableDraftIds={new Set([156])}
        onOpenHeroDraft={onOpenHeroDraft}
      />,
      { wrapper: Wrapper },
    );

    fireEvent.click(await screen.findByTestId('node-w-1-0'));
    expect(screen.getByTestId('matchStatsModal')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('view-draft-btn'));

    expect(onOpenHeroDraft).toHaveBeenCalledWith(156);
    expect(navigate).not.toHaveBeenCalled();
    expect(
      screen.queryByTestId('nested-herodraft-modal'),
    ).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByTestId('matchStatsModal')).not.toBeInTheDocument(),
    );
  });

  it('reports a match opening so the openable drafts can refresh', async () => {
    const onMatchOpen = vi.fn();
    render(
      <BracketView
        tournamentId={7}
        embedded
        openableDraftIds={new Set()}
        onOpenHeroDraft={vi.fn()}
        onMatchOpen={onMatchOpen}
      />,
      { wrapper: Wrapper },
    );

    expect(onMatchOpen).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByTestId('node-w-1-0'));
    expect(screen.getByTestId('matchStatsModal')).toBeInTheDocument();
    await waitFor(() => expect(onMatchOpen).toHaveBeenCalledTimes(1));
  });

  it('shows no open-draft button when the draft is not openable', async () => {
    render(
      <BracketView
        tournamentId={7}
        embedded
        openableDraftIds={new Set()}
        onOpenHeroDraft={vi.fn()}
      />,
      { wrapper: Wrapper },
    );

    fireEvent.click(await screen.findByTestId('node-w-1-0'));
    expect(screen.getByTestId('matchStatsModal')).toBeInTheDocument();
    expect(screen.queryByTestId('view-draft-btn')).not.toBeInTheDocument();
  });

  it('hides the toolbar, locks nodes and closes the match without navigating', async () => {
    render(<BracketView tournamentId={7} embedded header={<p>hdr</p>} />, {
      wrapper: Wrapper,
    });

    expect(screen.queryByTestId('bracket-toolbar')).not.toBeInTheDocument();
    expect(screen.getByText('hdr')).toBeInTheDocument();
    expect(screen.getByTestId('flow').dataset.draggable).toBe('false');
    expect(screen.getByTestId('bracketContainer').className).not.toContain(
      'h-[700px]',
    );

    fireEvent.click(await screen.findByTestId('node-w-1-0'));
    fireEvent.click(screen.getByTestId('dialog-close-button'));

    expect(navigate).not.toHaveBeenCalled();
  });

  it('clears pending deep-link ids instead of opening them', async () => {
    useTournamentStore.setState({ pendingDraftId: 156, pendingMatchId: '42' });
    render(<BracketView tournamentId={7} embedded />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(useTournamentStore.getState().pendingDraftId).toBeNull();
      expect(useTournamentStore.getState().pendingMatchId).toBeNull();
    });
    expect(
      screen.queryByTestId('nested-herodraft-modal'),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId('matchStatsModal')).not.toBeInTheDocument();
  });

  it('keeps the website toolbar and match URL navigation', async () => {
    render(<BracketView tournamentId={7} />, { wrapper: Wrapper });

    expect(screen.getByTestId('bracket-toolbar')).toBeInTheDocument();
    expect(screen.getByTestId('flow').dataset.draggable).toBe('true');
    fireEvent.click(await screen.findByTestId('node-w-1-0'));

    expect(navigate).toHaveBeenCalledWith('/tournament/7/bracket/match/42', {
      replace: true,
    });
  });
});

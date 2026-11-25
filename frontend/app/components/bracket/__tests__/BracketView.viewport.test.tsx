// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, waitFor } from '@testing-library/react';
import type { NodeChange } from '@xyflow/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useBracketStore } from '~/store/bracketStore';
import { useTournamentStore } from '~/store/tournamentStore';
import { BracketView } from '../BracketView';
import type { BracketMatch } from '../types';

const { getLayoutedElements, fitView, setViewport, flow } = vi.hoisted(() => ({
  getLayoutedElements: vi.fn(),
  fitView: vi.fn(),
  setViewport: vi.fn(),
  flow: {
    onNodesChange: undefined as undefined | ((changes: NodeChange[]) => void),
  },
}));

vi.mock('@xyflow/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@xyflow/react')>();
  type StubProps = {
    nodes: { id: string; type?: string }[];
    onNodesChange?: (changes: NodeChange[]) => void;
  };
  return {
    ...actual,
    useReactFlow: () => ({
      fitView,
      setViewport,
      getViewport: () => ({ x: 0, y: 0, zoom: 1 }),
    }),
    ReactFlow: ({ nodes, onNodesChange }: StubProps) => {
      flow.onNodesChange = onNodesChange;
      return <div data-testid="flow" data-count={nodes.length} />;
    },
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
vi.mock('~/hooks/useCanManageTournament', () => ({
  useCanManageCurrentTournament: () => true,
}));
vi.mock('~/hooks/useBracket', () => ({
  MATCH_RESULT_MUTATION_KEY: ['bracket-match-result'],
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

const baseMatch: BracketMatch = {
  id: 'w-1-0',
  gameId: 42,
  round: 1,
  position: 0,
  bracketType: 'winners',
  eliminationType: 'double',
  radiantTeam: team(1, 'Ember Lynx'),
  direTeam: team(2, 'Cinder'),
  status: 'live',
};

const secondMatch: BracketMatch = {
  ...baseMatch,
  id: 'w-1-1',
  gameId: 43,
  position: 1,
};

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient();
  return (
    <MemoryRouter initialEntries={['/activity']}>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
}

const settle = () =>
  act(() => new Promise<void>((resolve) => setTimeout(resolve, 120)));

describe.each([
  ['embedded (Activity)', true, fitView],
  ['website', false, setViewport],
] as const)('BracketView viewport, %s', (_label, embedded, viewportSpy) => {
  beforeEach(() => {
    fitView.mockReset();
    setViewport.mockReset();
    flow.onNodesChange = undefined;
    useBracketStore.setState({ matches: [baseMatch], isDirty: false });
    useTournamentStore.setState({ pendingDraftId: null, pendingMatchId: null });
  });

  const mount = async () => {
    render(<BracketView tournamentId={7} embedded={embedded} />, {
      wrapper: Wrapper,
    });
    await waitFor(() => expect(viewportSpy).toHaveBeenCalledTimes(1));
    await settle();
    expect(viewportSpy).toHaveBeenCalledTimes(1);
  };

  it('keeps the viewport when a match is selected', async () => {
    await mount();
    act(() => {
      flow.onNodesChange?.([{ type: 'select', id: 'w-1-0', selected: true }]);
    });
    await settle();
    expect(viewportSpy).toHaveBeenCalledTimes(1);
  });

  it('keeps the viewport when nodes are re-measured', async () => {
    await mount();
    act(() => {
      flow.onNodesChange?.([
        {
          type: 'dimensions',
          id: 'w-1-0',
          dimensions: { width: 200, height: 80 },
        },
      ]);
    });
    await settle();
    expect(viewportSpy).toHaveBeenCalledTimes(1);
  });

  it('keeps the viewport when a result changes but the structure does not', async () => {
    await mount();
    act(() => {
      useBracketStore.setState({
        matches: [{ ...baseMatch, status: 'completed', winner: 'radiant' }],
      });
    });
    await settle();
    expect(viewportSpy).toHaveBeenCalledTimes(1);
  });

  it('refits when the bracket structure changes', async () => {
    await mount();
    act(() => {
      useBracketStore.setState({ matches: [baseMatch, secondMatch] });
    });
    await waitFor(() => expect(viewportSpy).toHaveBeenCalledTimes(2));
  });
});

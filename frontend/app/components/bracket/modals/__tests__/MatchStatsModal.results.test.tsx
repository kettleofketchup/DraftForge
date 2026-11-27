// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { BracketMatchDTO } from '~/components/bracket/schemas';
import { useBracketQuery } from '~/hooks/useBracket';
import { useBracketStore } from '~/store/bracketStore';
import { MatchStatsModal } from '../MatchStatsModal';

type Winner = 'radiant' | 'dire' | null;

const { loadBracket, advanceWinner, toast } = vi.hoisted(() => ({
  loadBracket: vi.fn(),
  advanceWinner: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('~/components/api/bracketAPI', () => ({
  loadBracket,
  advanceWinner,
  saveBracket: vi.fn(),
}));
vi.mock('sonner', () => ({ toast }));
vi.mock('~/store/userStore', async () => {
  const { create } = await import('zustand');
  const store = create(() => ({
    currentUser: { pk: 1 },
    tournament: { pk: 7 },
  }));
  return { useUserStore: store };
});
vi.mock('~/hooks/useCanManageTournament', () => ({
  useCanManageCurrentTournament: () => true,
}));
vi.mock('~/hooks/useHeroDraft', () => ({
  useCreateHeroDraft: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useResetHeroDraft: () => ({ isPending: false, mutateAsync: vi.fn() }),
}));
vi.mock('~/hooks/useGameLobby', () => ({
  useGameLobby: () => ({ data: undefined }),
}));
vi.mock('~/components/lobby/LobbyPanel', () => ({ LobbyPanel: () => null }));
vi.mock('../DotaMatchStatsModal', () => ({ DotaMatchStatsModal: () => null }));
vi.mock('../LinkSteamMatchModal', () => ({ LinkSteamMatchModal: () => null }));

const server: Record<number, Winner> = {};
const inFlight: Record<number, () => void> = {};

const team = (pk: number) => ({ pk, name: `Team ${pk}` });

function dto(pk: number, position: number): BracketMatchDTO {
  const radiant = team(position * 2 + 1);
  const dire = team(position * 2 + 2);
  const winner = server[pk];
  return {
    pk,
    round: 1,
    position,
    bracket_type: 'winners',
    elimination_type: 'double',
    radiant_team: radiant,
    dire_team: dire,
    winning_team:
      winner === 'radiant' ? radiant : winner === 'dire' ? dire : null,
    status: winner ? 'completed' : 'pending',
    gameid: null,
    herodraft_id: null,
    lobby_state: null,
  } as BracketMatchDTO;
}

const bracket = () => ({
  tournamentId: 7,
  version: `v-${server[42] ?? '-'}-${server[43] ?? '-'}`,
  matches: [dto(42, 0), dto(43, 1)],
});

function Harness({ matchId }: { matchId: string }) {
  useBracketQuery(7);
  const match = useBracketStore((s) => s.matches.find((m) => m.id === matchId));
  if (!match) return null;
  return <MatchStatsModal match={match} isOpen onClose={() => {}} />;
}

let qc: QueryClient;

function Providers({ children }: { children: ReactNode }) {
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
}

const winnerOf = (id: string) =>
  useBracketStore.getState().matches.find((m) => m.id === id)?.winner;

describe('back-to-back match results (issue #963)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    delete server[42];
    delete server[43];
    useBracketStore.setState({
      matches: [],
      isDirty: false,
      hasStructuralEdits: false,
      pendingResultWrites: 0,
      baseVersion: null,
    });
    loadBracket.mockImplementation(async () => bracket());
    advanceWinner.mockImplementation(
      (gameId: number, winner: Winner) =>
        new Promise((resolve) => {
          inFlight[gameId] = () => {
            server[gameId] = winner;
            resolve(dto(gameId, gameId === 42 ? 0 : 1));
          };
        }),
    );
  });

  it('persists both winners and the first refetch does not wipe the second', async () => {
    const { rerender } = render(<Harness matchId="w-1-0" />, {
      wrapper: Providers,
    });
    await waitFor(() => expect(winnerOf('w-1-0')).toBeUndefined());
    await waitFor(() => expect(screen.getByTestId('radiantWinsButton')));

    fireEvent.click(screen.getByTestId('radiantWinsButton'));
    await waitFor(() =>
      expect(advanceWinner).toHaveBeenCalledWith(42, 'radiant'),
    );

    rerender(<Harness matchId="w-1-1" />);
    fireEvent.click(screen.getByTestId('direWinsButton'));
    await waitFor(() => expect(advanceWinner).toHaveBeenCalledWith(43, 'dire'));

    await act(async () => inFlight[42]());
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(winnerOf('w-1-0')).toBe('radiant');
    expect(winnerOf('w-1-1')).toBe('dire');
    expect(useBracketStore.getState().isDirty).toBe(true);

    await act(async () => inFlight[43]());

    await waitFor(() => expect(useBracketStore.getState().isDirty).toBe(false));
    expect(winnerOf('w-1-0')).toBe('radiant');
    expect(winnerOf('w-1-1')).toBe('dire');
    await waitFor(() =>
      expect(useBracketStore.getState().baseVersion).toBe('v-radiant-dire'),
    );
    expect(server).toEqual({ 42: 'radiant', 43: 'dire' });
  });

  it('leaves a result for Save when the bracket has structural edits', async () => {
    render(<Harness matchId="w-1-0" />, { wrapper: Providers });
    await waitFor(() => expect(screen.getByTestId('radiantWinsButton')));
    act(() => {
      useBracketStore
        .getState()
        .assignTeamToSlot('w-1-1', 'radiant', team(9) as never);
    });

    fireEvent.click(screen.getByTestId('radiantWinsButton'));
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(advanceWinner).not.toHaveBeenCalled();
    expect(winnerOf('w-1-0')).toBe('radiant');
    expect(useBracketStore.getState().isDirty).toBe(true);
  });
});

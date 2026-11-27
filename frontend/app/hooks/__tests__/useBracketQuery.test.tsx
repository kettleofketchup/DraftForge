// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { AxiosError, AxiosHeaders } from 'axios';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { BracketMatchDTO } from '~/components/bracket/schemas';
import { mapApiMatchToMatch, useBracketStore } from '~/store/bracketStore';
import {
  reloadBracket,
  useBracketQuery,
  usePersistMatchResult,
  useSaveBracket,
} from '../useBracket';

const { loadBracket, saveBracket, advanceWinner, toast } = vi.hoisted(() => ({
  loadBracket: vi.fn(),
  saveBracket: vi.fn(),
  advanceWinner: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('~/components/api/bracketAPI', () => ({
  loadBracket,
  saveBracket,
  advanceWinner,
}));
vi.mock('sonner', () => ({ toast }));

const apiMatch = (
  overrides: Partial<BracketMatchDTO> = {},
): BracketMatchDTO => ({
  pk: 42,
  round: 1,
  position: 0,
  bracket_type: 'winners',
  elimination_type: 'double',
  radiant_team: { pk: 1, name: 'Ember Lynx' },
  dire_team: { pk: 2, name: 'Cinder' },
  status: 'live',
  gameid: null,
  herodraft_id: null,
  lobby_state: null,
  ...overrides,
});

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

async function refetchWith(
  result: { current: ReturnType<typeof useBracketQuery> },
  match: BracketMatchDTO,
) {
  loadBracket.mockResolvedValue({ tournamentId: 7, matches: [match] });
  await act(async () => {
    await result.current.refetch();
  });
  expect(loadBracket).toHaveBeenCalledTimes(2);
  await waitFor(() => expect(result.current.data?.matches[0]).toEqual(match));
}

describe('useBracketQuery store seeding', () => {
  beforeEach(() => {
    loadBracket.mockReset();
    useBracketStore.setState({ matches: [], isDirty: false });
    loadBracket.mockResolvedValue({ tournamentId: 7, matches: [apiMatch()] });
  });

  const mount = async () => {
    const { result } = renderHook(() => useBracketQuery(7), { wrapper });
    await waitFor(() =>
      expect(useBracketStore.getState().matches).toHaveLength(1),
    );
    return result;
  };

  it('pushes a herodraft_id-only change to the store', async () => {
    const result = await mount();
    expect(useBracketStore.getState().matches[0].herodraft_id).toBeUndefined();

    await refetchWith(result, apiMatch({ herodraft_id: 156 }));

    await waitFor(() =>
      expect(useBracketStore.getState().matches[0].herodraft_id).toBe(156),
    );
  });

  it('pushes a gameId-only change to the store', async () => {
    const result = await mount();
    expect(useBracketStore.getState().matches[0].gameId).toBe(42);

    await refetchWith(result, apiMatch({ pk: 99 }));

    await waitFor(() =>
      expect(useBracketStore.getState().matches[0].gameId).toBe(99),
    );
  });

  it('leaves the store untouched when nothing changed', async () => {
    const result = await mount();
    const before = useBracketStore.getState().matches;

    await refetchWith(result, apiMatch());

    expect(useBracketStore.getState().matches).toBe(before);
  });
});

describe('useBracketQuery with unsaved edits', () => {
  beforeEach(() => {
    loadBracket.mockReset();
    useBracketStore.setState({ matches: [], isDirty: false });
    loadBracket.mockResolvedValue({ tournamentId: 7, matches: [apiMatch()] });
  });

  const mountDirty = async () => {
    const { result } = renderHook(() => useBracketQuery(7), { wrapper });
    await waitFor(() =>
      expect(useBracketStore.getState().matches).toHaveLength(1),
    );
    const edited = useBracketStore
      .getState()
      .matches.map((m) => ({ ...m, status: 'completed' as const }));
    act(() => {
      useBracketStore.setState({ matches: edited, isDirty: true });
    });
    return { result, edited };
  };

  it('keeps the edits and flags a server change', async () => {
    const { result, edited } = await mountDirty();
    expect(result.current.serverChanged).toBe(false);

    await refetchWith(result, apiMatch({ dire_team: { pk: 3, name: 'Ash' } }));

    await waitFor(() => expect(result.current.serverChanged).toBe(true));
    expect(useBracketStore.getState().matches).toBe(edited);
    expect(useBracketStore.getState().isDirty).toBe(true);
  });

  it('keeps the loaded version until server changes are accepted', async () => {
    loadBracket.mockResolvedValue({
      tournamentId: 7,
      version: 'v1',
      matches: [apiMatch()],
    });
    const { result, edited } = await mountDirty();
    act(() => {
      useBracketStore.setState({ hasStructuralEdits: true });
    });
    loadBracket.mockResolvedValue({
      tournamentId: 7,
      version: 'v2',
      matches: [apiMatch({ dire_team: { pk: 3, name: 'Ash' } })],
    });
    await act(async () => {
      await result.current.refetch();
    });
    await waitFor(() => expect(result.current.serverChanged).toBe(true));
    expect(useBracketStore.getState().baseVersion).toBe('v1');
    expect(useBracketStore.getState().hasStructuralEdits).toBe(true);
    expect(useBracketStore.getState().matches).toBe(edited);

    act(() => {
      useBracketStore.setState({ isDirty: false });
    });
    await waitFor(() =>
      expect(useBracketStore.getState().baseVersion).toBe('v2'),
    );
    expect(useBracketStore.getState().hasStructuralEdits).toBe(false);
    expect(result.current.serverChanged).toBe(false);
  });

  it('does not flag a refetch that changed nothing on the server', async () => {
    const { result } = await mountDirty();

    await refetchWith(result, apiMatch());

    expect(result.current.serverChanged).toBe(false);
  });

  it('loads the server bracket once the edits are discarded', async () => {
    const { result } = await mountDirty();
    await refetchWith(result, apiMatch({ dire_team: { pk: 3, name: 'Ash' } }));
    await waitFor(() => expect(result.current.serverChanged).toBe(true));

    act(() => {
      useBracketStore.setState({ isDirty: false });
    });

    await waitFor(() =>
      expect(useBracketStore.getState().matches[0].direTeam?.name).toBe('Ash'),
    );
    expect(result.current.serverChanged).toBe(false);
  });
});

describe('useSaveBracket', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useBracketStore.setState({ matches: [], isDirty: true });
  });

  it('shows the roster conflict and keeps edits when Save is refused', async () => {
    const error =
      'ko_p1 also play for Team C. Resolve that before reopening this team.';
    const config = { headers: new AxiosHeaders() };
    saveBracket.mockRejectedValue(
      new AxiosError(
        'Request failed with status code 409',
        '409',
        config,
        null,
        {
          status: 409,
          statusText: 'Conflict',
          headers: {},
          config,
          data: {
            code: 'roster_conflict',
            error,
            details: { team_id: 1, user_ids: [2] },
          },
        },
      ),
    );
    const { result } = renderHook(() => useSaveBracket(7), { wrapper });

    await act(async () => {
      await result.current.mutateAsync([]).catch(() => undefined);
    });

    expect(toast.error).toHaveBeenCalledWith(
      `Failed to save bracket: ${error}`,
    );
    expect(toast.success).not.toHaveBeenCalled();
    expect(useBracketStore.getState().isDirty).toBe(true);
  });

  it('sends the loaded version and offers a reload when Save is stale', async () => {
    const local = mapApiMatchToMatch(apiMatch(), [apiMatch()]);
    useBracketStore.setState({
      matches: [{ ...local, radiantTeam: undefined }],
      isDirty: true,
      hasStructuralEdits: true,
      baseVersion: 'v1',
    });
    const config = { headers: new AxiosHeaders() };
    saveBracket.mockRejectedValue(
      new AxiosError(
        'Request failed with status code 409',
        '409',
        config,
        null,
        {
          status: 409,
          statusText: 'Conflict',
          headers: {},
          config,
          data: {
            code: 'bracket_stale',
            error: 'The bracket changed since you loaded it.',
            details: { current_version: 'v2' },
          },
        },
      ),
    );
    const fresh = apiMatch({
      status: 'completed',
      winning_team: { pk: 1, name: 'Ember Lynx' },
    });
    loadBracket.mockResolvedValue({
      tournamentId: 7,
      version: 'v2',
      matches: [fresh],
    });
    const { result } = renderHook(() => useSaveBracket(7), { wrapper });

    await act(async () => {
      await result.current
        .mutateAsync(useBracketStore.getState().matches)
        .catch(() => undefined);
    });

    expect(saveBracket).toHaveBeenCalledWith(7, expect.any(Array), 'v1');
    expect(toast.error).toHaveBeenCalledTimes(1);
    const [message, options] = toast.error.mock.calls[0];
    expect(message).toBe('The bracket changed since you loaded it.');
    expect(useBracketStore.getState().isDirty).toBe(true);
    expect(useBracketStore.getState().matches[0].radiantTeam).toBeUndefined();

    await act(async () => {
      options.action.onClick();
      await waitFor(() => expect(loadBracket).toHaveBeenCalled());
    });

    await waitFor(() =>
      expect(useBracketStore.getState().baseVersion).toBe('v2'),
    );
    const state = useBracketStore.getState();
    expect(state.isDirty).toBe(false);
    expect(state.hasStructuralEdits).toBe(false);
    expect(state.matches[0].winner).toBe('radiant');
    expect(state.matches[0].radiantTeam?.pk).toBe(1);
  });
});

describe('bracket store across tournaments', () => {
  const teamC = { pk: 3, name: 'Tidewater' };

  beforeEach(() => {
    vi.clearAllMocks();
    loadBracket.mockReset();
    useBracketStore.setState({
      tournamentId: null,
      matches: [],
      isDirty: false,
      isVirtual: true,
    });
  });

  const mountAt = async (tournamentId: number) => {
    loadBracket.mockImplementation(async (id: number) => ({
      tournamentId: id,
      matches: [apiMatch({ pk: id * 100 })],
    }));
    const hook = renderHook(({ id }) => useBracketQuery(id), {
      wrapper,
      initialProps: { id: tournamentId },
    });
    await waitFor(() =>
      expect(useBracketStore.getState().matches[0]?.gameId).toBe(
        tournamentId * 100,
      ),
    );
    return hook;
  };

  it('clears version, structural edits and pending writes on tournament switch', () => {
    useBracketStore.setState({
      tournamentId: 7,
      baseVersion: 'old',
      hasStructuralEdits: true,
      pendingResultWrites: 2,
      isDirty: true,
    });
    useBracketStore.getState().bindTournament(8);
    expect(useBracketStore.getState()).toMatchObject({
      tournamentId: 8,
      baseVersion: null,
      hasStructuralEdits: false,
      pendingResultWrites: 0,
      isDirty: false,
    });
    useBracketStore.getState().setMatches([]);
    expect(useBracketStore.getState().hasStructuralEdits).toBe(true);
  });

  it('does not reload an old tournament into the current store', async () => {
    useBracketStore.setState({ tournamentId: 8, baseVersion: 'current' });
    loadBracket.mockResolvedValue({
      tournamentId: 7,
      version: 'old',
      matches: [apiMatch()],
    });
    await reloadBracket(new QueryClient(), 7);
    expect(useBracketStore.getState().matches).toEqual([]);
    expect(useBracketStore.getState().baseVersion).toBe('current');
  });

  it.each(['success', 'error'])(
    'ignores a late result %s after switching tournaments',
    async (outcome) => {
      useBracketStore.getState().bindTournament(7);
      let finish: () => void = () => undefined;
      advanceWinner.mockImplementation(
        () =>
          new Promise((resolve, reject) => {
            finish = () =>
              outcome === 'success'
                ? resolve({})
                : reject(new Error('write failed'));
          }),
      );
      const { result } = renderHook(() => usePersistMatchResult(7), {
        wrapper,
      });
      let pending: Promise<unknown> = Promise.resolve();
      act(() => {
        pending = result.current
          .mutateAsync({ gameId: 42, winner: 'radiant' })
          .catch(() => undefined);
      });
      await waitFor(() => expect(advanceWinner).toHaveBeenCalled());
      expect(useBracketStore.getState().pendingResultWrites).toBe(1);
      act(() => {
        useBracketStore.getState().bindTournament(8);
        useBracketStore.setState({
          isDirty: true,
          pendingResultWrites: 1,
          baseVersion: 'current',
        });
      });
      await act(async () => {
        finish();
        await pending;
      });
      expect(useBracketStore.getState()).toMatchObject({
        tournamentId: 8,
        isDirty: true,
        pendingResultWrites: 1,
        baseVersion: 'current',
      });
    },
  );

  it('drops the previous tournament before the next one loads', async () => {
    const hook = await mountAt(7);
    loadBracket.mockImplementation(() => new Promise(() => undefined));

    hook.rerender({ id: 8 });

    expect(useBracketStore.getState().matches).toEqual([]);
    expect(useBracketStore.getState().tournamentId).toBe(8);
  });

  it('loads the next tournament even with unsaved edits on the previous one', async () => {
    const hook = await mountAt(7);
    act(() => {
      useBracketStore
        .getState()
        .assignTeamToSlot('w-1-0', 'radiant', teamC as never);
    });
    expect(useBracketStore.getState().isDirty).toBe(true);

    hook.rerender({ id: 8 });

    await waitFor(() =>
      expect(useBracketStore.getState().matches[0]?.gameId).toBe(800),
    );
    expect(loadBracket).toHaveBeenCalledWith(8);
    expect(useBracketStore.getState().isDirty).toBe(false);
    expect(useBracketStore.getState().matches[0].radiantTeam?.pk).toBe(1);
  });

  it('reloads a tournament after switching away and back', async () => {
    const hook = await mountAt(7);
    loadBracket.mockImplementation(() => new Promise(() => undefined));
    hook.rerender({ id: 8 });
    hook.rerender({ id: 7 });

    await waitFor(() =>
      expect(useBracketStore.getState().matches[0]?.gameId).toBe(700),
    );
  });

  it('refuses to save another tournament’s bracket', async () => {
    useBracketStore.setState({ tournamentId: 7, isDirty: true });
    const { result } = renderHook(() => useSaveBracket(8), { wrapper });

    await act(async () => {
      await result.current.mutateAsync([]).catch(() => undefined);
    });

    expect(saveBracket).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalled();
  });

  it('ignores a save that finishes after switching tournaments', async () => {
    useBracketStore.setState({ tournamentId: 7, isDirty: true });
    let finish: (value: unknown) => void = () => undefined;
    saveBracket.mockImplementation(
      () => new Promise((resolve) => (finish = resolve)),
    );
    const { result } = renderHook(() => useSaveBracket(7), { wrapper });

    let pending: Promise<unknown> = Promise.resolve();
    act(() => {
      pending = result.current.mutateAsync([]);
    });
    await waitFor(() => expect(saveBracket).toHaveBeenCalled());
    useBracketStore.setState({ tournamentId: 8, matches: [], isDirty: false });
    await act(async () => {
      finish({ tournamentId: 7, matches: [apiMatch({ pk: 700 })] });
      await pending;
    });

    expect(useBracketStore.getState().tournamentId).toBe(8);
    expect(useBracketStore.getState().matches).toEqual([]);
  });
});

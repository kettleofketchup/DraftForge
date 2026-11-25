// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { AxiosError, AxiosHeaders } from 'axios';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { BracketMatchDTO } from '~/components/bracket/schemas';
import { useBracketStore } from '~/store/bracketStore';
import { useBracketQuery, useSaveBracket } from '../useBracket';

const { loadBracket, saveBracket, toast } = vi.hoisted(() => ({
  loadBracket: vi.fn(),
  saveBracket: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('~/components/api/bracketAPI', () => ({
  loadBracket,
  saveBracket,
  advanceWinner: vi.fn(),
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
});

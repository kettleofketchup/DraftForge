import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { initDraftRounds } from '~/components/api/api';
import type {
  DraftResetConflict,
  DraftResetReport,
} from '~/components/api/types';
import type { DraftRoundType, TournamentType } from '~/index';
import {
  draftWsSelectors,
  useDraftWebSocketStore,
} from '~/store/draftWebSocketStore';
import type { WebSocketDraftState } from '~/types/draftEvent';
import { draftResetSummary, initDraftHook } from '../initDraftHook';

vi.mock('~/components/api/api', () => ({ initDraftRounds: vi.fn() }));
vi.mock('sonner', () => ({
  toast: {
    loading: vi.fn(() => 'toast-id'),
    success: vi.fn(),
    error: vi.fn(),
    dismiss: vi.fn(),
    promise: vi.fn(),
  },
}));

const referencesError = {
  response: {
    status: 409,
    data: {
      error: 'Teams are used by games or other records.',
      code: 'draft_reset_has_references',
      references: {
        'app.Game.radiant_team': 2,
        'app.Game.dire_team': 2,
        'app.Game.winning_team': 2,
      },
      usage: [
        {
          model: 'app.Game',
          label: 'game',
          label_plural: 'games',
          count: 2,
          teams: [{ pk: 1, name: 'Team A' }],
        },
      ],
    },
  },
};

const initialized = {
  pk: 7,
  teams: [],
  draft: { pk: 3, draft_rounds: [{ pk: 11 }] },
  draft_reset: {
    reset_teams: [1, 2, 3, 4],
    dropped_teams: [{ pk: 5, name: 'Gone', reason: 'no_captain' }],
    kept_teams: [],
    cleared_deputies: [],
  },
};

const mockedInit = vi.mocked(initDraftRounds);

function run(
  confirmForce: (conflict: DraftResetConflict) => Promise<boolean>,
  onReport?: (report: DraftResetReport) => void,
) {
  return initDraftHook({
    onReport,
    tournament: { pk: 7 } as TournamentType,
    setTournament: vi.fn(),
    setDraft: vi.fn(),
    curDraftRound: {} as DraftRoundType,
    setCurDraftRound: vi.fn(),
    confirmForce,
  });
}

describe('initDraftHook', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('re-posts with force after the references are confirmed', async () => {
    mockedInit
      .mockRejectedValueOnce(referencesError)
      .mockResolvedValueOnce(initialized as unknown as TournamentType);
    const confirmForce = vi.fn().mockResolvedValue(true);

    await run(confirmForce);

    expect(confirmForce).toHaveBeenCalledWith({
      references: referencesError.response.data.references,
      usage: referencesError.response.data.usage,
    });
    expect(mockedInit).toHaveBeenCalledTimes(2);
    expect(mockedInit.mock.calls[0][0]).not.toHaveProperty('force');
    expect(mockedInit.mock.calls[1][0]).toMatchObject({
      tournament_pk: 7,
      force: true,
    });
    expect(toast.error).not.toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith(
      'Draft initialized. 4 teams reset to captains, 1 dropped.',
      expect.anything(),
    );
  });

  it('hands the report on when teams were dropped or kept', async () => {
    mockedInit.mockResolvedValueOnce(initialized as unknown as TournamentType);
    const onReport = vi.fn();

    await run(vi.fn(), onReport);

    expect(onReport).toHaveBeenCalledWith(initialized.draft_reset);
  });

  it('does not open a summary when every team was simply reset', async () => {
    mockedInit.mockResolvedValueOnce({
      ...initialized,
      draft_reset: { ...initialized.draft_reset, dropped_teams: [] },
    } as unknown as TournamentType);
    const onReport = vi.fn();

    await run(vi.fn(), onReport);

    expect(onReport).not.toHaveBeenCalled();
  });

  it('leaves the success toast up: no dismiss after it is shown', async () => {
    mockedInit.mockResolvedValueOnce(initialized as unknown as TournamentType);

    await run(vi.fn());

    expect(toast.success).toHaveBeenCalledOnce();
    expect(vi.mocked(toast.success).mock.calls[0][1]).toMatchObject({
      id: 'toast-id',
    });
    expect(toast.dismiss).not.toHaveBeenCalled();
  });

  it('drops a completed WebSocket snapshot the restart replaced', async () => {
    useDraftWebSocketStore.setState({
      draftState: {
        pk: 3,
        state: 'completed',
        draft_rounds: [{ pk: 1, choice: 9 }],
      } as unknown as WebSocketDraftState,
    });
    mockedInit.mockResolvedValueOnce(initialized as unknown as TournamentType);

    await run(vi.fn());

    const ws = useDraftWebSocketStore.getState();
    expect(ws.draftState).toBeNull();
    expect(draftWsSelectors.isDraftCompleted(ws)).toBe(false);
  });

  it('keeps a WebSocket snapshot that already has the new rounds', async () => {
    const fresh = {
      pk: 3,
      state: 'drafting',
      draft_rounds: [{ pk: 11 }],
    } as unknown as WebSocketDraftState;
    useDraftWebSocketStore.setState({ draftState: fresh });
    mockedInit.mockResolvedValueOnce(initialized as unknown as TournamentType);

    await run(vi.fn());

    expect(useDraftWebSocketStore.getState().draftState).toBe(fresh);
  });

  it('stops without an error toast when the references are declined', async () => {
    mockedInit.mockRejectedValueOnce(referencesError);
    const confirmForce = vi.fn().mockResolvedValue(false);

    await run(confirmForce);

    expect(confirmForce).toHaveBeenCalledOnce();
    expect(mockedInit).toHaveBeenCalledOnce();
    expect(toast.error).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('shows the server error for any other failure without asking', async () => {
    mockedInit.mockRejectedValueOnce({
      response: { status: 400, data: { error: 'no captains assigned' } },
    });
    const confirmForce = vi.fn();

    await run(confirmForce);

    expect(confirmForce).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith(
      'Failed to initialize draft: no captains assigned',
      expect.anything(),
    );
  });
});

describe('draftResetSummary', () => {
  it('pluralises and lists only non-empty groups', () => {
    expect(
      draftResetSummary({
        reset_teams: [1],
        dropped_teams: [],
        kept_teams: [{ pk: 2, name: 'Kept', reason: 'no_captain' }],
        cleared_deputies: [],
      }),
    ).toBe(
      'Draft initialized. 1 team reset to captains, 1 kept out of the draft.',
    );
    expect(draftResetSummary(undefined)).toBe('Draft initialized.');
  });
});

import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { initDraftRounds } from '~/components/api/api';
import type { DraftRoundType, TournamentType } from '~/index';
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
      references: { 'app.Game.radiant_team': 2 },
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
  confirmForce: (references: Record<string, number>) => Promise<boolean>,
) {
  return initDraftHook({
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

    expect(confirmForce).toHaveBeenCalledWith({ 'app.Game.radiant_team': 2 });
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

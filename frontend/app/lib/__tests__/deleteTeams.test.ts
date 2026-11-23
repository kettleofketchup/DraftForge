import { AxiosError, AxiosHeaders } from 'axios';
import { describe, expect, it, vi } from 'vitest';
import type { TeamUsageCheck } from '~/components/api/teamAPI';
import { TeamUsageCheckSchema } from '~/components/api/teamAPI';
import {
  deleteTeamsInOrder,
  deleteTeamsMessage,
  teamInUseMessage,
} from '~/lib/deleteTeams';

function axiosError(status: number, data: unknown): AxiosError {
  const config = { headers: new AxiosHeaders() };
  return new AxiosError('failed', String(status), config, undefined, {
    status,
    statusText: '',
    headers: {},
    config,
    data,
  });
}

// Same shape as backend TeamUsage (app/services/team_references.py).
const gameUsage = {
  model: 'tournament.Game',
  label: 'game',
  label_plural: 'games',
  count: 2,
  teams: [{ pk: 2, name: 'Team B' }],
};
const inUseDetail = 'Team B is still used by 2 games and cannot be deleted.';

const inUse = axiosError(409, {
  code: 'team_in_use',
  detail: inUseDetail,
  usage: [gameUsage],
});

const free: TeamUsageCheck = { in_use: false, detail: null, usage: [] };
const used: TeamUsageCheck = {
  in_use: true,
  detail: inUseDetail,
  usage: [gameUsage],
};

describe('TeamUsageCheckSchema', () => {
  it('parses the backend usage body', () => {
    expect(TeamUsageCheckSchema.parse(used)).toEqual(used);
    expect(TeamUsageCheckSchema.parse(free)).toEqual(free);
  });
});

describe('deleteTeamsInOrder', () => {
  it('checks every team, then deletes every team in order', async () => {
    const checkUsage = vi.fn().mockResolvedValue(free);
    const remove = vi.fn().mockResolvedValue(undefined);
    const result = await deleteTeamsInOrder([{ pk: 1 }, { pk: 2 }], {
      checkUsage,
      remove,
    });
    expect(result).toEqual({ ok: true });
    expect(checkUsage.mock.calls).toEqual([[1], [2]]);
    expect(remove.mock.calls).toEqual([[1], [2]]);
  });

  it('deletes nothing when any team is in use', async () => {
    const checkUsage = vi
      .fn()
      .mockImplementation(async (pk: number) => (pk === 2 ? used : free));
    const remove = vi.fn().mockResolvedValue(undefined);
    const result = await deleteTeamsInOrder([{ pk: 1 }, { pk: 2 }, { pk: 3 }], {
      checkUsage,
      remove,
    });
    expect(result).toEqual({ ok: false, blocked: [inUseDetail] });
    expect(remove).not.toHaveBeenCalled();
  });

  it('deletes nothing when a usage check fails', async () => {
    const error = axiosError(403, { detail: 'Not allowed.' });
    const checkUsage = vi
      .fn()
      .mockResolvedValueOnce(free)
      .mockRejectedValueOnce(error);
    const remove = vi.fn();
    const result = await deleteTeamsInOrder([{ pk: 1 }, { pk: 2 }], {
      checkUsage,
      remove,
    });
    expect(result).toEqual({ ok: false, error, deleted: [] });
    expect(remove).not.toHaveBeenCalled();
  });

  it('stops at a delete refused after the check, reporting what went', async () => {
    const checkUsage = vi.fn().mockResolvedValue(free);
    const remove = vi
      .fn()
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(inUse)
      .mockResolvedValue(undefined);
    const result = await deleteTeamsInOrder([{ pk: 1 }, { pk: 2 }, { pk: 3 }], {
      checkUsage,
      remove,
    });
    expect(result).toEqual({ ok: false, error: inUse, deleted: [1] });
    expect(remove.mock.calls).toEqual([[1], [2]]);
  });

  it('succeeds with no teams', async () => {
    const checkUsage = vi.fn();
    const remove = vi.fn();
    expect(await deleteTeamsInOrder([], { checkUsage, remove })).toEqual({
      ok: true,
    });
    expect(checkUsage).not.toHaveBeenCalled();
    expect(remove).not.toHaveBeenCalled();
  });
});

describe('deleteTeamsMessage', () => {
  it('lists every blocking team and says nothing was deleted', () => {
    expect(
      deleteTeamsMessage({ ok: false, blocked: ['A is used.', 'B is used.'] }),
    ).toBe('No teams were deleted or created. A is used. B is used.');
  });

  it('says nothing was deleted when the first step failed', () => {
    expect(
      deleteTeamsMessage({ ok: false, error: new Error('x'), deleted: [] }),
    ).toBe(
      'Failed to delete the existing teams. No teams were deleted or created.',
    );
  });

  it('counts teams already deleted when a later delete failed', () => {
    expect(deleteTeamsMessage({ ok: false, error: inUse, deleted: [1] })).toBe(
      `${inUseDetail} 1 team was already deleted; no teams were created.`,
    );
    expect(
      deleteTeamsMessage({
        ok: false,
        error: new Error('x'),
        deleted: [1, 3],
      }),
    ).toBe(
      'Failed to delete the existing teams. 2 teams were already deleted; no teams were created.',
    );
  });
});

describe('teamInUseMessage', () => {
  it('returns the backend detail for a 409 team_in_use', () => {
    expect(teamInUseMessage(inUse)).toBe(inUseDetail);
  });

  it('returns null for other errors', () => {
    expect(
      teamInUseMessage(axiosError(403, { detail: 'Not allowed.' })),
    ).toBeNull();
    expect(teamInUseMessage(axiosError(500, 'oops'))).toBeNull();
    expect(
      teamInUseMessage(
        axiosError(409, { code: 'override_required', detail: 'x' }),
      ),
    ).toBeNull();
    expect(teamInUseMessage(new Error('network'))).toBeNull();
    expect(teamInUseMessage(undefined)).toBeNull();
  });
});

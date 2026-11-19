import { AxiosError, AxiosHeaders } from 'axios';
import { describe, expect, it, vi } from 'vitest';
import { deleteTeamsInOrder, teamInUseMessage } from '~/lib/deleteTeams';

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

const inUse = axiosError(409, {
  code: 'team_in_use',
  detail: 'Team A is used by 2 bracket games.',
  usage: [{ kind: 'game', count: 2 }],
});

describe('deleteTeamsInOrder', () => {
  it('deletes every team in order', async () => {
    const remove = vi.fn().mockResolvedValue(undefined);
    const result = await deleteTeamsInOrder([{ pk: 1 }, { pk: 2 }], remove);
    expect(result).toEqual({ ok: true });
    expect(remove.mock.calls).toEqual([[1], [2]]);
  });

  it('stops at the first refusal', async () => {
    const remove = vi
      .fn()
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(inUse)
      .mockResolvedValue(undefined);
    const result = await deleteTeamsInOrder(
      [{ pk: 1 }, { pk: 2 }, { pk: 3 }],
      remove,
    );
    expect(result).toEqual({ ok: false, error: inUse, deleted: [1] });
    expect(remove.mock.calls).toEqual([[1], [2]]);
  });

  it('succeeds with no teams', async () => {
    const remove = vi.fn();
    expect(await deleteTeamsInOrder([], remove)).toEqual({ ok: true });
    expect(remove).not.toHaveBeenCalled();
  });
});

describe('teamInUseMessage', () => {
  it('returns the backend detail for a 409 team_in_use', () => {
    expect(teamInUseMessage(inUse)).toBe('Team A is used by 2 bracket games.');
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

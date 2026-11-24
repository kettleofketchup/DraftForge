import { AxiosError, AxiosHeaders } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { patch } = vi.hoisted(() => ({ patch: vi.fn() }));

vi.mock('~/components/api/axios', () => ({
  api: { patch },
  default: { patch },
}));

import { setTeamPlacement } from '../bracketAPI';

beforeEach(() => {
  patch.mockReset();
});

describe('setTeamPlacement', () => {
  it('PATCHes the placement and parses the response', async () => {
    patch.mockResolvedValue({ data: { team_id: 9, placement: 3 } });
    const result = await setTeamPlacement(4, 9, 3);
    expect(patch).toHaveBeenCalledWith(
      '/bracket/tournaments/4/teams/9/placement/',
      { placement: 3 },
    );
    expect(result).toEqual({ team_id: 9, placement: 3 });
  });

  it('clears the placement with null', async () => {
    patch.mockResolvedValue({ data: { team_id: 9, placement: null } });
    const result = await setTeamPlacement(4, 9, null);
    expect(patch).toHaveBeenCalledWith(
      '/bracket/tournaments/4/teams/9/placement/',
      { placement: null },
    );
    expect(result.placement).toBeNull();
  });

  it('rejects a malformed response', async () => {
    patch.mockResolvedValue({ data: { team_id: 9, placement: 'x' } });
    await expect(setTeamPlacement(4, 9, 3)).rejects.toThrow();
  });

  it('propagates a roster conflict unchanged', async () => {
    const config = { headers: new AxiosHeaders() };
    const err = new AxiosError('failed', '409', config, undefined, {
      status: 409,
      statusText: '',
      headers: {},
      config,
      data: { code: 'roster_conflict', error: 'x', details: {} },
    });
    patch.mockRejectedValue(err);
    await expect(setTeamPlacement(4, 9, null)).rejects.toBe(err);
  });
});

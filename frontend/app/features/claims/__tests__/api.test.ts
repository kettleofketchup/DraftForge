import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { get } }));

import { getClaimRequests } from '../api';

const row = {
  id: 1,
  claimer: 2,
  claimer_username: 'claimer',
  claimer_discord_id: '123',
  claimer_avatar: null,
  target_user: 3,
  target_nickname: 'Target',
  target_username: null,
  target_discordNickname: null,
  target_steamid: 765,
  target_mmr: 4000,
  target_game_mmrs: { '1': 4000, '2': 0 },
  organization: 4,
  organization_name: 'Org',
  status: 'pending',
  reviewed_by: null,
  reviewed_by_username: null,
  rejection_reason: '',
  created_at: '2026-01-01T00:00:00Z',
  reviewed_at: null,
};

beforeEach(() => {
  get.mockReset();
});

describe('getClaimRequests', () => {
  it('filters by organization and status and parses the rows', async () => {
    get.mockResolvedValue({ data: [row] });
    const claims = await getClaimRequests({
      organizationId: 4,
      status: 'pending',
    });
    expect(get).toHaveBeenCalledWith('/claim-requests/', {
      params: { organization: 4, status: 'pending' },
    });
    expect(claims).toEqual([row]);
  });

  it('parses an approved claim whose target profile was merged away', async () => {
    const approved = {
      ...row,
      status: 'approved',
      target_user: null,
      target_nickname: null,
      target_steamid: null,
      target_mmr: null,
      target_game_mmrs: null,
      reviewed_by: 5,
      reviewed_by_username: 'admin',
      reviewed_at: '2026-01-02T00:00:00Z',
    };
    get.mockResolvedValue({ data: [approved] });
    const claims = await getClaimRequests({
      organizationId: 4,
      status: 'approved',
    });
    expect(claims).toEqual([approved]);
  });

  it('rejects a malformed body', async () => {
    get.mockResolvedValue({ data: [{ ...row, status: 'unknown' }] });
    await expect(
      getClaimRequests({ organizationId: 4 }),
    ).rejects.toBeInstanceOf(ZodError);
  });
});

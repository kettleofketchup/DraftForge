import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { get, post } }));

import { approveClaimRequest, getClaimRequests } from '../api';

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
  post.mockReset();
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

  it('rejects a malformed body', async () => {
    get.mockResolvedValue({ data: [{ ...row, status: 'unknown' }] });
    await expect(
      getClaimRequests({ organizationId: 4 }),
    ).rejects.toBeInstanceOf(ZodError);
  });
});

describe('approveClaimRequest', () => {
  it('posts the approval and returns the message', async () => {
    post.mockResolvedValue({ data: { message: 'Profile merged' } });
    await expect(approveClaimRequest(9)).resolves.toBe('Profile merged');
    expect(post).toHaveBeenCalledWith('/claim-requests/9/approve/');
  });

  it('rejects a malformed body', async () => {
    post.mockResolvedValue({ data: {} });
    await expect(approveClaimRequest(9)).rejects.toBeInstanceOf(ZodError);
  });
});

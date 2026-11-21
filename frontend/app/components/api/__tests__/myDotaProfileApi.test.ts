import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { get } }));

import { getMyDotaProfile } from '../myDotaProfileApi';

const body = {
  id: 1,
  org_user_id: 2,
  rank_status: 'active',
  rank_medal: 'Legend 1',
  rank_date: null,
  battle_cup_tier: null,
  mmr: null,
  rank_screenshot: null,
  battlecup_screenshot: null,
  unverified_friend_id: '',
  resolved_friend_id: '616161',
  pos_1: true,
  pos_2: false,
  pos_3: false,
  pos_4: false,
  pos_5: false,
};

beforeEach(() => {
  get.mockReset();
});

describe('getMyDotaProfile', () => {
  it('parses the body and keeps the resolved Friend ID', async () => {
    get.mockResolvedValue({ data: body });
    const profile = await getMyDotaProfile(7);
    expect(get).toHaveBeenCalledWith('/organizations/7/my-dota-profile/');
    expect(profile.resolved_friend_id).toBe('616161');
    expect(profile.unverified_friend_id).toBe('');
    expect(profile.positions.pos_1).toBe(true);
    expect(profile.rank_medal).toBe('Legend 1');
  });

  it('rejects a malformed body', async () => {
    get.mockResolvedValue({ data: { ...body, pos_1: 'yes' } });
    await expect(getMyDotaProfile(7)).rejects.toBeInstanceOf(ZodError);
  });
});

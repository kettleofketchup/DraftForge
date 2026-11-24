import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { get } }));

import { getOrganizationUsers } from '../orgAPI';

const member = {
  orgUserPk: 11,
  pk: 7,
  username: 'player7',
  nickname: 'Seven',
  guildNickname: null,
  discordNickname: 'seven#1',
  avatar: 'abc',
  discordId: '123456789012345678',
  positions: {
    pk: 3,
    carry: 5,
    mid: 0,
    offlane: 2,
    soft_support: 0,
    hard_support: 1,
  },
  steam_account_id: 1234,
  avatarUrl: 'https://cdn.discordapp.com/avatars/123456789012345678/abc.png',
  mmr: 4200,
  mmr_game_type: 1,
  game_mmrs: { '1': 4200, '2': 0 },
  league_mmr: null,
};

const steamOnlyMember = {
  ...member,
  orgUserPk: 12,
  pk: 8,
  username: null,
  nickname: null,
  discordNickname: null,
  avatar: null,
  discordId: null,
  positions: null,
  steam_account_id: null,
  avatarUrl: null,
  mmr: 0,
  game_mmrs: { '1': 0, '2': 0 },
};

beforeEach(() => {
  get.mockReset();
});

describe('getOrganizationUsers', () => {
  it('requests the org members and keeps every serializer field', async () => {
    get.mockResolvedValue({ data: [member, steamOnlyMember] });

    const users = await getOrganizationUsers(5);

    expect(get).toHaveBeenCalledWith('/organizations/5/users/');
    expect(users).toEqual([member, steamOnlyMember]);
  });

  it('rejects a member missing its OrgUser pk', async () => {
    const { orgUserPk: _, ...withoutOrgUserPk } = member;
    get.mockResolvedValue({ data: [withoutOrgUserPk] });

    await expect(getOrganizationUsers(5)).rejects.toBeInstanceOf(ZodError);
  });

  it('rejects a non-list body', async () => {
    get.mockResolvedValue({ data: { detail: 'Not found.' } });

    await expect(getOrganizationUsers(5)).rejects.toBeInstanceOf(ZodError);
  });
});

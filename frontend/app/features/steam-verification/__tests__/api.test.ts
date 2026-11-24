import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('~/components/api/axios', () => ({ default: { get, post } }));

import { getSteamVerification, setSteamVerification } from '../api';

const body = {
  steam_account_id: 123,
  steam_account_verified: true,
  steam_account_verified_at: '2026-11-22T10:00:00+00:00',
  steam_account_verified_org_name: 'Kettle League',
  steam_account_exists_checked: true,
  steam_profile_url: 'https://steamcommunity.com/profiles/76561197960265851',
  dotabuff_url: 'https://www.dotabuff.com/players/123',
  can_verify: true,
};

beforeEach(() => {
  get.mockReset();
  post.mockReset();
});

describe('getSteamVerification', () => {
  it('parses a realistic body', async () => {
    get.mockResolvedValue({ data: body });
    await expect(getSteamVerification(5)).resolves.toEqual(body);
    expect(get).toHaveBeenCalledWith('/users/5/steam-verification/');
  });

  it('parses a user with no Friend ID', async () => {
    const empty = {
      ...body,
      steam_account_id: null,
      steam_account_verified: false,
      steam_account_verified_at: null,
      steam_account_verified_org_name: null,
      steam_account_exists_checked: false,
      steam_profile_url: null,
      dotabuff_url: null,
      can_verify: false,
    };
    get.mockResolvedValue({ data: empty });
    await expect(getSteamVerification(5)).resolves.toEqual(empty);
  });

  it('rejects a malformed body with a ZodError', async () => {
    get.mockResolvedValue({ data: { ...body, can_verify: 'yes' } });
    await expect(getSteamVerification(5)).rejects.toBeInstanceOf(ZodError);
  });
});

describe('setSteamVerification', () => {
  it('posts the displayed id and parses the reply', async () => {
    post.mockResolvedValue({ data: body });
    await expect(setSteamVerification(5, true, 123)).resolves.toEqual(body);
    expect(post).toHaveBeenCalledWith('/users/5/steam-verification/', {
      verified: true,
      steam_account_id: 123,
    });
  });

  it('sends verified false to unverify', async () => {
    post.mockResolvedValue({
      data: { ...body, steam_account_verified: false },
    });
    await setSteamVerification(5, false, 123);
    expect(post).toHaveBeenCalledWith('/users/5/steam-verification/', {
      verified: false,
      steam_account_id: 123,
    });
  });

  it('rejects a malformed reply with a ZodError', async () => {
    post.mockResolvedValue({ data: { steam_account_id: 123 } });
    await expect(setSteamVerification(5, true, 123)).rejects.toBeInstanceOf(
      ZodError,
    );
  });
});

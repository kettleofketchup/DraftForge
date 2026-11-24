import { describe, expect, it } from 'vitest';

import { CoreUserSchema, UserSchema } from '~/components/user/schemas';
import { DotaProfileApiSchema } from '~/hooks/useUserProfile';

const verification = {
  steam_account_verified: true,
  steam_account_verified_at: '2026-11-22T10:00:00+00:00',
  steam_account_exists_checked: true,
};

const user = { pk: 5, username: 'player', steam_account_id: 123 };

describe('UserSchema Friend ID verification fields', () => {
  it('parses a payload without them', () => {
    const parsed = UserSchema.parse(user);
    expect(parsed.steam_account_verified).toBeUndefined();
    expect(parsed.steam_account_verified_at).toBeUndefined();
    expect(parsed.steam_account_exists_checked).toBeUndefined();
  });

  it('parses them when present', () => {
    expect(UserSchema.parse({ ...user, ...verification })).toMatchObject(
      verification,
    );
  });

  it('accepts a null verified_at', () => {
    const parsed = UserSchema.parse({
      ...user,
      steam_account_verified: false,
      steam_account_verified_at: null,
      steam_account_exists_checked: false,
    });
    expect(parsed.steam_account_verified_at).toBeNull();
  });

  it('parses the org name from an org member payload', () => {
    const parsed = UserSchema.parse({
      ...user,
      ...verification,
      steam_account_verified_org_name: 'Kettle League',
    });
    expect(parsed.steam_account_verified_org_name).toBe('Kettle League');
  });

  it('rejects a non-boolean verified flag', () => {
    expect(() =>
      UserSchema.parse({ ...user, steam_account_verified: 'yes' }),
    ).toThrow();
  });
});

describe('CoreUserSchema Friend ID verification fields', () => {
  it('keeps them as core keys for the user cache', () => {
    expect(Object.keys(CoreUserSchema.shape)).toEqual(
      expect.arrayContaining([
        'steam_account_verified',
        'steam_account_verified_at',
        'steam_account_verified_org_name',
        'steam_account_exists_checked',
      ]),
    );
  });

  it('parses with and without them', () => {
    expect(CoreUserSchema.parse(user).steam_account_verified).toBeUndefined();
    expect(CoreUserSchema.parse({ ...user, ...verification })).toMatchObject(
      verification,
    );
  });
});

describe('DotaProfileApiSchema Friend ID verification fields', () => {
  const profile = {
    id: 1,
    org_user_id: 2,
    rank_status: 'active',
    rank_medal: 'Legend 3',
    rank_date: null,
    battle_cup_tier: null,
    mmr: 3000,
    rank_screenshot: null,
    battlecup_screenshot: null,
    steam_account_id: 123,
    pos_1: true,
    pos_2: false,
    pos_3: false,
    pos_4: false,
    pos_5: false,
  };

  it('parses a payload without them', () => {
    expect(
      DotaProfileApiSchema.parse(profile).steam_account_verified,
    ).toBeUndefined();
  });

  it('parses all four when present', () => {
    const fields = {
      ...verification,
      steam_account_verified_org_name: null,
    };
    expect(DotaProfileApiSchema.parse({ ...profile, ...fields })).toMatchObject(
      fields,
    );
  });
});

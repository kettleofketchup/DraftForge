import { describe, expect, it } from 'vitest';

import { eventSignupSchema } from '~/components/events/schemas';

const userData = {
  pk: 3,
  username: 'player',
  nickname: null,
  avatar: null,
  discordId: null,
  discordNickname: null,
  positions: null,
  steam_account_id: 123,
  avatarUrl: null,
};

const row = {
  id: 1,
  event: 2,
  user: 3,
  username: 'player',
  user_avatar: null,
  user_data: userData,
  dota_profile: null,
  org_user_mmr: null,
  org_user_pk: null,
  organization: null,
  suggested_mmr: 3000,
  suggested_mmr_range: [2500, 3500],
  suggested_mmr_range_source: 'fallback',
  event_team: null,
  signup_type: 'player',
  status: 'rsvp',
  waitlist_position: null,
  created_at: '2026-11-01T10:00:00Z',
  updated_at: '2026-11-01T10:00:00Z',
};

describe('eventSignupSchema Friend ID verification fields', () => {
  it('parses a row without them', () => {
    const parsed = eventSignupSchema.parse(row);
    expect(parsed.can_verify_steam_account).toBeUndefined();
    expect(parsed.user_data?.steam_account_verified).toBeUndefined();
    expect(parsed.user_data?.steam_account_verified_org_name).toBeUndefined();
  });

  it('parses them on user_data and the row', () => {
    const verification = {
      steam_account_verified: true,
      steam_account_verified_at: '2026-11-22T10:00:00+00:00',
      steam_account_verified_org_name: 'Kettle League',
      steam_account_exists_checked: true,
    };
    const parsed = eventSignupSchema.parse({
      ...row,
      user_data: { ...userData, ...verification },
      can_verify_steam_account: true,
    });
    expect(parsed.user_data).toMatchObject(verification);
    expect(parsed.can_verify_steam_account).toBe(true);
  });

  it('accepts a null org name for viewers it is hidden from', () => {
    const parsed = eventSignupSchema.parse({
      ...row,
      user_data: {
        ...userData,
        steam_account_verified: false,
        steam_account_verified_at: null,
        steam_account_verified_org_name: null,
        steam_account_exists_checked: false,
      },
      can_verify_steam_account: false,
    });
    expect(parsed.user_data?.steam_account_verified_org_name).toBeNull();
  });
});

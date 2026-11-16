import { describe, expect, it } from 'vitest';

import {
  discordEventDMSchema,
  discordEventLogSchema,
  eventSignupSchema,
  eventStaffUserSchema,
} from '../schemas';

const names = {
  nickname: null,
  discordNickname: 'GwaihirTheWindlord',
  guildNickname: 'DragonClaw',
};

function withoutKeys<T extends Record<string, unknown>>(
  obj: T,
  keys: string[],
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(obj).filter(([k]) => !keys.includes(k)),
  );
}

const staff = {
  pk: 3,
  username: 'dc_handle',
  avatarUrl: null,
  ...names,
};

const userData = {
  pk: 3,
  username: 'dc_handle',
  avatar: null,
  discordId: '123',
  positions: null,
  steam_account_id: null,
  avatarUrl: null,
  ...names,
};

const signup = {
  id: 1,
  event: 2,
  user: 3,
  username: 'DragonClaw',
  user_avatar: null,
  user_data: userData,
  dota_profile: null,
  org_user_mmr: null,
  org_user_pk: null,
  organization: 7,
  suggested_mmr: 3000,
  suggested_mmr_range: [2500, 3500],
  suggested_mmr_range_source: 'fallback',
  event_team: null,
  signup_type: 'player',
  status: 'confirmed',
  waitlist_position: null,
  created_at: '2026-11-16T00:00:00Z',
  updated_at: '2026-11-16T00:00:00Z',
};

const log = {
  id: 1,
  category: 1,
  category_display: 'System',
  action: 'post',
  target_type: 'event',
  discord_user_id: '123',
  discord_username: 'dc_handle',
  username: 'dc_handle',
  avatar: null,
  message_id: null,
  status_code: null,
  error_message: '',
  success: true,
  created_at: '2026-11-16T00:00:00Z',
  ...names,
};

const dm = {
  id: 1,
  dm_type: 1,
  dm_type_display: 'Reminder',
  username: 'dc_handle',
  avatar: null,
  discord_user_id: '123',
  can_send: true,
  message_id: 'm',
  sent_at: null,
  delivered: false,
  responded: false,
  response_text: '',
  responded_at: null,
  created_at: '2026-11-16T00:00:00Z',
  ...names,
};

const NEW_KEYS = ['discordNickname', 'guildNickname'];

describe('eventStaffUserSchema names', () => {
  it('parses a PR 2 payload and keeps the Discord names', () => {
    const parsed = eventStaffUserSchema.parse(staff);
    expect(parsed.discordNickname).toBe('GwaihirTheWindlord');
    expect(parsed.guildNickname).toBe('DragonClaw');
  });

  it('parses a payload without the new keys', () => {
    expect(
      eventStaffUserSchema.safeParse(withoutKeys(staff, NEW_KEYS)).success,
    ).toBe(true);
  });

  it('parses a payload without nickname', () => {
    expect(
      eventStaffUserSchema.safeParse(withoutKeys(staff, ['nickname'])).success,
    ).toBe(true);
  });
});

describe('eventSignupSchema user_data names', () => {
  it('parses a PR 2 payload and keeps the Discord names', () => {
    const parsed = eventSignupSchema.parse(signup);
    expect(parsed.user_data?.discordNickname).toBe('GwaihirTheWindlord');
    expect(parsed.user_data?.guildNickname).toBe('DragonClaw');
  });

  it('parses user_data without the new keys', () => {
    const payload = { ...signup, user_data: withoutKeys(userData, NEW_KEYS) };
    expect(eventSignupSchema.safeParse(payload).success).toBe(true);
  });

  it('parses user_data without nickname', () => {
    const payload = {
      ...signup,
      user_data: withoutKeys(userData, ['nickname']),
    };
    expect(eventSignupSchema.safeParse(payload).success).toBe(true);
  });
});

describe('discordEventLogSchema names', () => {
  it('parses a PR 2 payload and keeps the Discord names', () => {
    const parsed = discordEventLogSchema.parse(log);
    expect(parsed.discordNickname).toBe('GwaihirTheWindlord');
    expect(parsed.guildNickname).toBe('DragonClaw');
  });

  it('parses a payload without the new keys', () => {
    expect(
      discordEventLogSchema.safeParse(withoutKeys(log, NEW_KEYS)).success,
    ).toBe(true);
  });

  it('parses a payload without nickname', () => {
    expect(
      discordEventLogSchema.safeParse(withoutKeys(log, ['nickname'])).success,
    ).toBe(true);
  });
});

describe('discordEventDMSchema names', () => {
  it('parses a PR 2 payload and keeps the Discord names', () => {
    const parsed = discordEventDMSchema.parse(dm);
    expect(parsed.discordNickname).toBe('GwaihirTheWindlord');
    expect(parsed.guildNickname).toBe('DragonClaw');
  });

  it('parses a payload without the new keys', () => {
    expect(
      discordEventDMSchema.safeParse(withoutKeys(dm, NEW_KEYS)).success,
    ).toBe(true);
  });

  it('parses a payload without nickname', () => {
    expect(
      discordEventDMSchema.safeParse(withoutKeys(dm, ['nickname'])).success,
    ).toBe(true);
  });
});

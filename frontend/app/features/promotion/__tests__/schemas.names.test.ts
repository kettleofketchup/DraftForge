import { describe, expect, it } from 'vitest';

import { CandidateRowSchema } from '../schemas';

const row = {
  user_pk: 3,
  username: 'dc_handle',
  discordUsername: 'dc_handle',
  discordId: '123',
  avatarUrl: null,
  recent_count: 0,
  last_messaged: null,
  earning_send_exists: false,
  signed_up: false,
  nickname: null,
  discordNickname: 'GwaihirTheWindlord',
  guildNickname: 'DragonClaw',
};

function without(keys: string[]): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(row).filter(([k]) => !keys.includes(k)),
  );
}

describe('CandidateRowSchema names', () => {
  it('parses a PR 2 payload and keeps the Discord names', () => {
    const parsed = CandidateRowSchema.parse(row);
    expect(parsed.discordNickname).toBe('GwaihirTheWindlord');
    expect(parsed.guildNickname).toBe('DragonClaw');
    expect('nickname' in parsed).toBe(false);
  });

  it('parses a payload without the new keys', () => {
    expect(
      CandidateRowSchema.safeParse(
        without(['discordNickname', 'guildNickname']),
      ).success,
    ).toBe(true);
  });

  it('parses a payload without nickname', () => {
    expect(CandidateRowSchema.safeParse(without(['nickname'])).success).toBe(
      true,
    );
  });
});

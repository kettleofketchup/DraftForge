import { describe, expect, it } from 'vitest';

import { LeaderboardRowSchema, MemberSummarySchema } from '../schemas';

const member = {
  org_user_pk: 10,
  user_pk: 3,
  username: 'dc_handle',
  avatarUrl: null,
  nickname: null,
  discordNickname: 'GwaihirTheWindlord',
  guildNickname: 'DragonClaw',
};

function without(keys: string[]): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(member).filter(([k]) => !keys.includes(k)),
  );
}

describe('MemberSummarySchema names', () => {
  it('parses a PR 2 payload and keeps the Discord names', () => {
    const parsed = MemberSummarySchema.parse(member);
    expect(parsed.discordNickname).toBe('GwaihirTheWindlord');
    expect(parsed.guildNickname).toBe('DragonClaw');
  });

  it('parses a payload without the new keys', () => {
    expect(
      MemberSummarySchema.safeParse(
        without(['discordNickname', 'guildNickname']),
      ).success,
    ).toBe(true);
  });

  it('parses a payload without nickname', () => {
    expect(MemberSummarySchema.safeParse(without(['nickname'])).success).toBe(
      true,
    );
  });

  it('leaderboard rows inherit the name keys', () => {
    const parsed = LeaderboardRowSchema.parse({
      ...without(['nickname']),
      points: 5,
      entries: 1,
    });
    expect(parsed.guildNickname).toBe('DragonClaw');
  });
});

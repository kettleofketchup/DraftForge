import { beforeEach, describe, expect, it } from 'vitest';

import { useUserCacheStore } from '~/store/userCacheStore';

import { DisplayName } from '../avatar';

const dragon = {
  pk: 1,
  username: 'dc_handle',
  discordNickname: 'GwaihirTheWindlord',
  orgNicknames: { 7: 'DragonClaw' },
};

beforeEach(() => {
  useUserCacheStore.getState().reset();
});

describe('DisplayName', () => {
  it('prefers the global Discord name over the username', () => {
    expect(DisplayName({ username: 'u', discordNickname: 'G' })).toBe('G');
  });

  it('uses the org server nickname when given an org', () => {
    expect(DisplayName(dragon, undefined, 7)).toBe('DragonClaw');
    expect(DisplayName(dragon, undefined, 8)).toBe('GwaihirTheWindlord');
    expect(DisplayName(dragon)).toBe('GwaihirTheWindlord');
  });

  it('ignores a stale site nickname', () => {
    expect(DisplayName({ username: 'u', nickname: 'MySite' })).toBe('u');
  });

  it('guards against raw pks and missing users', () => {
    expect(DisplayName(5 as never)).toBe('?');
    expect(DisplayName(undefined)).toBe('?');
  });

  it('falls back to User <pk> without a username', () => {
    expect(DisplayName({ pk: 4, username: null })).toBe('User 4');
  });

  it('truncates to maxLength', () => {
    expect(DisplayName(dragon, 5, 7)).toBe('Drago…');
  });

  it('keeps the guild member precedence', () => {
    const member = {
      nick: 'N',
      user: { username: 'u', global_name: 'G' },
    } as never;
    expect(DisplayName(member)).toBe('N');
    expect(
      DisplayName({
        nick: null,
        user: { username: 'u', global_name: 'G' },
      } as never),
    ).toBe('G');
    expect(
      DisplayName({
        nick: null,
        user: { username: 'u', global_name: null },
      } as never),
    ).toBe('u');
  });
});

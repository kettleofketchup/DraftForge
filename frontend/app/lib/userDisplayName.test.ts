import { beforeEach, describe, expect, it } from 'vitest';

import { useUserCacheStore } from '~/store/userCacheStore';

import {
  displayNameById,
  isDiscordMember,
  matchesUserQuery,
  orgRowDisplayName,
  orgRowNameSource,
  resolveDisplayName,
  truncateName,
  userNameCandidates,
} from './userDisplayName';

const dragon = {
  pk: 1,
  username: 'dc_handle',
  discordNickname: 'GwaihirTheWindlord',
  orgNicknames: { 7: 'DragonClaw' },
};

const seedDragon = () =>
  useUserCacheStore.getState().upsert(
    {
      pk: 1,
      username: 'dc_handle',
      discordNickname: 'GwaihirTheWindlord',
      guildNickname: 'DragonClaw',
    } as never,
    { orgId: 7 },
  );

beforeEach(() => {
  useUserCacheStore.getState().reset();
});

describe('resolveDisplayName', () => {
  it('uses the org server nickname in that org only', () => {
    expect(resolveDisplayName(dragon, { orgId: 7 })).toBe('DragonClaw');
    expect(resolveDisplayName(dragon, { orgId: 8 })).toBe('GwaihirTheWindlord');
    expect(resolveDisplayName(dragon)).toBe('GwaihirTheWindlord');
    expect(resolveDisplayName(dragon, { orgId: null })).toBe(
      'GwaihirTheWindlord',
    );
  });

  it('never shows a stale site nickname', () => {
    expect(resolveDisplayName({ ...dragon, nickname: 'MySite' } as never)).toBe(
      'GwaihirTheWindlord',
    );
    expect(
      resolveDisplayName({ pk: 2, username: 'u', nickname: 'MySite' } as never),
    ).toBe('u');
  });

  it('skips blank names and falls back to User <pk> or ?', () => {
    expect(resolveDisplayName({ ...dragon, discordNickname: ' ' })).toBe(
      'dc_handle',
    );
    expect(
      resolveDisplayName(
        { ...dragon, orgNicknames: { 7: '  ' } },
        { orgId: 7 },
      ),
    ).toBe('GwaihirTheWindlord');
    expect(
      resolveDisplayName({ pk: 5, username: null, discordNickname: '' }),
    ).toBe('User 5');
    expect(resolveDisplayName({ username: '', discordNickname: null })).toBe(
      '?',
    );
    expect(resolveDisplayName(null)).toBe('?');
    expect(resolveDisplayName(undefined)).toBe('?');
  });

  it('resolves a Discord guild member regardless of org', () => {
    const member = { nick: 'N', user: { username: 'U', global_name: 'G' } };
    expect(resolveDisplayName(member)).toBe('N');
    expect(resolveDisplayName(member, { orgId: 7 })).toBe('N');
    expect(resolveDisplayName({ ...member, nick: null })).toBe('G');
    expect(
      resolveDisplayName({
        nick: ' ',
        user: { username: 'U', global_name: null },
      }),
    ).toBe('U');
  });

  it('treats a numeric user FK as a user, not a guild member', () => {
    expect(resolveDisplayName({ pk: 1, user: 5, username: 'a' } as never)).toBe(
      'a',
    );
  });

  it('looks up the org nickname in the store for raw objects', () => {
    seedDragon();
    expect(
      resolveDisplayName({ pk: 1, username: 'dc_handle' }, { orgId: 7 }),
    ).toBe('DragonClaw');
    expect(resolveDisplayName({ pk: 1, username: 'dc_handle' })).toBe(
      'dc_handle',
    );
  });

  it('prefers an own orgNicknames key, including null, over the store', () => {
    seedDragon();
    expect(
      resolveDisplayName(
        { pk: 1, username: 'dc_handle', orgNicknames: { 7: null } },
        { orgId: 7 },
      ),
    ).toBe('dc_handle');
    expect(
      resolveDisplayName(
        { pk: 1, username: 'dc_handle', orgNicknames: {} },
        { orgId: 7 },
      ),
    ).toBe('DragonClaw');
  });

  it('ignores a flat guildNickname on a raw object', () => {
    expect(
      resolveDisplayName(
        { pk: 2, username: 'u', guildNickname: 'Flat' } as never,
        {
          orgId: 7,
        },
      ),
    ).toBe('u');
  });

  it('truncates with maxLength', () => {
    expect(resolveDisplayName(dragon, { orgId: 7, maxLength: 5 })).toBe(
      'Drago…',
    );
    expect(resolveDisplayName(dragon, { orgId: 7, maxLength: 20 })).toBe(
      'DragonClaw',
    );
  });
});

describe('orgRowNameSource', () => {
  it('maps a flat org row to a NameSource scoped to that org', () => {
    const row = {
      user_pk: 3,
      username: 'u',
      discordNickname: 'G',
      guildNickname: 'S',
    };
    expect(resolveDisplayName(orgRowNameSource(row, 7), { orgId: 7 })).toBe(
      'S',
    );
    expect(resolveDisplayName(orgRowNameSource(row, 7), { orgId: null })).toBe(
      'G',
    );
    expect(orgRowNameSource(row, 7).pk).toBe(3);
  });

  it('falls back to pk and carries no org nickname without an org', () => {
    const source = orgRowNameSource(
      { pk: 4, username: null, guildNickname: 'S' },
      null,
    );
    expect(source.pk).toBe(4);
    expect(source.orgNicknames).toEqual({});
    expect(resolveDisplayName(source)).toBe('User 4');
  });

  it('stores null when the row has no server nickname', () => {
    seedDragon();
    const source = orgRowNameSource({ user_pk: 1, username: 'dc_handle' }, 7);
    expect(source.orgNicknames).toEqual({ 7: null });
    expect(resolveDisplayName(source, { orgId: 7 })).toBe('dc_handle');
  });
});

describe('truncateName', () => {
  it('only truncates names longer than n', () => {
    expect(truncateName('Drag', 5)).toBe('Drag');
    expect(truncateName('DragonClaw', 5)).toBe('Drago…');
  });
});

describe('isDiscordMember', () => {
  it('requires a user object with a username', () => {
    expect(isDiscordMember({ nick: null, user: { username: 'U' } })).toBe(true);
    expect(isDiscordMember({ user: 5 })).toBe(false);
    expect(isDiscordMember({ user: null })).toBe(false);
    expect(isDiscordMember(null)).toBe(false);
  });
});

describe('displayNameById', () => {
  it('resolves cached users and falls back otherwise', () => {
    seedDragon();
    expect(displayNameById(1, 'payload', 7)).toBe('DragonClaw');
    expect(displayNameById(1, 'payload')).toBe('GwaihirTheWindlord');
    expect(displayNameById(99, 'payload')).toBe('payload');
    expect(displayNameById(99)).toBe('User 99');
    expect(displayNameById(null)).toBe('?');
    expect(displayNameById(undefined, 'payload')).toBe('payload');
  });
});

describe('userNameCandidates / matchesUserQuery', () => {
  it('lists every non-empty name, org nickname only in that org', () => {
    const user = { ...dragon, discordUsername: 'dragon_d' };
    expect(userNameCandidates(user, 7)).toEqual([
      'DragonClaw',
      'GwaihirTheWindlord',
      'dragon_d',
      'dc_handle',
    ]);
    expect(userNameCandidates(user)).toEqual([
      'GwaihirTheWindlord',
      'dragon_d',
      'dc_handle',
    ]);
    expect(userNameCandidates(user, 8)).toEqual([
      'GwaihirTheWindlord',
      'dragon_d',
      'dc_handle',
    ]);
  });

  it('never includes a stale site nickname', () => {
    expect(
      userNameCandidates({ pk: 2, username: 'u', nickname: 'MySite' } as never),
    ).toEqual(['u']);
    expect(
      matchesUserQuery(
        { pk: 2, username: 'u', nickname: 'MySite' } as never,
        'mysite',
      ),
    ).toBe(false);
  });

  it('lists guild member names', () => {
    expect(
      userNameCandidates({
        nick: 'N',
        user: { username: 'U', global_name: 'G' },
      }),
    ).toEqual(['N', 'G', 'U']);
  });

  it('matches case-insensitively without leaking org nicknames', () => {
    expect(matchesUserQuery(dragon, 'DC_HAND')).toBe(true);
    expect(matchesUserQuery(dragon, 'dragon', 7)).toBe(true);
    expect(matchesUserQuery(dragon, 'dragon')).toBe(false);
    expect(matchesUserQuery(dragon, 'dragon', 8)).toBe(false);
    expect(matchesUserQuery(dragon, 'gwaihir')).toBe(true);
  });

  it('uses the store org nickname for raw objects', () => {
    seedDragon();
    expect(
      matchesUserQuery({ pk: 1, username: 'dc_handle' }, 'dragon', 7),
    ).toBe(true);
  });
});

describe('orgRowDisplayName', () => {
  const row = {
    user_pk: 3,
    username: 'u',
    discordNickname: 'G',
    guildNickname: 'Server',
  };

  it('resolves an org row for its org and truncates', () => {
    expect(orgRowDisplayName(row, 7)).toBe('Server');
    expect(orgRowDisplayName(row, null)).toBe('G');
    expect(orgRowDisplayName(row, 7, 3)).toBe('Ser…');
  });
});

// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { useUserCacheStore } from '~/store/userCacheStore';

import {
  filterUsers,
  findUserByName,
  userMatchesQuery,
  userSearchNames,
} from './userSearch';

beforeEach(() => useUserCacheStore.getState().reset());
afterEach(() => window.history.pushState({}, '', '/'));

describe('userMatchesQuery', () => {
  it('matches the Discord name shown instead of the username', () => {
    const user = {
      pk: 9,
      username: '5c0obysn4cks',
      discordNickname: 'Wanna see nirvana',
    };
    expect(userMatchesQuery(user, 'NIR')).toBe(true);
    expect(userMatchesQuery(user, '5c0')).toBe(true);
    expect(userMatchesQuery(user, 'zzz')).toBe(false);
  });

  it('matches the org server nickname in an org', () => {
    const user = { pk: 9, username: 'u', guildNickname: 'ServerName' };
    expect(userMatchesQuery(user, 'server', { orgId: 3 })).toBe(true);
  });

  it('takes the org from the page', () => {
    useUserCacheStore.getState().upsert(
      { pk: 4, username: 'plain', guildNickname: 'OrgNick' },
      {
        orgId: 2,
      },
    );
    expect(userMatchesQuery({ pk: 4 }, 'orgnick')).toBe(false);
    window.history.pushState({}, '', '/organizations/2');
    expect(userMatchesQuery({ pk: 4 }, 'orgnick')).toBe(true);
  });

  it('matches names known only to the user cache', () => {
    useUserCacheStore
      .getState()
      .upsert({ pk: 5, username: 'c', discordNickname: 'CachedGlobal' });
    expect(userMatchesQuery({ pk: 5 }, 'cachedglo')).toBe(true);
  });

  it('matches every name of a Discord guild member', () => {
    const member = {
      nick: 'ServerNick',
      user: { username: 'handle', global_name: 'Global' },
    };
    expect(userSearchNames(member)).toEqual(['ServerNick', 'Global', 'handle']);
    expect(userMatchesQuery(member, 'glob')).toBe(true);
    expect(userMatchesQuery(member, 'nope')).toBe(false);
  });

  it('treats a blank query as a match', () => {
    expect(userMatchesQuery({ username: 'u' }, '  ')).toBe(true);
  });
});

describe('filterUsers', () => {
  const users = [
    { pk: 1, username: 'alpha', discordNickname: 'Shared' },
    { pk: 2, username: 'beta', discordNickname: 'Shared' },
    { pk: 3, username: 'gamma' },
  ];

  it('drops excluded pks and predicate matches', () => {
    expect(filterUsers(users, 'shared', { excludePks: [1] })).toEqual([
      users[1],
    ]);
    expect(
      filterUsers(users, '', { exclude: (u) => u.username === 'gamma' }),
    ).toEqual([users[0], users[1]]);
  });

  it('returns an empty list for missing input', () => {
    expect(filterUsers(undefined, 'a')).toEqual([]);
  });
});

describe('findUserByName', () => {
  it('finds by any name, exactly and case-insensitively', () => {
    const users = [
      { pk: 1, username: 'alpha' },
      { pk: 2, username: 'beta', discordNickname: 'Wanna see nirvana' },
    ];
    expect(findUserByName(users, 'wanna see NIRVANA')).toBe(users[1]);
    expect(findUserByName(users, 'ALPHA')).toBe(users[0]);
    expect(findUserByName(users, 'nirvana')).toBeUndefined();
    expect(findUserByName(users, ' ')).toBeUndefined();
  });
});

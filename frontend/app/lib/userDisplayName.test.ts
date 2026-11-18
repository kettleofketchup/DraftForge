import { beforeEach, describe, expect, it } from 'vitest';

import { useUserCacheStore } from '~/store/userCacheStore';

import {
  mergeCachedUser,
  resolveDisplayName,
  userRefPk,
} from './userDisplayName';

const upsert = (raw: Record<string, unknown>, orgId?: number) =>
  useUserCacheStore
    .getState()
    .upsert(raw as never, orgId ? { orgId } : undefined);

describe('userRefPk', () => {
  it('reads pk, then user_id, then a numeric user', () => {
    expect(userRefPk({ pk: 1, user_id: 2, user: 3 })).toBe(1);
    expect(userRefPk({ user_id: 2, user: 3 })).toBe(2);
    expect(userRefPk({ user: 3 })).toBe(3);
  });

  it('reads id only from objects that look like users', () => {
    expect(userRefPk({ id: 4, username: 'u' })).toBe(4);
    expect(userRefPk({ id: 4, discordNickname: 'G' })).toBe(4);
    expect(userRefPk({ id: 4, avatar: 'hash' })).toBe(4);
    expect(userRefPk({ id: 4, name: 'Team' })).toBeUndefined();
  });

  it('ignores Discord members, nested user objects and junk', () => {
    expect(
      userRefPk({ nick: 'n', user: { id: '9', username: 'd' } }),
    ).toBeUndefined();
    expect(userRefPk(null)).toBeUndefined();
    expect(userRefPk(5)).toBeUndefined();
    expect(userRefPk({ pk: null, user_id: 6 })).toBe(6);
  });
});

describe('resolveDisplayName', () => {
  beforeEach(() => useUserCacheStore.getState().reset());

  it('outside an org: global name, then username', () => {
    expect(
      resolveDisplayName({ username: 'u', discordNickname: 'Global' }),
    ).toBe('Global');
    expect(resolveDisplayName({ username: 'u', discordNickname: '' })).toBe(
      'u',
    );
    expect(resolveDisplayName({ username: 'u', guildNickname: 'Server' })).toBe(
      'u',
    );
  });

  it('keeps the site nickname above Discord names until its removal', () => {
    expect(
      resolveDisplayName({
        username: 'u',
        nickname: 'Site',
        discordNickname: 'Global',
      }),
    ).toBe('Site');
    expect(
      resolveDisplayName(
        { username: 'u', nickname: 'Site', guildNickname: 'Server' },
        { orgId: 7 },
      ),
    ).toBe('Server');
    useUserCacheStore
      .getState()
      .upsert({ pk: 5, username: 'c', nickname: 'Cached' });
    expect(resolveDisplayName({ pk: 5 })).toBe('Cached');
  });

  it('in an org: server nickname, then global name, then username', () => {
    const user = {
      pk: 1,
      username: 'u',
      discordNickname: 'Global',
      guildNickname: 'Server',
    };
    expect(resolveDisplayName(user, { orgId: 7 })).toBe('Server');
    expect(
      resolveDisplayName({ ...user, guildNickname: null }, { orgId: 7 }),
    ).toBe('Global');
    expect(resolveDisplayName({ username: 'u' }, { orgId: 7 })).toBe('u');
  });

  it('falls back to User <pk> or ?', () => {
    expect(resolveDisplayName({ pk: 12 })).toBe('User 12');
    expect(resolveDisplayName({ user_id: 13, username: null })).toBe('User 13');
    expect(resolveDisplayName({})).toBe('?');
    expect(resolveDisplayName(undefined)).toBe('?');
  });

  it('resolves Discord guild members: nick, global_name, username', () => {
    expect(
      resolveDisplayName({
        nick: 'N',
        user: { username: 'd', global_name: 'G' },
      }),
    ).toBe('N');
    expect(
      resolveDisplayName({
        nick: null,
        user: { username: 'd', global_name: 'G' },
      }),
    ).toBe('G');
    expect(resolveDisplayName({ user: { username: 'd' } })).toBe('d');
  });

  it('truncates to maxLength', () => {
    expect(resolveDisplayName({ username: 'abcdef' }, { maxLength: 3 })).toBe(
      'abc…',
    );
  });

  it('fills missing names from the cache entry', () => {
    upsert({ pk: 1, username: 'cached', discordNickname: 'CachedGlobal' });
    expect(resolveDisplayName({ user_id: 1 })).toBe('CachedGlobal');
    expect(resolveDisplayName({ pk: 1, username: 'payload' })).toBe(
      'CachedGlobal',
    );
  });

  it('prefers payload names over the cache entry', () => {
    upsert({ pk: 1, username: 'cached', discordNickname: 'CachedGlobal' });
    expect(resolveDisplayName({ pk: 1, discordNickname: 'Fresh' })).toBe(
      'Fresh',
    );
  });

  it('uses the cached server nickname for the display org only', () => {
    upsert({ pk: 1, username: 'u', guildNickname: 'InSeven' }, 7);
    expect(resolveDisplayName({ pk: 1 }, { orgId: 7 })).toBe('InSeven');
    expect(resolveDisplayName({ pk: 1 }, { orgId: 8 })).toBe('u');
    expect(resolveDisplayName({ pk: 1 })).toBe('u');
  });

  it('payload server nickname beats the cache; explicit null hides it', () => {
    upsert(
      { pk: 1, username: 'u', discordNickname: 'G', guildNickname: 'Cached' },
      7,
    );
    expect(
      resolveDisplayName({ pk: 1, guildNickname: 'Fresh' }, { orgId: 7 }),
    ).toBe('Fresh');
    expect(
      resolveDisplayName({ pk: 1, guildNickname: null }, { orgId: 7 }),
    ).toBe('G');
    expect(
      resolveDisplayName({ pk: 1, orgNicknames: { 7: 'Own' } }, { orgId: 7 }),
    ).toBe('Own');
  });
});

describe('mergeCachedUser', () => {
  beforeEach(() => useUserCacheStore.getState().reset());

  it('returns the payload unchanged when nothing is cached', () => {
    const payload = { user_id: 3, avatar: 'h' };
    expect(mergeCachedUser(payload, undefined)).toBe(payload);
  });

  it('fills avatar fields the payload lacks', () => {
    upsert({ pk: 3, username: 'u', discordId: '42', avatar: 'old' });
    const merged = mergeCachedUser(
      { user_id: 3, avatar: 'new' },
      useUserCacheStore.getState().entities[3],
    );
    expect(merged).toMatchObject({
      pk: 3,
      discordId: '42',
      avatar: 'new',
      username: 'u',
    });
  });
});

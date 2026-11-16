import { beforeEach, describe, expect, it } from 'vitest';

import { CoreUserSchema } from '~/components/user/schemas';

import { useUserCacheStore } from './userCacheStore';

const user = () =>
  ({
    pk: 5,
    username: 'x',
    positions: {
      carry: 5,
      mid: 0,
      offlane: 0,
      soft_support: 0,
      hard_support: 0,
    },
    admin_organization_ids: [1, 2],
  }) as never;

describe('userCacheStore.upsert', () => {
  beforeEach(() => {
    useUserCacheStore.getState().reset();
  });

  it('keeps the same entities when an equal user arrives as fresh objects', () => {
    useUserCacheStore.getState().upsert(user());
    const before = useUserCacheStore.getState().entities;
    useUserCacheStore.getState().upsert(user());
    expect(useUserCacheStore.getState().entities).toBe(before);
  });

  it('stores a nested change', () => {
    useUserCacheStore.getState().upsert(user());
    useUserCacheStore.getState().upsert({
      ...(user() as object),
      positions: {
        carry: 1,
        mid: 0,
        offlane: 0,
        soft_support: 0,
        hard_support: 0,
      },
    } as never);
    expect(useUserCacheStore.getState().entities[5].positions?.carry).toBe(1);
  });
});

describe('userCacheStore.dropScoped', () => {
  beforeEach(() => {
    useUserCacheStore.getState().reset();
  });

  it('drops only the named org slot', () => {
    const store = useUserCacheStore.getState();
    store.upsert({ pk: 5, username: 'x', mmr: 4000, orgUserPk: 11 } as never, {
      orgId: 1,
    });
    store.upsert({ pk: 5, username: 'x', mmr: 3000, orgUserPk: 12 } as never, {
      orgId: 2,
    });
    useUserCacheStore.getState().dropScoped({ orgId: 1 });
    const entry = useUserCacheStore.getState().entities[5];
    expect(entry.orgData[1]).toBeUndefined();
    expect(entry.orgData[2]?.mmr).toBe(3000);
  });

  it('leaves entities untouched when nothing is cached for the scope', () => {
    useUserCacheStore.getState().upsert(user());
    const before = useUserCacheStore.getState().entities;
    useUserCacheStore.getState().dropScoped({ leagueId: 9 });
    expect(useUserCacheStore.getState().entities).toBe(before);
  });
});

describe('userCacheStore orgNicknames', () => {
  beforeEach(() => {
    useUserCacheStore.getState().reset();
  });

  const entry = (pk = 1) => useUserCacheStore.getState().entities[pk];

  it('stores a server nickname under the upsert org without touching orgData', () => {
    useUserCacheStore
      .getState()
      .upsert({ pk: 1, username: 'u', guildNickname: 'DragonClaw' } as never, {
        orgId: 7,
      });
    expect(entry().orgNicknames).toEqual({ 7: 'DragonClaw' });
    expect(entry().orgData[7]).toBeUndefined();
    expect(
      (entry() as unknown as Record<string, unknown>).guildNickname,
    ).toBeUndefined();
  });

  it('starts with an empty map when no org context is given', () => {
    useUserCacheStore.getState().upsert({ pk: 1, username: 'u' } as never);
    expect(entry().orgNicknames).toEqual({});
  });

  it('merges nicknames from a second org', () => {
    const store = useUserCacheStore.getState();
    store.upsert(
      { pk: 1, username: 'u', guildNickname: 'DragonClaw' } as never,
      { orgId: 7 },
    );
    store.upsert({ pk: 1, username: 'u', guildNickname: 'Gwai' } as never, {
      orgId: 8,
    });
    expect(entry().orgNicknames).toEqual({ 7: 'DragonClaw', 8: 'Gwai' });
  });

  it('applies a nickname-only change', () => {
    const store = useUserCacheStore.getState();
    store.upsert({ pk: 1, username: 'u', guildNickname: 'Old' } as never, {
      orgId: 7,
    });
    store.upsert({ pk: 1, username: 'u', guildNickname: 'New' } as never, {
      orgId: 7,
    });
    expect(entry().orgNicknames[7]).toBe('New');
  });

  it('ignores a flat guildNickname without an org context', () => {
    useUserCacheStore
      .getState()
      .upsert({ pk: 1, username: 'u', guildNickname: 'DragonClaw' } as never);
    expect(entry().orgNicknames).toEqual({});
    expect(
      (entry() as unknown as Record<string, unknown>).guildNickname,
    ).toBeUndefined();
  });

  it('keeps the nickname on an own undefined and clears it on explicit null', () => {
    const store = useUserCacheStore.getState();
    store.upsert(
      { pk: 1, username: 'u', guildNickname: 'DragonClaw' } as never,
      { orgId: 7 },
    );
    store.upsert({ pk: 1, username: 'u', guildNickname: undefined } as never, {
      orgId: 7,
    });
    expect(entry().orgNicknames[7]).toBe('DragonClaw');
    store.upsert({ pk: 1, username: 'u', guildNickname: null } as never, {
      orgId: 7,
    });
    expect(entry().orgNicknames).toEqual({ 7: null });
  });

  it('dropScoped deletes only the named org nickname', () => {
    const store = useUserCacheStore.getState();
    store.upsert({ pk: 1, username: 'u', guildNickname: 'A' } as never, {
      orgId: 7,
    });
    store.upsert({ pk: 1, username: 'u', guildNickname: 'B' } as never, {
      orgId: 8,
    });
    useUserCacheStore.getState().dropScoped({ orgId: 7 });
    expect(entry().orgNicknames).toEqual({ 8: 'B' });
  });

  it('a nickname-only write does not make org MMR look fresh', () => {
    useUserCacheStore
      .getState()
      .upsert({ pk: 1, username: 'u', guildNickname: 'DragonClaw' } as never, {
        orgId: 7,
      });
    expect(useUserCacheStore.getState().isStale(1, { orgId: 7 })).toBe(true);
    expect(useUserCacheStore.getState().isStale(1)).toBe(false);
  });

  it('accepts one-character Discord names', () => {
    expect(
      CoreUserSchema.safeParse({ pk: 1, username: 'uu', discordNickname: 'G' })
        .success,
    ).toBe(true);
    expect('guildNickname' in CoreUserSchema.shape).toBe(false);
  });
});

import { beforeEach, describe, expect, it } from 'vitest';

import { useUserCacheStore } from './userCacheStore';

const user = () =>
  ({
    pk: 5,
    username: 'x',
    positions: { carry: 5, mid: 0, offlane: 0, soft_support: 0, hard_support: 0 },
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
      positions: { carry: 1, mid: 0, offlane: 0, soft_support: 0, hard_support: 0 },
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
    store.upsert({ pk: 5, username: 'x', mmr: 4000, orgUserPk: 11 } as never, { orgId: 1 });
    store.upsert({ pk: 5, username: 'x', mmr: 3000, orgUserPk: 12 } as never, { orgId: 2 });
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

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

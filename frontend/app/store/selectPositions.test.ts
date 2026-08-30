import { beforeEach, describe, expect, it } from 'vitest';

import { GAME_TYPE } from '~/components/game/constants';

import { selectPositions } from './selectPositions';
import { useUserCacheStore } from './userCacheStore';

describe('selectPositions', () => {
  beforeEach(() => {
    useUserCacheStore.getState().reset();
  });

  it('reads positions off the list-populated userCacheStore for the dota id', () => {
    useUserCacheStore.getState().upsert({
      pk: 5,
      username: 'x',
      positions: { carry: 5, mid: 0, offlane: 0, soft_support: 0, hard_support: 0 },
    } as never);
    const pos = selectPositions(useUserCacheStore.getState(), 5, GAME_TYPE.DOTA2);
    expect(pos?.carry).toBe(5);
  });

  it('returns undefined for null gameType', () => {
    expect(selectPositions(useUserCacheStore.getState(), 5, null)).toBeUndefined();
  });

  it('returns undefined for non-dota gameType', () => {
    useUserCacheStore.getState().upsert({
      pk: 7,
      username: 'y',
      positions: { carry: 3, mid: 0, offlane: 0, soft_support: 0, hard_support: 0 },
    } as never);
    expect(
      selectPositions(useUserCacheStore.getState(), 7, GAME_TYPE.DEADLOCK),
    ).toBeUndefined();
  });

  it('returns undefined for an unknown user pk', () => {
    expect(
      selectPositions(useUserCacheStore.getState(), 999, GAME_TYPE.DOTA2),
    ).toBeUndefined();
  });
});

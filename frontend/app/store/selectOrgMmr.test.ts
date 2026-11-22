// @vitest-environment jsdom
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { GAME_TYPE } from '~/components/game/constants';

import { selectOrgMmr, useOrgMmr } from './selectOrgMmr';
import { useUserCacheStore } from './userCacheStore';
import type { UserEntry } from './userCacheTypes';

const entry = {
  pk: 5,
  username: 'x',
  orgData: { 7: { id: 11, mmrs: { 1: 4000, 2: 2500 }, _fetchedAt: 0 } },
  leagueData: {},
  _fetchedAt: 0,
} as UserEntry;

describe('selectOrgMmr', () => {
  it('returns the value for the requested game', () => {
    expect(selectOrgMmr(entry, 7, GAME_TYPE.DOTA2)).toBe(4000);
    expect(selectOrgMmr(entry, 7, GAME_TYPE.DEADLOCK)).toBe(2500);
  });

  it('returns undefined for an unknown org, no org or no entry', () => {
    expect(selectOrgMmr(entry, 8, GAME_TYPE.DOTA2)).toBeUndefined();
    expect(selectOrgMmr(entry, undefined, GAME_TYPE.DOTA2)).toBeUndefined();
    expect(selectOrgMmr(undefined, 7, GAME_TYPE.DOTA2)).toBeUndefined();
  });
});

describe('useOrgMmr', () => {
  beforeEach(() => useUserCacheStore.getState().reset());

  it('reads the cached per-game value', () => {
    useUserCacheStore.getState().upsert(
      {
        pk: 5,
        username: 'x',
        orgUserPk: 11,
        game_mmrs: { '1': 4000, '2': 2500 },
      } as never,
      { orgId: 7 },
    );
    const { result } = renderHook(() => useOrgMmr(5, 7, GAME_TYPE.DEADLOCK));
    expect(result.current).toBe(2500);
  });
});

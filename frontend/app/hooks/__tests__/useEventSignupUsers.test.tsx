// @vitest-environment jsdom
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import type { EventSignupType } from '~/components/events/schemas';
import { GAME_TYPE } from '~/components/game/constants';
import { useUserCacheStore } from '~/store/userCacheStore';

import { useEventSignupUsers } from '../useEvent';

const signup = (extra: Record<string, unknown>) =>
  ({
    user_data: { pk: 5, username: 'x' },
    org_user_pk: 11,
    org_user_mmr: 2500,
    ...extra,
  }) as unknown as EventSignupType;

describe('useEventSignupUsers', () => {
  beforeEach(() => {
    useUserCacheStore.getState().reset();
    useUserCacheStore.getState().upsert(
      {
        pk: 5,
        username: 'x',
        orgUserPk: 11,
        game_mmrs: { '1': 4000 },
      } as never,
      { orgId: 7 },
    );
  });

  it('files a Deadlock signup MMR under Deadlock and keeps Dota', () => {
    renderHook(() => useEventSignupUsers([signup({})], 7, GAME_TYPE.DEADLOCK));
    const mmrs = useUserCacheStore.getState().entities[5].orgData[7].mmrs;
    expect(mmrs).toEqual({ 1: 4000, 2: 2500 });
  });

  it('uses org_user_game_mmrs when present', () => {
    renderHook(() =>
      useEventSignupUsers(
        [signup({ org_user_game_mmrs: { '1': 4100, '2': 2500 } })],
        7,
        GAME_TYPE.DEADLOCK,
      ),
    );
    const mmrs = useUserCacheStore.getState().entities[5].orgData[7].mmrs;
    expect(mmrs).toEqual({ 1: 4100, 2: 2500 });
  });
});

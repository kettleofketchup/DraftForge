// @vitest-environment jsdom
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('~/components/api/api', () => ({}));

const { useEventSignupUsers } = await import('~/hooks/useEvent');
const { useUserCacheStore } = await import('~/store/userCacheStore');

const signup = {
  user_data: {
    pk: 1,
    username: 'dc_handle',
    discordNickname: 'GwaihirTheWindlord',
    guildNickname: 'DragonClaw',
  },
  org_user_pk: 40,
  org_user_mmr: 4000,
} as never;

beforeEach(() => useUserCacheStore.getState().reset());

describe('useEventSignupUsers name ingest', () => {
  it('stores the signup server nickname under the event org', () => {
    renderHook(() => useEventSignupUsers([signup], 7));
    expect(useUserCacheStore.getState().getById(1)?.orgNicknames).toEqual({
      7: 'DragonClaw',
    });
  });

  it('stores no server nickname without an event org', () => {
    renderHook(() => useEventSignupUsers([signup]));
    expect(useUserCacheStore.getState().getById(1)?.orgNicknames).toEqual({});
  });
});

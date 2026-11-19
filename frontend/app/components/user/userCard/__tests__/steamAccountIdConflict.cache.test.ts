// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { useUserCacheStore } from '~/store/userCacheStore';

import { describeSteamAccountIdConflict } from '../steamAccountIdConflict';

const SUFFIX = 'Saving will fail until it is freed from that account.';
const holder = { pk: 275, nickname: '', username: 'geo.potter' };

const goTo = (path: string) => window.history.pushState({}, '', path);

beforeEach(() => useUserCacheStore.getState().reset());
afterEach(() => goTo('/'));

describe('describeSteamAccountIdConflict with the user cache', () => {
  it('names the holder by their cached Discord name', () => {
    useUserCacheStore.getState().upsert([
      {
        pk: 275,
        username: 'geo.potter',
        discordNickname: 'Georgie',
      } as never,
    ]);
    expect(describeSteamAccountIdConflict(holder, 314)).toBe(
      `Already used by Georgie (@geo.potter). ${SUFFIX}`,
    );
  });

  it('names the holder by their server nickname on an org page', () => {
    useUserCacheStore
      .getState()
      .upsert(
        [{ pk: 275, username: 'geo.potter', guildNickname: 'GP' } as never],
        { orgId: 4 },
      );
    goTo('/organizations/4');
    expect(describeSteamAccountIdConflict(holder, 314)).toBe(
      `Already used by GP (@geo.potter). ${SUFFIX}`,
    );
  });
});

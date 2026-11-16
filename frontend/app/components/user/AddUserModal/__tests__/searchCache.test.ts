import { beforeEach, describe, expect, it } from 'vitest';
import { cacheSearchResults } from '~/components/user/AddUserModal/searchCache';
import { useUserCacheStore } from '~/store/userCacheStore';

const results = [
  {
    pk: 1,
    username: 'dc_handle',
    discordNickname: 'GwaihirTheWindlord',
    guildNickname: 'DragonClaw',
  },
  { pk: 2, username: 'outsider', discordNickname: null, guildNickname: null },
] as never[];

beforeEach(() => useUserCacheStore.getState().reset());

describe('cacheSearchResults', () => {
  it('upserts org-scoped search results under the org and returns them unchanged', () => {
    expect(cacheSearchResults(results, { orgId: 7, leagueId: 10 })).toBe(
      results,
    );
    expect(useUserCacheStore.getState().getById(1)?.orgNicknames).toEqual({
      7: 'DragonClaw',
    });
    expect(useUserCacheStore.getState().getById(2)?.orgNicknames).toEqual({
      7: null,
    });
  });

  it('stores no server nickname for an unscoped search', () => {
    cacheSearchResults(results, {});
    expect(useUserCacheStore.getState().getById(1)?.orgNicknames).toEqual({});
  });
});

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getLeagueUsers } = vi.hoisted(() => ({ getLeagueUsers: vi.fn() }));
vi.mock('~/components/api/api', () => ({
  getLeagueUsers,
  fetchLeague: vi.fn(),
}));

const { useLeagueStore } = await import('~/store/leagueStore');
const { useUserCacheStore } = await import('~/store/userCacheStore');

const leagueUser = {
  pk: 1,
  username: 'player',
  guildNickname: 'ServerNick',
  orgUserPk: 900,
  mmr: 4000,
};

beforeEach(() => {
  useLeagueStore.getState().reset();
  useUserCacheStore.getState().reset();
  getLeagueUsers.mockReset();
  getLeagueUsers.mockResolvedValue([leagueUser]);
});

describe('getLeagueUsers org scoping', () => {
  it('applies a new org id to already loaded league users', async () => {
    await useLeagueStore.getState().getLeagueUsers(10);
    await useLeagueStore.getState().getLeagueUsers(10, 7);

    const entry = useUserCacheStore.getState().getById(1);
    expect(entry?.orgNicknames).toEqual({ 7: 'ServerNick' });
    expect(entry?.orgData[7]).toBeDefined();
  });

  it('applies a second org id to already loaded league users', async () => {
    await useLeagueStore.getState().getLeagueUsers(10, 7);
    await useLeagueStore.getState().getLeagueUsers(10, 8);

    const entry = useUserCacheStore.getState().getById(1);
    expect(entry?.orgNicknames).toEqual({ 7: 'ServerNick', 8: 'ServerNick' });
    expect(entry?.orgData[8]).toBeDefined();
  });

  it('applies an org id passed while the league fetch is in flight', async () => {
    const first = useLeagueStore.getState().getLeagueUsers(10);
    const second = useLeagueStore.getState().getLeagueUsers(10, 7);
    await Promise.all([first, second]);

    expect(getLeagueUsers).toHaveBeenCalledTimes(1);
    expect(useUserCacheStore.getState().getById(1)?.orgNicknames).toEqual({
      7: 'ServerNick',
    });
  });

  it('fetches once for the same league and org', async () => {
    await useLeagueStore.getState().getLeagueUsers(10, 7);
    await useLeagueStore.getState().getLeagueUsers(10, 7);
    await useLeagueStore.getState().getLeagueUsers(10, 8);

    expect(getLeagueUsers).toHaveBeenCalledTimes(1);
  });

  it('does not apply a previous league response to a new league', async () => {
    await useLeagueStore.getState().getLeagueUsers(10);
    getLeagueUsers.mockResolvedValue([{ ...leagueUser, pk: 2 }]);
    await useLeagueStore.getState().getLeagueUsers(11, 7);

    expect(getLeagueUsers).toHaveBeenCalledTimes(2);
    expect(useUserCacheStore.getState().getById(1)?.orgNicknames).toEqual({});
    expect(useUserCacheStore.getState().getById(2)?.orgNicknames).toEqual({
      7: 'ServerNick',
    });
  });
});

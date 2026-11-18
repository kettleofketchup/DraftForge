import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getLeagueUsers } = vi.hoisted(() => ({ getLeagueUsers: vi.fn() }));
vi.mock('~/components/api/api', () => ({
  getLeagueUsers,
  fetchLeague: vi.fn(),
}));

const { useLeagueStore } = await import('~/store/leagueStore');
const { useUserCacheStore } = await import('~/store/userCacheStore');

beforeEach(() => {
  useLeagueStore.getState().reset();
  useUserCacheStore.getState().reset();
  getLeagueUsers.mockResolvedValue([
    {
      id: 50,
      pk: 1,
      username: 'dc_handle',
      discordNickname: 'GwaihirTheWindlord',
      guildNickname: 'DragonClaw',
      mmr: 4000,
    },
  ]);
});

describe('league users name ingest', () => {
  it('upserts league users under the league org so server nicknames are kept', async () => {
    await useLeagueStore.getState().getLeagueUsers(10, 7);
    const entry = useUserCacheStore.getState().getById(1);
    expect(entry?.orgNicknames).toEqual({ 7: 'DragonClaw' });
    expect(entry?.discordNickname).toBe('GwaihirTheWindlord');
  });

  it('stores no server nickname without a league org', async () => {
    await useLeagueStore.getState().getLeagueUsers(10);
    expect(useUserCacheStore.getState().getById(1)?.orgNicknames).toEqual({});
  });
});

import { beforeEach, describe, expect, it } from 'vitest';
import { useUserCacheStore } from '~/store/userCacheStore';
import { playerName, sampleContext } from '../render';

const event = {
  id: 42,
  name: 'Friday Inhouse',
  scheduled_at: '2026-11-15T01:00:00Z',
  signups_open_at: null,
};

beforeEach(() => useUserCacheStore.getState().reset());

describe('playerName', () => {
  const row = { username: 'u', discordNickname: 'G', guildNickname: 'S' };

  it('uses the server nickname for the org, like the backend player_name', () => {
    expect(playerName(row, 7)).toBe('S');
  });

  it('falls back to the global Discord name, then the username', () => {
    expect(playerName({ ...row, guildNickname: null }, 7)).toBe('G');
    expect(
      playerName(
        { username: 'u', discordNickname: null, guildNickname: null },
        7,
      ),
    ).toBe('u');
  });

  it('ignores a server nickname without an org', () => {
    expect(playerName(row)).toBe('G');
  });

  it('ignores a stale site nickname', () => {
    expect(playerName({ username: 'u', nickname: 'Site' } as never, 7)).toBe(
      'u',
    );
  });

  it("reads the sender's cached server nickname by pk", () => {
    useUserCacheStore
      .getState()
      .upsert([{ pk: 4, username: 'bob', guildNickname: 'Bobster' } as never], {
        orgId: 7,
      });
    expect(
      playerName({ pk: 4, username: 'bob', discordNickname: 'Bobby' }, 7),
    ).toBe('Bobster');
  });
});

describe('sampleContext promoter', () => {
  it('uses the sender server nickname for the sample org', () => {
    const ctx = sampleContext(
      event,
      { pk: 7, name: 'Kettle Club' },
      { username: 'bob', discordNickname: 'Bobby', guildNickname: 'S' },
      'https://x',
    );
    expect(ctx.promoter).toBe('S');
  });

  it('keeps the global name when the org has no pk', () => {
    const ctx = sampleContext(
      event,
      { name: 'Kettle Club' },
      { username: 'bob', discordNickname: 'Bobby', guildNickname: 'S' },
      'https://x',
    );
    expect(ctx.promoter).toBe('Bobby');
  });
});

import { beforeEach, describe, expect, it } from 'vitest';

import { useUserCacheStore } from './userCacheStore';

const user = () =>
  ({
    pk: 5,
    username: 'x',
    positions: {
      carry: 5,
      mid: 0,
      offlane: 0,
      soft_support: 0,
      hard_support: 0,
    },
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
      positions: {
        carry: 1,
        mid: 0,
        offlane: 0,
        soft_support: 0,
        hard_support: 0,
      },
    } as never);
    expect(useUserCacheStore.getState().entities[5].positions?.carry).toBe(1);
  });
});

describe('userCacheStore.dropScoped', () => {
  beforeEach(() => {
    useUserCacheStore.getState().reset();
  });

  it('drops only the named org slot', () => {
    const store = useUserCacheStore.getState();
    store.upsert({ pk: 5, username: 'x', mmr: 4000, orgUserPk: 11 } as never, {
      orgId: 1,
    });
    store.upsert({ pk: 5, username: 'x', mmr: 3000, orgUserPk: 12 } as never, {
      orgId: 2,
    });
    useUserCacheStore.getState().dropScoped({ orgId: 1 });
    const entry = useUserCacheStore.getState().entities[5];
    expect(entry.orgData[1]).toBeUndefined();
    expect(entry.orgData[2]?.mmrs).toEqual({ 1: 3000 });
  });

  it('leaves entities untouched when nothing is cached for the scope', () => {
    useUserCacheStore.getState().upsert(user());
    const before = useUserCacheStore.getState().entities;
    useUserCacheStore.getState().dropScoped({ leagueId: 9 });
    expect(useUserCacheStore.getState().entities).toBe(before);
  });
});

describe('userCacheStore orgNicknames', () => {
  beforeEach(() => {
    useUserCacheStore.getState().reset();
  });

  const entry = (pk = 1) => useUserCacheStore.getState().entities[pk];
  const upsert = (raw: Record<string, unknown>, orgId?: number) =>
    useUserCacheStore
      .getState()
      .upsert(raw as never, orgId ? { orgId } : undefined);

  it('records guildNickname under the upsert org', () => {
    upsert({ pk: 1, username: 'u', guildNickname: 'Claw' }, 7);
    expect(entry().orgNicknames).toEqual({ 7: 'Claw' });
    expect(entry().orgData[7]).toBeUndefined();
    expect(
      (entry() as unknown as Record<string, unknown>).guildNickname,
    ).toBeUndefined();
  });

  it('ignores guildNickname without an org context', () => {
    upsert({ pk: 1, username: 'u', guildNickname: 'Claw' });
    expect(entry().orgNicknames).toEqual({});
  });

  it('keeps nicknames from several orgs and applies nickname-only changes', () => {
    upsert({ pk: 1, username: 'u', guildNickname: 'A' }, 7);
    upsert({ pk: 1, username: 'u', guildNickname: 'B' }, 8);
    upsert({ pk: 1, username: 'u', guildNickname: 'A2' }, 7);
    expect(entry().orgNicknames).toEqual({ 7: 'A2', 8: 'B' });
  });

  it('keeps the nickname when absent and clears it on explicit null', () => {
    upsert({ pk: 1, username: 'u', guildNickname: 'A' }, 7);
    upsert({ pk: 1, username: 'u' }, 7);
    expect(entry().orgNicknames?.[7]).toBe('A');
    upsert({ pk: 1, username: 'u', guildNickname: null }, 7);
    expect(entry().orgNicknames).toEqual({ 7: null });
  });

  it('keeps MMR alongside the nickname', () => {
    upsert(
      { pk: 1, username: 'u', guildNickname: 'A', mmr: 4000, orgUserPk: 3 },
      7,
    );
    expect(entry().orgData[7]?.mmrs).toEqual({ 1: 4000 });
    expect(entry().orgNicknames?.[7]).toBe('A');
  });

  it('dropScoped removes only that org nickname', () => {
    upsert({ pk: 1, username: 'u', guildNickname: 'A' }, 7);
    upsert({ pk: 1, username: 'u', guildNickname: 'B' }, 8);
    useUserCacheStore.getState().dropScoped({ orgId: 7 });
    expect(entry().orgNicknames).toEqual({ 8: 'B' });
  });
});

describe('userCacheStore per-game org MMR', () => {
  beforeEach(() => {
    useUserCacheStore.getState().reset();
  });

  const entry = () => useUserCacheStore.getState().entities[1];
  const upsert = (raw: Record<string, unknown>) =>
    useUserCacheStore
      .getState()
      .upsert({ pk: 1, username: 'u', orgUserPk: 3, ...raw } as never, {
        orgId: 7,
      });

  it('upsert full game_mmrs then flat Deadlock-only source keeps Dota', () => {
    upsert({ game_mmrs: { '1': 4000, '2': 2500 } });
    upsert({ mmr: 3000, mmr_game_type: 2 });
    expect(entry().orgData[7]?.mmrs).toEqual({ 1: 4000, 2: 3000 });
  });

  it('files flat mmr without mmr_game_type under Dota 2', () => {
    upsert({ mmr: 3000 });
    expect(entry().orgData[7]?.mmrs).toEqual({ 1: 3000 });
  });

  it('prefers game_mmrs over the flat mmr', () => {
    upsert({ mmr: 3000, mmr_game_type: 1, game_mmrs: { '1': 4000, '2': 0 } });
    expect(entry().orgData[7]?.mmrs).toEqual({ 1: 4000, 2: 0 });
  });

  it('detects a change to a single game', () => {
    upsert({ game_mmrs: { '1': 4000, '2': 2500 } });
    const before = useUserCacheStore.getState().entities;
    upsert({ game_mmrs: { '1': 4000, '2': 2500 } });
    expect(useUserCacheStore.getState().entities).toBe(before);
    upsert({ game_mmrs: { '1': 4000, '2': 2600 } });
    expect(useUserCacheStore.getState().entities).not.toBe(before);
    expect(entry().orgData[7]?.mmrs[2]).toBe(2600);
  });

  it('does not store game_mmrs or mmr_game_type on the core entry', () => {
    upsert({ game_mmrs: { '1': 4000 }, mmr_game_type: 1 });
    const raw = entry() as unknown as Record<string, unknown>;
    expect(raw.game_mmrs).toBeUndefined();
    expect(raw.mmr_game_type).toBeUndefined();
  });
});

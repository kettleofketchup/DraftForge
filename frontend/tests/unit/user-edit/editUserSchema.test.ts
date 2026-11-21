import { describe, expect, it, vi } from 'vitest';
import { updateOrgUser } from '~/components/api/api';
import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
import {
  buildDefaults,
  dispatchPatch,
  EditUserSchema,
  pickDirty,
} from '~/components/user/userCard/editUserSchema';

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  updateOrgUser: vi.fn(),
}));

const baseUser = {
  pk: 42,
  orgUserPk: 7,
  username: 'alice',
  nickname: 'Ali',
  mmr: 5000,
  steam_account_id: 999,
  positions: { carry: 1, mid: 2, offlane: 3, soft_support: 4, hard_support: 5 },
  is_staff: false,
  is_superuser: false,
} as any;

const org = { pk: 11, name: 'Test Org' } as OrganizationType;
const league = {
  pk: 22,
  name: 'Test League',
  organization: org,
} as unknown as LeagueType;

describe('buildDefaults', () => {
  it('includes every game in org scope', () => {
    const d = buildDefaults(
      { ...baseUser, game_mmrs: { '1': 5000, '2': 2500 } },
      { kind: 'org', organization: org },
    );
    expect(d.game_mmrs).toEqual({ '1': 5000, '2': 2500 });
    expect(d.nickname).toBe('Ali');
    expect(d.positions.carry).toBe(1);
  });

  it('includes the league game in league scope', () => {
    const d = buildDefaults(baseUser, {
      kind: 'league',
      league,
      organization: org,
    });
    expect(d.game_mmrs).toEqual({ '1': 5000 });
  });

  it('Deadlock tournament scope defaults only Deadlock from flat mmr', () => {
    const d = buildDefaults(
      { ...baseUser, mmr: 2500, mmr_game_type: 2 },
      { kind: 'org', organization: org, gameType: 2 },
    );
    expect(d.game_mmrs).toEqual({ '2': 2500 });
  });

  it('omits org MMR in global scope', () => {
    const d = buildDefaults(baseUser, { kind: 'global' });
    expect('game_mmrs' in d).toBe(false);
    expect('mmr' in d).toBe(false);
  });

  it('defaults missing positions to 0 not undefined', () => {
    const u = { ...baseUser, positions: { carry: 1 } };
    const d = buildDefaults(u, { kind: 'global' });
    expect(d.positions.mid).toBe(0);
    expect(d.positions.hard_support).toBe(0);
  });

  it('coerces nullish strings to null', () => {
    const u = { ...baseUser, nickname: undefined };
    const d = buildDefaults(u, { kind: 'global' });
    expect(d.nickname).toBe(null);
  });
});

describe('pickDirty', () => {
  it('returns empty object when no fields are dirty', () => {
    expect(pickDirty({ nickname: 'x' } as any, {})).toEqual({});
  });

  it('picks top-level dirty fields', () => {
    expect(
      pickDirty(
        { nickname: 'NewNick', game_mmrs: { '1': 6000 } } as any,
        { nickname: true } as any,
      ),
    ).toEqual({ nickname: 'NewNick' });
  });

  it('recurses into positions for partial nested dirty', () => {
    expect(
      pickDirty(
        {
          positions: {
            carry: 1,
            mid: 2,
            offlane: 3,
            soft_support: 4,
            hard_support: 5,
          },
        } as any,
        { positions: { carry: true, hard_support: true } } as any,
      ),
    ).toEqual({ positions: { carry: 1, hard_support: 5 } });
  });

  it('combines top-level and nested dirty fields', () => {
    const data = {
      nickname: 'New',
      game_mmrs: { '1': 6000, '2': 3000 },
      positions: {
        carry: 1,
        mid: 2,
        offlane: 3,
        soft_support: 4,
        hard_support: 5,
      },
    } as any;
    const dirty = {
      nickname: true,
      positions: { carry: true },
      game_mmrs: { '2': true },
    } as any;
    expect(pickDirty(data, dirty)).toEqual({
      nickname: 'New',
      positions: { carry: 1 },
      game_mmrs: { '2': 3000 },
    });
  });
});

describe('EditUserSchema', () => {
  it('accepts a full valid input', () => {
    const result = EditUserSchema.safeParse({
      nickname: 'Ali',
      steam_account_id: 999,
      positions: {
        carry: 1,
        mid: 2,
        offlane: 3,
        soft_support: 4,
        hard_support: 5,
      },
      game_mmrs: { '1': 5000, '2': null },
    });
    expect(result.success).toBe(true);
  });

  it('coerces numeric strings on game_mmrs and steam_account_id', () => {
    const result = EditUserSchema.safeParse({
      nickname: 'Ali',
      steam_account_id: '999',
      positions: {
        carry: 0,
        mid: 0,
        offlane: 0,
        soft_support: 0,
        hard_support: 0,
      },
      game_mmrs: { '2': '5000' },
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.game_mmrs?.['2']).toBe(5000);
      expect(result.data.steam_account_id).toBe(999);
    }
  });

  it('rejects positions out of range', () => {
    const result = EditUserSchema.safeParse({
      nickname: 'Ali',
      steam_account_id: 0,
      positions: {
        carry: 6,
        mid: 0,
        offlane: 0,
        soft_support: 0,
        hard_support: 0,
      },
    });
    expect(result.success).toBe(false);
  });
});

describe('dispatchPatch per-game org MMR', () => {
  it('sends only the dirty games and ?game_type=1 in org scope', async () => {
    const mock = vi.mocked(updateOrgUser);
    mock.mockResolvedValue({ pk: 42, mmr: 6000 } as any);
    const user = { ...baseUser, dbUpdate: vi.fn() };
    await dispatchPatch(
      user,
      { kind: 'org', organization: org },
      { game_mmrs: { '1': 6000 } },
    );
    expect(mock).toHaveBeenCalledWith(11, 7, { game_mmrs: { 1: 6000 } }, 1);
  });

  it('sends a Deadlock edit with ?game_type=2 and no legacy mmr', async () => {
    const mock = vi.mocked(updateOrgUser);
    mock.mockResolvedValue({ pk: 42, mmr: 3000 } as any);
    const user = { ...baseUser, dbUpdate: vi.fn() };
    await dispatchPatch(
      user,
      { kind: 'org', organization: org, gameType: 2 },
      { game_mmrs: { '2': 3000 } },
    );
    expect(mock).toHaveBeenCalledWith(11, 7, { game_mmrs: { 2: 3000 } }, 2);
  });

  it('sends a Deadlock league-scoped clear as null', async () => {
    const mock = vi.mocked(updateOrgUser);
    mock.mockResolvedValue({ pk: 42, mmr: 0 } as any);
    const user = { ...baseUser, dbUpdate: vi.fn() };
    await dispatchPatch(
      user,
      { kind: 'league', league, organization: org, gameType: 2 },
      { game_mmrs: { '2': null } },
    );
    expect(mock).toHaveBeenCalledWith(11, 7, { game_mmrs: { 2: null } }, 2);
  });
});

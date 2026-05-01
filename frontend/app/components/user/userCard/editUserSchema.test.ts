import { describe, expect, it } from 'vitest';
import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
import {
  buildDefaults,
  EditUserSchema,
  pickDirty,
  type EditUserInput,
  type EditUserScope,
} from './editUserSchema';

const baseUser = {
  pk: 42,
  orgUserPk: 7,
  username: 'alice',
  nickname: 'Ali',
  mmr: 5000,
  steam_account_id: 999,
  guildNickname: 'AliGuild',
  positions: { carry: 1, mid: 2, offlane: 3, soft_support: 4, hard_support: 5 },
  is_staff: false,
  is_superuser: false,
} as any;

const org = { pk: 11, name: 'Test Org' } as OrganizationType;
const league = { pk: 22, name: 'Test League', organization: org } as unknown as LeagueType;

describe('buildDefaults', () => {
  it('includes mmr in org scope', () => {
    const d = buildDefaults(baseUser, { kind: 'org', organization: org });
    expect(d.mmr).toBe(5000);
    expect(d.nickname).toBe('Ali');
    expect(d.positions.carry).toBe(1);
  });

  it('includes mmr in league scope', () => {
    const d = buildDefaults(baseUser, { kind: 'league', league, organization: org });
    expect(d.mmr).toBe(5000);
  });

  it('omits mmr in global scope', () => {
    const d = buildDefaults(baseUser, { kind: 'global' });
    expect('mmr' in d).toBe(false);
  });

  it('defaults missing positions to 0 not undefined', () => {
    const u = { ...baseUser, positions: { carry: 1 } };
    const d = buildDefaults(u, { kind: 'global' });
    expect(d.positions.mid).toBe(0);
    expect(d.positions.hard_support).toBe(0);
  });

  it('coerces nullish strings to null', () => {
    const u = { ...baseUser, nickname: undefined, guildNickname: null };
    const d = buildDefaults(u, { kind: 'global' });
    expect(d.nickname).toBe(null);
    expect(d.guildNickname).toBe(null);
  });
});

describe('pickDirty', () => {
  it('returns empty object when no fields are dirty', () => {
    expect(pickDirty({ nickname: 'x' } as any, {})).toEqual({});
  });

  it('picks top-level dirty fields', () => {
    expect(
      pickDirty(
        { nickname: 'NewNick', mmr: 6000 } as any,
        { nickname: true } as any,
      ),
    ).toEqual({ nickname: 'NewNick' });
  });

  it('recurses into positions for partial nested dirty', () => {
    expect(
      pickDirty(
        { positions: { carry: 1, mid: 2, offlane: 3, soft_support: 4, hard_support: 5 } } as any,
        { positions: { carry: true, hard_support: true } } as any,
      ),
    ).toEqual({ positions: { carry: 1, hard_support: 5 } });
  });

  it('combines top-level and nested dirty fields', () => {
    const data = {
      nickname: 'New',
      mmr: 6000,
      positions: { carry: 1, mid: 2, offlane: 3, soft_support: 4, hard_support: 5 },
    } as any;
    const dirty = { nickname: true, positions: { carry: true } } as any;
    expect(pickDirty(data, dirty)).toEqual({
      nickname: 'New',
      positions: { carry: 1 },
    });
  });
});

describe('EditUserSchema', () => {
  it('accepts a full valid input', () => {
    const result = EditUserSchema.safeParse({
      nickname: 'Ali',
      steam_account_id: 999,
      guildNickname: 'AliGuild',
      positions: { carry: 1, mid: 2, offlane: 3, soft_support: 4, hard_support: 5 },
      mmr: 5000,
    });
    expect(result.success).toBe(true);
  });

  it('coerces numeric strings on mmr and steam_account_id', () => {
    const result = EditUserSchema.safeParse({
      nickname: 'Ali',
      steam_account_id: '999',
      guildNickname: null,
      positions: { carry: 0, mid: 0, offlane: 0, soft_support: 0, hard_support: 0 },
      mmr: '5000',
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.mmr).toBe(5000);
      expect(result.data.steam_account_id).toBe(999);
    }
  });

  it('rejects positions out of range', () => {
    const result = EditUserSchema.safeParse({
      nickname: 'Ali',
      steam_account_id: 0,
      guildNickname: null,
      positions: { carry: 6, mid: 0, offlane: 0, soft_support: 0, hard_support: 0 },
    });
    expect(result.success).toBe(false);
  });
});

import { describe, expect, it } from 'vitest';
import { buildSignupPatchSchema } from '../EventSignupModal/schema';

const baseEvent = {
  game_type: 1, // DOTA2
  require_steam_id: true,
  allow_active_mmr: true,
  allow_previous_rank: true,
  allow_battlecup_rating: true,
  discord_require_rank_screenshot: false,
  discord_require_battlecup_screenshot: false,
};

const emptyProfile = null;

const completePositions = {
  carry: 1,
  mid: 0,
  offlane: 0,
  soft_support: 0,
  hard_support: 0,
};

const emptyPositions = {
  carry: 0,
  mid: 0,
  offlane: 0,
  soft_support: 0,
  hard_support: 0,
};

describe('buildSignupPatchSchema', () => {
  it('requires friend_id when required-and-missing', () => {
    const schema = buildSignupPatchSchema(baseEvent as never, emptyProfile);
    const result = schema.safeParse({});
    expect(result.success).toBe(false);
  });

  it('accepts a complete payload (positions as priority dict)', () => {
    const schema = buildSignupPatchSchema(baseEvent as never, emptyProfile);
    const ok = schema.safeParse({
      steam_account_id: '12345',
      rank_status: 'active',
      positions: {
        carry: 1,
        mid: 2,
        offlane: 0,
        soft_support: 0,
        hard_support: 0,
      },
      rank_medal_medal: 'Legend',
      rank_medal_star: '3',
    });
    expect(ok.success).toBe(true);
  });

  it('rejects positions with all zeros when positions are required', () => {
    const schema = buildSignupPatchSchema(baseEvent as never, emptyProfile);
    const result = schema.safeParse({
      steam_account_id: '12345',
      rank_status: 'active',
      positions: emptyPositions,
      rank_medal_medal: 'Immortal',
    });
    expect(result.success).toBe(false);
  });

  it('accepts Immortal without star', () => {
    const schema = buildSignupPatchSchema(baseEvent as never, emptyProfile);
    const ok = schema.safeParse({
      steam_account_id: '12345',
      rank_status: 'active',
      positions: completePositions,
      rank_medal_medal: 'Immortal',
    });
    expect(ok.success).toBe(true);
  });

  it('rejects medal without star for non-Immortal', () => {
    const schema = buildSignupPatchSchema(baseEvent as never, emptyProfile);
    const result = schema.safeParse({
      steam_account_id: '12345',
      rank_status: 'active',
      positions: completePositions,
      rank_medal_medal: 'Legend',
      // star missing
    });
    expect(result.success).toBe(false);
  });

  it('rejects bad screenshot URL when required', () => {
    const event = { ...baseEvent, discord_require_rank_screenshot: true };
    const schema = buildSignupPatchSchema(event as never, emptyProfile);
    const result = schema.safeParse({
      steam_account_id: '12345',
      rank_status: 'active',
      positions: completePositions,
      rank_medal_medal: 'Legend',
      rank_medal_star: '1',
      rank_screenshot: 'not-a-url',
    });
    expect(result.success).toBe(false);
  });

  it('still requires rank_status when profile has default never with no battle_cup_tier', () => {
    const profile = {
      steam_account_id: '12345',
      positions: {
        pos_1: true,
        pos_2: false,
        pos_3: false,
        pos_4: false,
        pos_5: false,
      },
      rank_status: 'never',
      rank_medal: null,
      mmr: null,
      rank_screenshot: null,
      battlecup_screenshot: null,
      battle_cup_tier: null,
    };
    const schema = buildSignupPatchSchema(baseEvent as never, profile as never);
    const result = schema.safeParse({
      steam_account_id: '12345',
      positions: completePositions,
    });
    expect(result.success).toBe(false);
  });

  it('treats rank_status as optional when profile has never WITH battle_cup_tier', () => {
    const profile = {
      steam_account_id: '12345',
      positions: {
        pos_1: true,
        pos_2: false,
        pos_3: false,
        pos_4: false,
        pos_5: false,
      },
      rank_status: 'never',
      rank_medal: null,
      mmr: null,
      rank_screenshot: null,
      battlecup_screenshot: null,
      battle_cup_tier: 4,
    };
    const schema = buildSignupPatchSchema(baseEvent as never, profile as never);
    const result = schema.safeParse({
      steam_account_id: '12345',
      positions: completePositions,
    });
    expect(result.success).toBe(true);
  });

  it('treats positions as optional when user already has priorities on their main profile', () => {
    // userPositions has carry=3 — user has picked a position; the modal
    // shouldn't force them to re-enter it just to RSVP.
    const userPositions = {
      carry: 3,
      mid: 0,
      offlane: 0,
      soft_support: 0,
      hard_support: 0,
    };
    const schema = buildSignupPatchSchema(baseEvent as never, emptyProfile, {
      userPositions,
    });
    const result = schema.safeParse({
      steam_account_id: '12345',
      rank_status: 'active',
      rank_medal_medal: 'Immortal',
    });
    expect(result.success).toBe(true);
  });

  it('trims the friend id and rejects non-digits', () => {
    const schema = buildSignupPatchSchema(baseEvent as never, emptyProfile);
    const base = {
      rank_status: 'never',
      positions: completePositions,
    };
    const padded = schema.safeParse({
      ...base,
      steam_account_id: ' 12345 ',
    });
    expect(padded.success).toBe(true);
    if (padded.success) {
      expect((padded.data as Record<string, unknown>).steam_account_id).toBe(
        '12345',
      );
    }
    const bad = schema.safeParse({ ...base, steam_account_id: '12a' });
    expect(bad.success).toBe(false);
    if (!bad.success) {
      expect(bad.error.issues.map((i) => i.path.join('.'))).toContain(
        'steam_account_id',
      );
    }
  });

  it('rejects a whitespace-only friend id when required', () => {
    const schema = buildSignupPatchSchema(baseEvent as never, emptyProfile);
    const result = schema.safeParse({
      rank_status: 'never',
      positions: completePositions,
      steam_account_id: '   ',
    });
    expect(result.success).toBe(false);
  });

  it('does not require friend id when steam_account_id is set', () => {
    const schema = buildSignupPatchSchema(baseEvent as never, emptyProfile, {
      steamAccountId: 12345,
    });
    const parsed = schema.safeParse({});
    const paths = parsed.success
      ? []
      : parsed.error.issues.map((i) => i.path.join('.'));
    expect(paths).not.toContain('steam_account_id');
  });

  it('drops a submitted friend id when the user already has one', () => {
    const schema = buildSignupPatchSchema(baseEvent as never, emptyProfile, {
      steamAccountId: 12345,
    });
    const parsed = schema.safeParse({
      rank_status: 'never',
      positions: completePositions,
      steam_account_id: '99999',
    });
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data).not.toHaveProperty('steam_account_id');
    }
  });

  it('accepts friend ids up to 2^32-1 and rejects 0 and larger ids', () => {
    const schema = buildSignupPatchSchema(baseEvent as never, emptyProfile);
    const base = { rank_status: 'never', positions: completePositions };
    expect(
      schema.safeParse({ ...base, steam_account_id: '4294967295' }).success,
    ).toBe(true);
    for (const fid of ['0', '4294967296']) {
      expect(schema.safeParse({ ...base, steam_account_id: fid }).success).toBe(
        false,
      );
    }
  });
});

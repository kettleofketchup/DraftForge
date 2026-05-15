import { describe, it, expect } from 'vitest';
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

describe('buildSignupPatchSchema', () => {
  it('requires friend_id when required-and-missing', () => {
    const schema = buildSignupPatchSchema(baseEvent as never, emptyProfile);
    const result = schema.safeParse({});
    expect(result.success).toBe(false);
  });

  it('accepts a complete payload', () => {
    const schema = buildSignupPatchSchema(baseEvent as never, emptyProfile);
    const ok = schema.safeParse({
      unverified_friend_id: '12345',
      rank_status: 'active',
      positions: [1, 2],
      rank_medal_medal: 'Legend',
      rank_medal_star: '3',
    });
    expect(ok.success).toBe(true);
  });

  it('accepts Immortal without star', () => {
    const schema = buildSignupPatchSchema(baseEvent as never, emptyProfile);
    const ok = schema.safeParse({
      unverified_friend_id: '12345',
      rank_status: 'active',
      positions: [1],
      rank_medal_medal: 'Immortal',
    });
    expect(ok.success).toBe(true);
  });

  it('rejects medal without star for non-Immortal', () => {
    const schema = buildSignupPatchSchema(baseEvent as never, emptyProfile);
    const result = schema.safeParse({
      unverified_friend_id: '12345',
      rank_status: 'active',
      positions: [1],
      rank_medal_medal: 'Legend',
      // star missing
    });
    expect(result.success).toBe(false);
  });

  it('rejects bad screenshot URL when required', () => {
    const event = { ...baseEvent, discord_require_rank_screenshot: true };
    const schema = buildSignupPatchSchema(event as never, emptyProfile);
    const result = schema.safeParse({
      unverified_friend_id: '12345',
      rank_status: 'active',
      positions: [1],
      rank_medal_medal: 'Legend',
      rank_medal_star: '1',
      rank_screenshot: 'not-a-url',
    });
    expect(result.success).toBe(false);
  });

  it('still requires rank_status when profile has default never with no battle_cup_tier', () => {
    // Mirrors evaluateSignupGap: default rank_status='never' from get_or_create
    // is treated as not-really-set unless corroborated by battle_cup_tier.
    const profile = {
      unverified_friend_id: '12345',
      positions: { pos_1: true, pos_2: false, pos_3: false, pos_4: false, pos_5: false },
      rank_status: 'never',
      rank_medal: null,
      mmr: null,
      rank_screenshot: null,
      battlecup_screenshot: null,
      battle_cup_tier: null,
    };
    const schema = buildSignupPatchSchema(baseEvent as never, profile as never);
    const result = schema.safeParse({
      unverified_friend_id: '12345',
      positions: [1],
      // rank_status omitted — should fail because the default 'never' on the
      // profile is not "really set" yet.
    });
    expect(result.success).toBe(false);
  });

  it('treats rank_status as optional when profile has never WITH battle_cup_tier', () => {
    const profile = {
      unverified_friend_id: '12345',
      positions: { pos_1: true, pos_2: false, pos_3: false, pos_4: false, pos_5: false },
      rank_status: 'never',
      rank_medal: null,
      mmr: null,
      rank_screenshot: null,
      battlecup_screenshot: null,
      battle_cup_tier: 4,
    };
    const schema = buildSignupPatchSchema(baseEvent as never, profile as never);
    const result = schema.safeParse({
      unverified_friend_id: '12345',
      positions: [1],
    });
    expect(result.success).toBe(true);
  });
});

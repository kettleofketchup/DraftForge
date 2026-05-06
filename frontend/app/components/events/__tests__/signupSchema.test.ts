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
});

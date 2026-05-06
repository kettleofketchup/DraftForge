import { describe, it, expect } from 'vitest';
import { evaluateSignupGap } from '../EventSignupModal/evaluateSignupGap';
import { GameType } from '../schemas';

const baseEvent = {
  id: 1,
  game_type: GameType.DOTA2,
  require_steam_id: false,
  allow_active_mmr: true,
  allow_previous_rank: true,
  allow_battlecup_rating: true,
  discord_require_rank_screenshot: false,
  discord_require_battlecup_screenshot: false,
};

const completeProfile = {
  unverified_friend_id: '123',
  rank_status: 'active' as const,
  rank_medal: 'Legend 1',
  positions: { pos_1: true, pos_2: false, pos_3: false, pos_4: false, pos_5: false },
  battle_cup_tier: null,
  rank_screenshot: null,
  battlecup_screenshot: null,
  mmr: null,
};

describe('evaluateSignupGap', () => {
  it('returns complete when nothing is missing', () => {
    expect(evaluateSignupGap(baseEvent as never, completeProfile as never)).toBe('complete');
  });

  it('flags friend_id when required and missing (universal across game types)', () => {
    const event = { ...baseEvent, require_steam_id: true, game_type: 99 };
    const profile = { ...completeProfile, unverified_friend_id: null };
    expect(evaluateSignupGap(event as never, profile as never)).toEqual(['friend_id']);
  });

  it('flags rank_status when missing on Dota 2', () => {
    const profile = { ...completeProfile, rank_status: '' };
    expect(evaluateSignupGap(baseEvent as never, profile as never)).toContain('rank_status');
  });

  it('flags rank_screenshot when required and missing for active rank', () => {
    const event = { ...baseEvent, discord_require_rank_screenshot: true };
    const profile = { ...completeProfile, rank_screenshot: null };
    expect(evaluateSignupGap(event as never, profile as never)).toContain('rank_screenshot');
  });

  it('does not flag screenshots for never-rank when battlecup screenshot is present', () => {
    const event = { ...baseEvent, discord_require_battlecup_screenshot: true };
    const profile = {
      ...completeProfile,
      rank_status: 'never' as const,
      rank_medal: null,
      battle_cup_tier: 5,
      battlecup_screenshot: 'https://i.imgur.com/x.png',
    };
    expect(evaluateSignupGap(event as never, profile as never)).toBe('complete');
  });

  it('flags battle_cup_tier when never-rank without tier set', () => {
    const profile = {
      ...completeProfile,
      rank_status: 'never' as const,
      rank_medal: null,
      battle_cup_tier: null,
    };
    expect(evaluateSignupGap(baseEvent as never, profile as never)).toContain('battle_cup_tier');
  });

  it('returns multiple missing keys when profile is empty', () => {
    const event = { ...baseEvent, require_steam_id: true };
    const result = evaluateSignupGap(event as never, null);
    expect(result).not.toBe('complete');
    expect(result).toContain('friend_id');
    expect(result).toContain('rank_status');
    expect(result).toContain('positions');
  });
});

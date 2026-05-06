import { type EventType } from '../schemas';
import { GAME_TYPE } from '~/components/game/constants';
import type { DotaProfileData } from '~/components/user';

function hasAnyPosition(profile: DotaProfileData | null | undefined): boolean {
  if (!profile?.positions) return false;
  const p = profile.positions;
  return !!(p.pos_1 || p.pos_2 || p.pos_3 || p.pos_4 || p.pos_5);
}

/**
 * Returns 'complete' if the profile satisfies all event requirements (skip-the-form
 * fast path), or a list of missing-section keys otherwise. The caller opens the
 * modal when the result is non-empty.
 *
 * Friend ID gate is universal across game types. Rich profile gates apply only
 * to Dota 2.
 */
export function evaluateSignupGap(
  event: EventType,
  profile: DotaProfileData | null | undefined,
): 'complete' | string[] {
  const missing: string[] = [];

  if (event.require_steam_id && !profile?.unverified_friend_id) missing.push('friend_id');

  if (event.game_type === GAME_TYPE.DOTA2) {
    if (!profile?.rank_status) missing.push('rank_status');
    if (!hasAnyPosition(profile)) missing.push('positions');
    if (profile?.rank_status === 'active' || profile?.rank_status === 'previous') {
      if (!profile.rank_medal) missing.push('rank_medal');
    }
    if (profile?.rank_status === 'never' && profile.battle_cup_tier == null) {
      missing.push('battle_cup_tier');
    }
    if (event.discord_require_rank_screenshot &&
        (profile?.rank_status === 'active' || profile?.rank_status === 'previous') &&
        !profile.rank_screenshot) {
      missing.push('rank_screenshot');
    }
    if (event.discord_require_battlecup_screenshot &&
        profile?.rank_status === 'never' &&
        !profile.battlecup_screenshot) {
      missing.push('battlecup_screenshot');
    }
  }

  return missing.length === 0 ? 'complete' : missing;
}

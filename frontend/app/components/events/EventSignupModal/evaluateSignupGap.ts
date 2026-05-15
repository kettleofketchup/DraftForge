import { type EventType } from '../schemas';
import { GAME_TYPE } from '~/components/game/constants';
import type { DotaProfileData } from '~/components/user';

function hasAnyPosition(profile: DotaProfileData | null | undefined): boolean {
  if (!profile?.positions) return false;
  const p = profile.positions;
  return !!(p.pos_1 || p.pos_2 || p.pos_3 || p.pos_4 || p.pos_5);
}

/**
 * Per-game completeness rule for the Dota 2 rank section.
 *
 * "Complete" means: a rank_status is picked AND the field that backs it up
 * carries a value (rank_medal for active/previous, battle_cup_tier for never).
 * Without the backing field, a `rank_status="never"` value could just be the
 * default that PlayerDotaProfile.get_or_create emits on first read — not a
 * deliberate user choice.
 */
function isDotaRankSectionComplete(
  profile: DotaProfileData | null | undefined,
): boolean {
  if (!profile?.rank_status) return false;
  if (profile.rank_status === 'never') {
    return profile.battle_cup_tier != null;
  }
  if (profile.rank_status === 'active' || profile.rank_status === 'previous') {
    return !!profile.rank_medal;
  }
  return false;
}

/**
 * isRankSectionComplete — has the user fully filled the rank section of their
 * profile for the event's game?
 *
 * Purpose: gate both the skip-the-form fast path (in evaluateSignupGap) and the
 * "is this field required?" decision in the signup form's zod schema. Both
 * callers must agree on what "complete" means; if the gap evaluator opens the
 * modal because rank is missing, the form must refuse to submit without one.
 *
 * The rule is game-specific. Dispatch by `event.game_type` so each game can
 * own its own completeness definition without leaking rules across games:
 *   - DOTA2: rank_status + corroborating medal/tier (see isDotaRankSectionComplete).
 *   - DEADLOCK: no rank section in the web signup modal today — vacuously true so
 *     the gap evaluator and schema don't try to enforce a rank field that the
 *     modal never renders. When Deadlock gains a rank section, add a helper.
 *
 * Returning `true` for games with no rank section is intentional: callers ask
 * "is the rank section a blocker?", and the answer for those games is "no".
 */
export function isRankSectionComplete(
  event: EventType,
  profile: DotaProfileData | null | undefined,
): boolean {
  switch (event.game_type) {
    case GAME_TYPE.DOTA2:
      return isDotaRankSectionComplete(profile);
    case GAME_TYPE.DEADLOCK:
      return true;
    default:
      return true;
  }
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
    if (!isRankSectionComplete(event, profile)) missing.push('rank_status');
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

import { z } from 'zod';
import { type EventType } from '../schemas';
import { GAME_TYPE } from '~/components/game/constants';
import type { DotaProfileData } from '~/components/user';
import { isRankSectionComplete } from './evaluateSignupGap';

const SCREENSHOT_URL_RE = /^https?:\/\/.+\.(png|jpe?g|webp)(\?.*)?$/i;

/**
 * Builds the zod schema for the signup form, dynamically based on the event's
 * config flags and what the user already has on their profile. Only the fields
 * the user actually needs to fill are required.
 *
 * `rank_medal_medal` and `rank_medal_star` are split UI fields the form stitches
 * into `rank_medal` at submit time. Including them here so the resolver doesn't
 * strip them; superRefine validates the joint state.
 */
type UserPositions = {
  carry?: number;
  mid?: number;
  offlane?: number;
  soft_support?: number;
  hard_support?: number;
} | null | undefined;

export function buildSignupPatchSchema(
  event: EventType,
  profile: DotaProfileData | null | undefined,
  userPositions?: UserPositions,
) {
  const fields: Record<string, z.ZodType> = {};

  if (event.require_steam_id && !profile?.unverified_friend_id) {
    fields.unverified_friend_id = z.string().min(1).max(20);
  } else {
    fields.unverified_friend_id = z.string().max(20).optional();
  }

  if (event.game_type === GAME_TYPE.DOTA2) {
    // Mirror evaluateSignupGap's per-game rule: the form requires rank_status
    // whenever the gap evaluator considered the rank section incomplete.
    // Without this, default `rank_status="never"` from get_or_create is treated
    // as already-picked here while the gap evaluator treats it as missing, and
    // the user can submit without ever picking a rank.
    if (!isRankSectionComplete(event, profile)) {
      fields.rank_status = z.enum(['active', 'previous', 'never']);
    } else {
      fields.rank_status = z.enum(['active', 'previous', 'never']).optional();
    }

    // Positions: priority dict matching User.positions (PositionsModel) shape
    // — each role rated 0..5 where 0 = "don't show this role" and 1..5 ranks
    // willingness (Favorite → Least Favorite). Mirrors the edit-profile
    // PositionForm so users don't relearn the UI per event.
    // Required when the user hasn't picked positions yet (all zeros).
    const positionDict = z.object({
      carry: z.number().int().min(0).max(5),
      mid: z.number().int().min(0).max(5),
      offlane: z.number().int().min(0).max(5),
      soft_support: z.number().int().min(0).max(5),
      hard_support: z.number().int().min(0).max(5),
    });
    // "Already picked" if the user has any non-zero priority on their main
    // profile (CustomUser.positions). Fallback to the per-org DotaProfile
    // booleans for back-compat when userPositions isn't provided.
    const hasPosFromUser = userPositions
      ? [
          userPositions.carry,
          userPositions.mid,
          userPositions.offlane,
          userPositions.soft_support,
          userPositions.hard_support,
        ].some((v) => (v ?? 0) > 0)
      : false;
    const hasPosFromProfile = profile?.positions
      ? Object.values(profile.positions).some(Boolean)
      : false;
    const hasPos = hasPosFromUser || hasPosFromProfile;
    if (!hasPos) {
      fields.positions = positionDict.refine(
        (p) => p.carry + p.mid + p.offlane + p.soft_support + p.hard_support > 0,
        { message: 'Pick at least one position' },
      );
    } else {
      fields.positions = positionDict.optional();
    }

    fields.rank_medal_medal = z.string().optional();
    fields.rank_medal_star = z.string().optional();
    fields.rank_medal = z.string().max(64).optional();
    fields.battle_cup_tier = z.number().int().min(1).max(8).optional();

    fields.rank_screenshot = z.string().regex(SCREENSHOT_URL_RE).optional();
    fields.battlecup_screenshot = z.string().regex(SCREENSHOT_URL_RE).optional();
  }

  return z.object(fields).superRefine((data, ctx) => {
    // Active/previous: medal+star must be picked together. Immortal medal needs no star.
    if (data.rank_status === 'active' || data.rank_status === 'previous') {
      const medal = (data as Record<string, unknown>).rank_medal_medal as string | undefined;
      const star = (data as Record<string, unknown>).rank_medal_star as string | undefined;
      const isImmortal = medal === 'Immortal';
      if (!medal) {
        ctx.addIssue({ code: 'custom', message: 'Pick a medal', path: ['rank_medal_medal'] });
      } else if (!isImmortal && !star) {
        ctx.addIssue({ code: 'custom', message: 'Pick a star', path: ['rank_medal_star'] });
      }
    }
  });
}

export type SignupInputPatch = z.infer<ReturnType<typeof buildSignupPatchSchema>>;

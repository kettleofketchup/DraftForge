import { z } from 'zod';
import { type EventType } from '../schemas';
import { GAME_TYPE } from '~/components/game/constants';
import type { DotaProfileData } from '~/components/user';

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
export function buildSignupPatchSchema(
  event: EventType,
  profile: DotaProfileData | null | undefined,
) {
  const fields: Record<string, z.ZodType> = {};

  if (event.require_steam_id && !profile?.unverified_friend_id) {
    fields.unverified_friend_id = z.string().min(1).max(20);
  } else {
    fields.unverified_friend_id = z.string().max(20).optional();
  }

  if (event.game_type === GAME_TYPE.DOTA2) {
    if (!profile?.rank_status) {
      fields.rank_status = z.enum(['active', 'previous', 'never']);
    } else {
      fields.rank_status = z.enum(['active', 'previous', 'never']).optional();
    }

    const hasPos = profile?.positions
      ? Object.values(profile.positions).some(Boolean)
      : false;
    if (!hasPos) {
      fields.positions = z.array(z.number().int().min(1).max(5)).min(1);
    } else {
      fields.positions = z.array(z.number().int().min(1).max(5)).optional();
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

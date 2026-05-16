import type { SignupInputPatch } from './schema';
import type { DotaProfileData } from '~/components/user';

type UserPositions = {
  carry?: number;
  mid?: number;
  offlane?: number;
  soft_support?: number;
  hard_support?: number;
} | null | undefined;

const POSITION_KEYS = [
  'carry',
  'mid',
  'offlane',
  'soft_support',
  'hard_support',
] as const;

function positionsEqual(a: UserPositions, b: UserPositions): boolean {
  return POSITION_KEYS.every((k) => (a?.[k] ?? 0) === (b?.[k] ?? 0));
}

/**
 * Diffs form values against (profile, userPositions) and returns only changed
 * fields. Used so the request body to /signup/ is a minimal patch (matches the
 * backend's "fields not in patch are not touched" contract).
 *
 * - `profile` (org-scoped PlayerDotaProfile) supplies rank/medal/screenshot
 *   prior values for the diff.
 * - `userPositions` (CustomUser.positions) supplies the per-role priority
 *   baseline so we only POST the positions dict when the user actually
 *   changed it.
 */
export function toPatch(
  values: SignupInputPatch,
  profile: DotaProfileData | null | undefined,
  userPositions?: UserPositions,
): Partial<SignupInputPatch> {
  const patch: Record<string, unknown> = {};
  const v = values as Record<string, unknown>;
  const p = (profile ?? {}) as Record<string, unknown>;

  for (const key of Object.keys(v)) {
    if (v[key] === undefined) continue;

    // Positions has its own equality (dict shape that doesn't live on
    // profile); skip the generic JSON.stringify compare for it.
    if (key === 'positions') {
      const next = v[key] as UserPositions;
      if (!positionsEqual(next, userPositions)) {
        patch[key] = next;
      }
      continue;
    }

    if (!profile) {
      patch[key] = v[key];
      continue;
    }
    if (JSON.stringify(v[key]) !== JSON.stringify(p[key])) {
      patch[key] = v[key];
    }
  }
  return patch as Partial<SignupInputPatch>;
}

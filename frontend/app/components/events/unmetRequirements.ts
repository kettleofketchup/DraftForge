import type { EventSignupType } from './schemas';

// Mirrors backend events.eligibility.Unmet / UNMET_LABELS.
export const UNMET_CODES = [
  'steam_id_missing',
  'mmr_unverified',
  'profile_incomplete',
  'dota_rank_undeclared',
  'rank_type_disallowed',
  'rank_screenshot_missing',
  'battlecup_screenshot_missing',
  'below_min_mmr',
  'conduct_below_threshold',
] as const;

export type UnmetCode = (typeof UNMET_CODES)[number];

export const UNMET_REQUIREMENT_LABELS: Record<UnmetCode, string> = {
  steam_id_missing: 'Steam friend ID missing',
  mmr_unverified: 'MMR not verified',
  profile_incomplete: 'Profile incomplete',
  dota_rank_undeclared: 'Rank not declared',
  rank_type_disallowed: 'Rank type not accepted',
  rank_screenshot_missing: 'Rank screenshot missing',
  battlecup_screenshot_missing: 'Battle Cup screenshot missing',
  below_min_mmr: 'Below minimum MMR',
  conduct_below_threshold: 'Attendance record below org threshold',
};

function isUnmetCode(code: string): code is UnmetCode {
  return (UNMET_CODES as readonly string[]).includes(code);
}

export function describeUnmet(codes: readonly string[] | undefined): string {
  return (codes ?? [])
    .map((c) => (isUnmetCode(c) ? UNMET_REQUIREMENT_LABELS[c] : c))
    .join(', ');
}

/** Why a signup is held, or null when there is nothing to show for its status. */
export function signupHoldReason(
  signup: Pick<EventSignupType, 'status' | 'unmet_requirements'>,
  autoApprove: boolean,
): string | null {
  const held =
    signup.status === 'pending_approval' ||
    (!autoApprove && signup.status === 'rsvp');
  if (!held) return null;
  return describeUnmet(signup.unmet_requirements) || null;
}

export function signupSuccessMessage(
  intent: 'rsvp' | 'tentative',
  status: string | undefined,
): string {
  if (status === 'pending_approval') return 'Signed up, pending approval';
  return intent === 'rsvp' ? 'Signed up!' : 'Marked as tentative!';
}

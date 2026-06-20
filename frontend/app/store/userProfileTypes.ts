import { z } from 'zod';

// Single-value user-global fields. T1 ships these; future tickets do not
// add to base (game/org-scoped data lives in other layers).
export const BaseProfileSchema = z.object({
  nickname: z.string().nullable().optional(),
  avatar: z.string().nullable().optional(),
});

export type BaseProfile = z.infer<typeof BaseProfileSchema>;

// Edit-layer (modal) shapes. These are the layered GET/PATCH payload the
// EditProfileModal Dota/Deadlock tabs read and write. List/card/table surfaces
// read positions from userCacheStore via selectPositions, NOT from here.
export interface PositionsValue {
  carry: number;
  mid: number;
  offlane: number;
  soft_support: number;
  hard_support: number;
}
export interface DotaUserProfile {
  positions?: PositionsValue | null;
  has_active_dota_mmr?: boolean;
  dota_mmr_last_verified?: string | null;
}
export interface DeadlockUserProfile {
  rank?: string | null;
  rank_date?: string | null;
}
// Placeholders for T3. Kept as empty objects so the type shape is stable
// across the epic and no consumer breaks when later tickets fill them in.
export type OrgUserProfile = Record<string, never>;        // T3 expands
export type OrgDotaUserProfile = { positions?: never };    // T3 expands
export type OrgDeadlockUserProfile = { rank?: never };     // T3 expands

export interface UserProfileEntry {
  pk: number;
  base: BaseProfile;
  gameUser: {
    dota?: DotaUserProfile;
    deadlock?: DeadlockUserProfile;
  };
  orgProfiles: Record<number, {
    orgUser: OrgUserProfile;
    dota?: OrgDotaUserProfile;
    deadlock?: OrgDeadlockUserProfile;
  }>;
  _fetchedAt: number;
}

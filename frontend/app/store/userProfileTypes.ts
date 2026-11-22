import { z } from 'zod';

// Single-value user-global fields only; game- and org-scoped data lives in
// the other layers.
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
// Org-scoped layers are not populated yet. They stay empty so the type shape
// is stable and no consumer breaks when they gain fields.
export type OrgUserProfile = Record<string, never>;
export type OrgDotaUserProfile = { positions?: never };
export type OrgDeadlockUserProfile = { rank?: never };

export interface UserProfileEntry {
  pk: number;
  base: BaseProfile;
  gameUser: {
    dota?: DotaUserProfile;
    deadlock?: DeadlockUserProfile;
  };
  orgProfiles: Record<
    number,
    {
      orgUser: OrgUserProfile;
      dota?: OrgDotaUserProfile;
      deadlock?: OrgDeadlockUserProfile;
    }
  >;
  _fetchedAt: number;
}

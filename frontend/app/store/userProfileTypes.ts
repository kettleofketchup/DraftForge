import { z } from 'zod';

// Single-value user-global fields. T1 ships these; future tickets do not
// add to base (game/org-scoped data lives in other layers).
export const BaseProfileSchema = z.object({
  nickname: z.string().nullable().optional(),
  avatar: z.string().nullable().optional(),
});

export type BaseProfile = z.infer<typeof BaseProfileSchema>;

// Placeholders for T2/T3. Kept as empty objects in T1 so the type
// shape is stable across the epic and no consumer breaks when later
// tickets fill them in.
export type DotaUserProfile = { positions?: never };       // T2 expands
export type DeadlockUserProfile = { rank?: never };        // T2 expands
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

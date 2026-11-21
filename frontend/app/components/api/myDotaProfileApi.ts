import { z } from 'zod';
import api from '~/components/api/axios';
import type { DotaProfileData } from '~/components/user';

// backend/org/views_profiles.py::_serialize_dota_profile
export const MyDotaProfileSchema = z.object({
  id: z.number(),
  org_user_id: z.number(),
  rank_status: z.string().nullable(),
  rank_medal: z.string().nullable(),
  rank_date: z.string().nullable(),
  battle_cup_tier: z.number().nullable(),
  mmr: z.number().nullable(),
  rank_screenshot: z.string().nullable(),
  battlecup_screenshot: z.string().nullable(),
  unverified_friend_id: z.string().nullable(),
  resolved_friend_id: z.string(),
  pos_1: z.boolean(),
  pos_2: z.boolean(),
  pos_3: z.boolean(),
  pos_4: z.boolean(),
  pos_5: z.boolean(),
});
export type MyDotaProfile = z.infer<typeof MyDotaProfileSchema>;

function toProfileData(profile: MyDotaProfile): DotaProfileData {
  return {
    unverified_friend_id: profile.unverified_friend_id,
    resolved_friend_id: profile.resolved_friend_id,
    positions: {
      pos_1: profile.pos_1,
      pos_2: profile.pos_2,
      pos_3: profile.pos_3,
      pos_4: profile.pos_4,
      pos_5: profile.pos_5,
    },
    rank_status: profile.rank_status ?? '',
    rank_medal: profile.rank_medal,
    mmr: profile.mmr,
    rank_screenshot: profile.rank_screenshot,
    battlecup_screenshot: profile.battlecup_screenshot,
    battle_cup_tier: profile.battle_cup_tier,
  };
}

/** GET /organizations/<orgId>/my-dota-profile/ */
export async function getMyDotaProfile(
  orgId: number,
): Promise<DotaProfileData> {
  const response = await api.get(`/organizations/${orgId}/my-dota-profile/`);
  return toProfileData(MyDotaProfileSchema.parse(response.data));
}

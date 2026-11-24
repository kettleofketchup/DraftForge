'use client';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import api from '~/components/api/axios';
import type { DotaProfileData } from '~/components/user';

/** Wire shape of `/api/organizations/<org_id>/my-dota-profile/`
 * (backend/org/views_profiles.py `_serialize_dota_profile`). */
export const DotaProfileApiSchema = z.object({
  id: z.number(),
  org_user_id: z.number(),
  rank_status: z.string(),
  rank_medal: z.string(),
  rank_date: z.string().nullable(),
  battle_cup_tier: z.number().nullable(),
  mmr: z.number().nullable(),
  rank_screenshot: z.string().nullable(),
  battlecup_screenshot: z.string().nullable(),
  steam_account_id: z.number().nullable(),
  steam_account_verified: z.boolean().optional(),
  steam_account_verified_at: z.string().nullable().optional(),
  steam_account_verified_org_name: z.string().nullable().optional(),
  steam_account_exists_checked: z.boolean().optional(),
  pos_1: z.boolean(),
  pos_2: z.boolean(),
  pos_3: z.boolean(),
  pos_4: z.boolean(),
  pos_5: z.boolean(),
});
export type DotaProfileApi = z.infer<typeof DotaProfileApiSchema>;

function adaptApiToData(api: DotaProfileApi): DotaProfileData {
  return {
    positions: {
      pos_1: api.pos_1,
      pos_2: api.pos_2,
      pos_3: api.pos_3,
      pos_4: api.pos_4,
      pos_5: api.pos_5,
    },
    rank_status: api.rank_status ?? '',
    rank_medal: api.rank_medal,
    mmr: api.mmr,
    rank_screenshot: api.rank_screenshot,
    battlecup_screenshot: api.battlecup_screenshot,
    battle_cup_tier: api.battle_cup_tier,
  };
}

/**
 * useUserDotaProfile — fetches the current user's PlayerDotaProfile for an org.
 *
 * Backed by `GET /api/organizations/<orgId>/my-dota-profile/` (auto-creates the
 * profile row if missing — backend uses get_or_create). Profiles are org-scoped
 * because PlayerDotaProfile hangs off OrgUser, so the caller passes the event's
 * organization. Mutations that write the profile (the /signup/ endpoint)
 * invalidate the `['user-dota-profile', userPk, orgId]` query so the next read
 * refetches fresh data.
 *
 * Coerces null → undefined for `initialData` so the query doesn't lock in a
 * resolved-null state (which would prevent refetches).
 *
 * Disabled when `orgId` is null/undefined (e.g., before the event loads). Pass
 * `initialData` from the SSR snapshot when available to avoid a render flicker.
 */
export function useUserDotaProfile(
  userPk: number | null | undefined,
  orgId: number | null | undefined,
  options?: { initialData?: DotaProfileData | null },
) {
  const initialData = options?.initialData ?? undefined;

  return useQuery({
    queryKey: ['user-dota-profile', userPk, orgId],
    queryFn: async () => {
      const resp = await api.get(`/organizations/${orgId}/my-dota-profile/`);
      return adaptApiToData(DotaProfileApiSchema.parse(resp.data));
    },
    enabled: userPk != null && orgId != null,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
    initialData,
  });
}

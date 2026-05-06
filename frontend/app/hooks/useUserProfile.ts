'use client';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import api from '~/components/api/axios';
import type { DotaProfileData } from '~/components/user';

/** Backend wire shape for `/api/organizations/<org_id>/my-dota-profile/`. */
type DotaProfileApi = {
  id: number;
  org_user_id: number;
  rank_status: string | null;
  rank_medal: string | null;
  rank_date: string | null;
  battle_cup_tier: number | null;
  mmr: number | null;
  rank_screenshot: string | null;
  battlecup_screenshot: string | null;
  unverified_friend_id: string | null;
  pos_1: boolean;
  pos_2: boolean;
  pos_3: boolean;
  pos_4: boolean;
  pos_5: boolean;
};

function adaptApiToData(api: DotaProfileApi): DotaProfileData {
  return {
    unverified_friend_id: api.unverified_friend_id,
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
      const resp = await api.get<DotaProfileApi>(
        `/organizations/${orgId}/my-dota-profile/`,
      );
      return adaptApiToData(resp.data);
    },
    enabled: userPk != null && orgId != null,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
    initialData,
  });
}

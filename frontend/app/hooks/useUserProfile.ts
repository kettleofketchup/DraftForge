'use client';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import api from '~/components/api/axios';
import type { DotaProfileData } from '~/components/user';

/**
 * useUserDotaProfile — fetches the current user's PlayerDotaProfile.
 *
 * Spec: skip-the-form fast path needs the freshest profile, not the SSR snapshot.
 *
 * The query is hydrated from `event.user_data.dota_profile` via `initialData`
 * (passed by the caller). If no `/users/<pk>/dota-profile/` endpoint exists yet,
 * the query never fires — consumers fall back to `initialData`. Mutations that
 * write the profile (the new /signup/ endpoint) invalidate this query so the
 * next read refetches fresh data.
 *
 * Coerces null → undefined for `initialData` so the query doesn't lock in a
 * resolved-null state (which would prevent refetches).
 */
export function useUserDotaProfile(
  userPk: number | null | undefined,
  options?: { initialData?: DotaProfileData | null },
) {
  const initialData = options?.initialData ?? undefined;

  return useQuery({
    queryKey: ['user-dota-profile', userPk],
    queryFn: async () => {
      const resp = await api.get<DotaProfileData>(`/users/${userPk}/dota-profile/`);
      return resp.data;
    },
    enabled: userPk != null,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
    initialData,
  });
}

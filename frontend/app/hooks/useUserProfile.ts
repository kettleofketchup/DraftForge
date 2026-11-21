'use client';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getMyDotaProfile } from '~/components/api/myDotaProfileApi';
import type { DotaProfileData } from '~/components/user';

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
    queryFn: () => getMyDotaProfile(orgId as number),
    enabled: userPk != null && orgId != null,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
    initialData,
  });
}

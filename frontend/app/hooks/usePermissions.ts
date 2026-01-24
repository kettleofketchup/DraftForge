/**
 * Permission hooks for checking user access to organizations and leagues.
 *
 * These hooks provide a centralized way to check if the current user has
 * admin or staff access to organizations and leagues.
 *
 * Permission hierarchy:
 * - Organization Admin: Can manage org settings, leagues, and all content
 * - Organization Staff: Can manage tournaments and games within org's leagues
 * - League Admin: Can manage league settings and tournaments
 * - League Staff: Can manage games (declare winners, link steam matches)
 */

import { useMemo } from 'react';
import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
import { useUserStore } from '~/store/userStore';

/**
 * Check if the current user is a superuser/staff (Django global admin).
 */
export function useIsSuperuser(): boolean {
  const currentUser = useUserStore((state) => state.currentUser);
  return !!currentUser?.is_staff;
}

/**
 * Check if the current user is an admin of the given organization.
 *
 * @param organization - The organization to check, or null/undefined
 * @returns true if user is org admin or superuser
 */
export function useIsOrganizationAdmin(
  organization: OrganizationType | null | undefined
): boolean {
  const currentUser = useUserStore((state) => state.currentUser);

  return useMemo(() => {
    if (!currentUser?.pk || !organization) return false;

    // Superuser has access to everything
    if (currentUser.is_staff) return true;

    // Check admin_ids array (preferred, always available)
    if (organization.admin_ids?.includes(currentUser.pk)) return true;

    // Check admins array (may contain full user objects)
    if (organization.admins?.some((admin) => admin.pk === currentUser.pk)) {
      return true;
    }

    return false;
  }, [currentUser?.pk, currentUser?.is_staff, organization]);
}

/**
 * Check if the current user has staff access to the given organization.
 * Staff access includes admins.
 *
 * @param organization - The organization to check, or null/undefined
 * @returns true if user is org admin, org staff, or superuser
 */
export function useIsOrganizationStaff(
  organization: OrganizationType | null | undefined
): boolean {
  const currentUser = useUserStore((state) => state.currentUser);
  const isOrgAdmin = useIsOrganizationAdmin(organization);

  return useMemo(() => {
    if (!currentUser?.pk || !organization) return false;

    // Org admins have staff access
    if (isOrgAdmin) return true;

    // Check staff_ids array
    if (organization.staff_ids?.includes(currentUser.pk)) return true;

    // Check staff array (may contain full user objects)
    if (organization.staff?.some((staff) => staff.pk === currentUser.pk)) {
      return true;
    }

    return false;
  }, [currentUser?.pk, organization, isOrgAdmin]);
}

/**
 * Check if the current user is an admin of the given league.
 * League admin access also includes organization admins.
 *
 * @param league - The league to check, or null/undefined
 * @param organization - The parent organization (optional, for org admin check)
 * @returns true if user is league admin, org admin, or superuser
 */
export function useIsLeagueAdmin(
  league: LeagueType | null | undefined,
  organization?: OrganizationType | null
): boolean {
  const currentUser = useUserStore((state) => state.currentUser);
  const isOrgAdmin = useIsOrganizationAdmin(organization);

  return useMemo(() => {
    if (!currentUser?.pk || !league) return false;

    // Superuser has access to everything
    if (currentUser.is_staff) return true;

    // Org admin has league admin access
    if (isOrgAdmin) return true;

    // Check admin_ids array
    if (league.admin_ids?.includes(currentUser.pk)) return true;

    // Check admins array (may contain full user objects)
    if (league.admins?.some((admin) => admin.pk === currentUser.pk)) {
      return true;
    }

    return false;
  }, [currentUser?.pk, currentUser?.is_staff, league, isOrgAdmin]);
}

/**
 * Check if the current user has staff access to the given league.
 * Staff access includes league admins and organization staff.
 *
 * @param league - The league to check, or null/undefined
 * @param organization - The parent organization (optional, for org staff check)
 * @returns true if user is league admin, league staff, org admin, org staff, or superuser
 */
export function useIsLeagueStaff(
  league: LeagueType | null | undefined,
  organization?: OrganizationType | null
): boolean {
  const currentUser = useUserStore((state) => state.currentUser);
  const isLeagueAdmin = useIsLeagueAdmin(league, organization);
  const isOrgStaff = useIsOrganizationStaff(organization);

  return useMemo(() => {
    if (!currentUser?.pk || !league) return false;

    // League admins have staff access
    if (isLeagueAdmin) return true;

    // Org staff have league staff access
    if (isOrgStaff) return true;

    // Check staff_ids array
    if (league.staff_ids?.includes(currentUser.pk)) return true;

    // Check staff array (may contain full user objects)
    if (league.staff?.some((staff) => staff.pk === currentUser.pk)) {
      return true;
    }

    return false;
  }, [currentUser?.pk, league, isLeagueAdmin, isOrgStaff]);
}

/**
 * Check if the current user can edit a tournament.
 * Requires league admin access.
 *
 * @param league - The league the tournament belongs to
 * @param organization - The parent organization
 * @returns true if user can edit tournaments in this league
 */
export function useCanEditTournament(
  league: LeagueType | null | undefined,
  organization?: OrganizationType | null
): boolean {
  return useIsLeagueAdmin(league, organization);
}

/**
 * Check if the current user can manage games (declare winners, link steam matches).
 * Requires league staff access.
 *
 * @param league - The league the game belongs to
 * @param organization - The parent organization
 * @returns true if user can manage games in this league
 */
export function useCanManageGames(
  league: LeagueType | null | undefined,
  organization?: OrganizationType | null
): boolean {
  return useIsLeagueStaff(league, organization);
}

/**
 * Get all permission flags for convenience.
 * Useful when you need to check multiple permissions at once.
 */
export function usePermissions(
  organization: OrganizationType | null | undefined,
  league: LeagueType | null | undefined
) {
  const isSuperuser = useIsSuperuser();
  const isOrgAdmin = useIsOrganizationAdmin(organization);
  const isOrgStaff = useIsOrganizationStaff(organization);
  const isLeagueAdmin = useIsLeagueAdmin(league, organization);
  const isLeagueStaff = useIsLeagueStaff(league, organization);
  const canEditTournament = useCanEditTournament(league, organization);
  const canManageGames = useCanManageGames(league, organization);

  return useMemo(
    () => ({
      isSuperuser,
      isOrgAdmin,
      isOrgStaff,
      isLeagueAdmin,
      isLeagueStaff,
      canEditTournament,
      canManageGames,
    }),
    [
      isSuperuser,
      isOrgAdmin,
      isOrgStaff,
      isLeagueAdmin,
      isLeagueStaff,
      canEditTournament,
      canManageGames,
    ]
  );
}

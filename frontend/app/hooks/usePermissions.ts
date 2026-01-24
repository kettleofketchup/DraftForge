/**
 * Permission hooks for checking user access to organizations and leagues.
 *
 * These hooks provide a centralized way to check if the current user has
 * admin or staff access to organizations and leagues.
 *
 * Permission hierarchy:
 * - Organization Owner: Full control, cannot be removed
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
 * Check if the current user is the owner of the given organization.
 *
 * @param organization - The organization to check, or null/undefined
 * @returns true if user is org owner
 */
export function useIsOrganizationOwner(
  organization: OrganizationType | null | undefined
): boolean {
  const currentUser = useUserStore((state) => state.currentUser);

  return useMemo(() => {
    if (!currentUser?.pk || !organization) return false;

    // Check owner_id
    if (organization.owner_id === currentUser.pk) return true;

    // Check owner object
    if (organization.owner?.pk === currentUser.pk) return true;

    return false;
  }, [currentUser?.pk, organization]);
}

/**
 * Check if the current user is an admin of the given organization.
 * Owner is considered an admin.
 *
 * @param organization - The organization to check, or null/undefined
 * @returns true if user is org owner, org admin, or superuser
 */
export function useIsOrganizationAdmin(
  organization: OrganizationType | null | undefined
): boolean {
  const currentUser = useUserStore((state) => state.currentUser);
  const isOwner = useIsOrganizationOwner(organization);

  return useMemo(() => {
    if (!currentUser?.pk || !organization) return false;

    // Superuser has access to everything
    if (currentUser.is_staff) return true;

    // Owner is admin
    if (isOwner) return true;

    // Check admin_ids array (preferred, always available)
    if (organization.admin_ids?.includes(currentUser.pk)) return true;

    // Check admins array (may contain full user objects)
    if (organization.admins?.some((admin) => admin.pk === currentUser.pk)) {
      return true;
    }

    return false;
  }, [currentUser?.pk, currentUser?.is_staff, organization, isOwner]);
}

/**
 * Check if the current user has staff access to the given organization.
 * Staff access includes admins.
 *
 * @param organization - The organization to check, or null/undefined
 * @returns true if user is org owner, org admin, org staff, or superuser
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
 * League admin access includes admins of any linked organization.
 *
 * @param league - The league to check, or null/undefined
 * @param organizations - Array of parent organizations (for org admin check)
 * @returns true if user is league admin, admin of any linked org, or superuser
 */
export function useIsLeagueAdmin(
  league: LeagueType | null | undefined,
  organizations?: OrganizationType[] | OrganizationType | null
): boolean {
  const currentUser = useUserStore((state) => state.currentUser);

  return useMemo(() => {
    if (!currentUser?.pk || !league) return false;

    // Superuser has access to everything
    if (currentUser.is_staff) return true;

    // Check league-specific admin_ids array
    if (league.admin_ids?.includes(currentUser.pk)) return true;

    // Check league-specific admins array
    if (league.admins?.some((admin) => admin.pk === currentUser.pk)) {
      return true;
    }

    // Check if user is admin of any linked organization
    const orgs = Array.isArray(organizations)
      ? organizations
      : organizations
        ? [organizations]
        : league.organizations || [];

    for (const org of orgs) {
      // Check owner
      // @ts-expect-error - owner_id may exist on full org type
      if (org.owner_id === currentUser.pk) return true;
      // @ts-expect-error - owner may be an object
      if (org.owner?.pk === currentUser.pk) return true;

      // Check admin_ids
      // @ts-expect-error - admin_ids may exist on full org type
      if (org.admin_ids?.includes(currentUser.pk)) return true;

      // Check admins array
      // @ts-expect-error - admins may exist
      if (org.admins?.some((admin: { pk: number }) => admin.pk === currentUser.pk)) {
        return true;
      }
    }

    return false;
  }, [currentUser?.pk, currentUser?.is_staff, league, organizations]);
}

/**
 * Check if the current user has staff access to the given league.
 * Staff access includes league admins and organization staff.
 *
 * @param league - The league to check, or null/undefined
 * @param organizations - Array of parent organizations (for org staff check)
 * @returns true if user is league admin, league staff, org admin, org staff, or superuser
 */
export function useIsLeagueStaff(
  league: LeagueType | null | undefined,
  organizations?: OrganizationType[] | OrganizationType | null
): boolean {
  const currentUser = useUserStore((state) => state.currentUser);
  const isLeagueAdmin = useIsLeagueAdmin(league, organizations);

  return useMemo(() => {
    if (!currentUser?.pk || !league) return false;

    // League admins have staff access
    if (isLeagueAdmin) return true;

    // Check league-specific staff_ids array
    if (league.staff_ids?.includes(currentUser.pk)) return true;

    // Check league-specific staff array
    if (league.staff?.some((staff) => staff.pk === currentUser.pk)) {
      return true;
    }

    // Check if user is staff of any linked organization
    const orgs = Array.isArray(organizations)
      ? organizations
      : organizations
        ? [organizations]
        : league.organizations || [];

    for (const org of orgs) {
      // Check staff_ids
      // @ts-expect-error - staff_ids may exist on full org type
      if (org.staff_ids?.includes(currentUser.pk)) return true;

      // Check staff array
      // @ts-expect-error - staff may exist
      if (org.staff?.some((staff: { pk: number }) => staff.pk === currentUser.pk)) {
        return true;
      }
    }

    return false;
  }, [currentUser?.pk, league, isLeagueAdmin, organizations]);
}

/**
 * Check if the current user can edit a tournament.
 * Requires league admin access.
 *
 * @param league - The league the tournament belongs to
 * @param organizations - The parent organizations
 * @returns true if user can edit tournaments in this league
 */
export function useCanEditTournament(
  league: LeagueType | null | undefined,
  organizations?: OrganizationType[] | OrganizationType | null
): boolean {
  return useIsLeagueAdmin(league, organizations);
}

/**
 * Check if the current user can manage games (declare winners, link steam matches).
 * Requires league staff access.
 *
 * @param league - The league the game belongs to
 * @param organizations - The parent organizations
 * @returns true if user can manage games in this league
 */
export function useCanManageGames(
  league: LeagueType | null | undefined,
  organizations?: OrganizationType[] | OrganizationType | null
): boolean {
  return useIsLeagueStaff(league, organizations);
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
  const isOrgOwner = useIsOrganizationOwner(organization);
  const isOrgAdmin = useIsOrganizationAdmin(organization);
  const isOrgStaff = useIsOrganizationStaff(organization);
  const isLeagueAdmin = useIsLeagueAdmin(league, organization);
  const isLeagueStaff = useIsLeagueStaff(league, organization);
  const canEditTournament = useCanEditTournament(league, organization);
  const canManageGames = useCanManageGames(league, organization);

  return useMemo(
    () => ({
      isSuperuser,
      isOrgOwner,
      isOrgAdmin,
      isOrgStaff,
      isLeagueAdmin,
      isLeagueStaff,
      canEditTournament,
      canManageGames,
    }),
    [
      isSuperuser,
      isOrgOwner,
      isOrgAdmin,
      isOrgStaff,
      isLeagueAdmin,
      isLeagueStaff,
      canEditTournament,
      canManageGames,
    ]
  );
}

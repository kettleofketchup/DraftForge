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
 * Check if the current user is authenticated.
 *
 * Use this for gates that should be open to any signed-in account
 * regardless of role — e.g. creating an organization. Centralises the
 * "logged in" check so we have one place to evolve the definition
 * (email-verified, MFA, etc.).
 */
export function useIsLoggedIn(): boolean {
  const currentUser = useUserStore((state) => state.currentUser);
  return !!currentUser?.pk;
}

/**
 * Check if the current user is a site-level admin.
 *
 * Django models two flags here:
 *  - ``is_staff``: can log into the Django admin
 *  - ``is_superuser``: bypasses all permission checks
 *
 * Either grants site-level admin access in this app's permission
 * hierarchy (site admin > org admin/staff > league admin/staff), so we
 * accept either. Older callers that only checked ``is_staff`` are
 * picked up by this same function now.
 */
export function useIsSuperuser(): boolean {
  const currentUser = useUserStore((state) => state.currentUser);
  return !!(currentUser?.is_staff || currentUser?.is_superuser);
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
    if (!currentUser?.pk) return false;

    // Site admin (is_staff OR is_superuser) outranks every tier and
    // applies even when no organization is in scope (e.g. a tournament
    // with no league/org loaded yet).
    if (currentUser.is_staff || currentUser.is_superuser) return true;

    if (!organization) return false;

    // Owner is admin
    if (isOwner) return true;

    // Check admin_ids array (preferred, always available)
    if (organization.admin_ids?.includes(currentUser.pk)) return true;

    // Check admins array (may contain full user objects)
    if (organization.admins?.some((admin) => admin.pk === currentUser.pk)) {
      return true;
    }

    return false;
  }, [
    currentUser?.pk,
    currentUser?.is_staff,
    currentUser?.is_superuser,
    organization,
    isOwner,
  ]);
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
    if (!currentUser?.pk) return false;

    // Site admin (is_staff OR is_superuser) bypasses every tier — must
    // short-circuit before the !organization early return so a site
    // admin can still act on tournaments/games whose org isn't loaded.
    if (currentUser.is_staff || currentUser.is_superuser) return true;

    // Org admins have staff access (cascade through useIsOrganizationAdmin
    // also picks up site admins, but the explicit check above runs first).
    if (isOrgAdmin) return true;

    if (!organization) return false;

    // Check staff_ids array
    if (organization.staff_ids?.includes(currentUser.pk)) return true;

    // Check staff array (may contain full user objects)
    if (organization.staff?.some((staff) => staff.pk === currentUser.pk)) {
      return true;
    }

    return false;
  }, [
    currentUser?.pk,
    currentUser?.is_staff,
    currentUser?.is_superuser,
    organization,
    isOrgAdmin,
  ]);
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
    if (!currentUser?.pk) return false;

    // Site admin (is_staff OR is_superuser) outranks every tier — must
    // run before the !league guard so a server admin can still edit a
    // tournament whose league is null.
    if (currentUser.is_staff || currentUser.is_superuser) return true;

    // League-specific lookups only meaningful when a league is present.
    if (league) {
      if (league.admin_ids?.includes(currentUser.pk)) return true;
      if (league.admins?.some((admin) => admin.pk === currentUser.pk)) {
        return true;
      }
    }

    // Org-admin cascade: hierarchy puts org > league, so an org admin
    // of the linked org grants league-admin access. Works even with no
    // league, as long as ``organizations`` was passed in.
    const orgs = Array.isArray(organizations)
      ? organizations
      : organizations
        ? [organizations]
        : league?.organization
          ? [league.organization]
          : [];

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
  }, [
    currentUser?.pk,
    currentUser?.is_staff,
    currentUser?.is_superuser,
    league,
    organizations,
  ]);
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
    if (!currentUser?.pk) return false;

    // Site admin (is_staff OR is_superuser) outranks every tier — must
    // run before the !league guard. Without this, a server admin gets
    // gated out of tournaments with no league.
    if (currentUser.is_staff || currentUser.is_superuser) return true;

    // League admin cascade (also covers site admins via useIsLeagueAdmin,
    // but the direct check above already short-circuits faster).
    if (isLeagueAdmin) return true;

    // League-specific staff lookups only meaningful when a league is present.
    if (league) {
      if (league.staff_ids?.includes(currentUser.pk)) return true;
      if (league.staff?.some((staff) => staff.pk === currentUser.pk)) {
        return true;
      }
    }

    // Org-staff cascade: hierarchy puts org > league, so an org staffer
    // of the linked org grants league-staff access. Works even with no
    // league, as long as ``organizations`` was passed in.
    const orgs = Array.isArray(organizations)
      ? organizations
      : organizations
        ? [organizations]
        : league?.organization
          ? [league.organization]
          : [];

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
  }, [
    currentUser?.pk,
    currentUser?.is_staff,
    currentUser?.is_superuser,
    league,
    isLeagueAdmin,
    organizations,
  ]);
}

/**
 * Check if the current user can edit a tournament.
 *
 * Mirrors the backend's `can_edit_tournament` cascade: site staff →
 * org admin/staff → league admin/staff. Includes league staff.
 *
 * @param league - The league the tournament belongs to
 * @param organizations - The parent organizations
 * @returns true if user can edit tournaments in this league
 */
export function useCanEditTournament(
  league: LeagueType | null | undefined,
  organizations?: OrganizationType[] | OrganizationType | null
): boolean {
  return useIsLeagueStaff(league, organizations);
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
 * Check if the current user can create a tournament anywhere in the app.
 *
 * Used to gate the global Create Tournament entry point on
 * ``/tournaments/`` where no specific league is in scope yet — the
 * form's league picker and the backend's per-league check are the real
 * authorisation. Mirrors the backend's ``has_league_admin_access``
 * cascade: site admin OR admin of any organisation OR admin of any
 * league.
 */
export function useCanCreateAnyTournament(): boolean {
  const currentUser = useUserStore((state) => state.currentUser);

  return useMemo(() => {
    if (!currentUser?.pk) return false;
    if (currentUser.is_staff || currentUser.is_superuser) return true;
    if ((currentUser.admin_organization_ids?.length ?? 0) > 0) return true;
    if ((currentUser.admin_league_ids?.length ?? 0) > 0) return true;
    return false;
  }, [
    currentUser?.pk,
    currentUser?.is_staff,
    currentUser?.is_superuser,
    currentUser?.admin_organization_ids,
    currentUser?.admin_league_ids,
  ]);
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

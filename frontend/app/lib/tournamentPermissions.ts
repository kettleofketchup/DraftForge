import type { UserType } from '~/components/user/types';

export type PermUser =
  | Pick<
      UserType,
      | 'pk'
      | 'is_staff'
      | 'is_superuser'
      | 'admin_organization_ids'
      | 'staff_organization_ids'
      | 'admin_league_ids'
      | 'staff_league_ids'
    >
  | null
  | undefined;

export type LeagueRef = {
  pk?: number;
  organization?: { pk: number } | null;
  organization_id?: number;
};

const has = (ids: number[] | undefined, pk: number | null | undefined): boolean =>
  pk != null && (ids?.includes(pk) ?? false);

const leagueOrgPk = (league: LeagueRef): number | undefined =>
  league.organization?.pk ?? league.organization_id;

export function isSiteStaff(user: PermUser): boolean {
  return !!(user?.is_staff || user?.is_superuser);
}

export function canCreateTournament(user: PermUser): boolean {
  return !!user?.is_staff;
}

export function canEditTournament(
  user: PermUser,
  t: { leaguePk: number | null | undefined; leagueOrgPk: number | null | undefined },
): boolean {
  if (!user) return false;
  if (isSiteStaff(user)) return true;
  if (t.leaguePk == null) return false;
  return (
    has(user.admin_league_ids, t.leaguePk) ||
    has(user.staff_league_ids, t.leaguePk) ||
    has(user.admin_organization_ids, t.leagueOrgPk) ||
    has(user.staff_organization_ids, t.leagueOrgPk)
  );
}

export function canAdminLeague(user: PermUser, league: LeagueRef): boolean {
  if (!user) return false;
  if (isSiteStaff(user)) return true;
  return (
    has(user.admin_league_ids, league.pk) ||
    has(user.admin_organization_ids, leagueOrgPk(league))
  );
}

export function leagueOptionsFor<L extends LeagueRef>(
  user: PermUser,
  leagues: L[],
  opts: { currentLeague: L | null; eventOrgPk: number | null },
): { options: L[]; allowNone: boolean; locked: boolean } {
  const { currentLeague, eventOrgPk } = opts;
  const staff = isSiteStaff(user);

  if (currentLeague && !canAdminLeague(user, currentLeague)) {
    return { options: [currentLeague], allowNone: false, locked: true };
  }

  const options = leagues.filter(
    (l) =>
      (eventOrgPk == null || leagueOrgPk(l) === eventOrgPk) &&
      (staff || canAdminLeague(user, l)),
  );
  if (currentLeague && !options.some((l) => l.pk === currentLeague.pk)) {
    options.unshift(currentLeague);
  }
  return { options, allowNone: staff, locked: false };
}

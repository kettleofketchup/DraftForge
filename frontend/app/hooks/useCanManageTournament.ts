import { canEditTournament } from '~/lib/tournamentPermissions';
import { useUserStore } from '~/store/userStore';

export type TournamentScopeRef =
  | { league_pk?: number | null; organization_pk?: number | null }
  | null
  | undefined;

/**
 * Mirrors backend `can_edit_tournament`: site staff, admins/staff of the
 * league's org (the event's org when there is no league), or the league's
 * admins/staff. Reads the viewer's own role id lists, so it needs no fetch.
 */
export function useCanManageTournament(
  tournament: TournamentScopeRef,
): boolean {
  const currentUser = useUserStore((s) => s.currentUser);
  return canEditTournament(currentUser, {
    leaguePk: tournament?.league_pk,
    leagueOrgPk: tournament?.organization_pk,
  });
}

/** {@link useCanManageTournament} for the tournament in the user store. */
export function useCanManageCurrentTournament(): boolean {
  const tournament = useUserStore((s) => s.tournament);
  return useCanManageTournament(tournament);
}

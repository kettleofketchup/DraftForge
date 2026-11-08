export interface TournamentEditContext {
  organizationId: number | undefined;
  leagueId: number | undefined;
}

/** Org/league ids for edit scoping, read from the tournament only (never the org/league stores). */
export function tournamentEditContext(
  tournament: { organization_pk?: number | null; league_pk?: number | null } | null | undefined,
): TournamentEditContext {
  return {
    organizationId: tournament?.organization_pk ?? undefined,
    leagueId: tournament?.league_pk ?? undefined,
  };
}

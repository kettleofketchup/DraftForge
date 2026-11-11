interface CaptainedTeam {
  captain?: { pk?: number | null } | null;
}

export function isCaptainOf(
  teams: ReadonlyArray<CaptainedTeam> | null | undefined,
  userPk: number | null | undefined,
): boolean {
  if (userPk == null) return false;
  return (teams ?? []).some((t) => t.captain?.pk === userPk);
}

import type {
  ManagedTeam,
  OtherTeamSummary,
  RosterUser,
} from '~/components/api/teamManagementAPI';
import { teamStatusLabel } from '~/components/team/teamStatus';
import { DisplayName } from '~/components/user/avatar';

export type CandidateStatus = { label: string; disabled: boolean };

export type TeamCandidateStatus = 'member' | 'standin' | 'dropout';

export type TeamCandidateRow = {
  user: RosterUser;
  status: TeamCandidateStatus;
};

export const ON_ANOTHER_TEAM = 'On another team';

const teamPks = (team: OtherTeamSummary): number[] => [
  ...team.member_pks,
  ...team.dropin_pks,
];

/** pk → row label; a live other team wins over any eliminated one. */
export function candidateLabels(
  otherTeams: OtherTeamSummary[],
  otherTeamPks: number[],
): Map<number, CandidateStatus> {
  const labels = new Map<number, CandidateStatus>();
  for (const team of otherTeams) {
    if (team.placement != null) continue;
    for (const pk of teamPks(team)) {
      if (!labels.has(pk)) {
        labels.set(pk, { label: `On ${team.name}`, disabled: true });
      }
    }
  }
  for (const team of otherTeams) {
    if (team.placement == null) continue;
    for (const pk of teamPks(team)) {
      if (!labels.has(pk)) {
        labels.set(pk, {
          label: `${team.name} · ${teamStatusLabel(team.placement)}`,
          disabled: false,
        });
      }
    }
  }
  for (const pk of otherTeamPks) {
    if (!labels.get(pk)?.disabled) {
      labels.set(pk, { label: ON_ANOTHER_TEAM, disabled: true });
    }
  }
  return labels;
}

/** Members (minus the captain), stand-ins and dropouts of this team. */
export function teamCandidateRows(team: ManagedTeam): TeamCandidateRow[] {
  const captainPk = team.captain?.pk;
  return [
    ...team.members
      .filter((user) => user.pk !== captainPk)
      .map((user) => ({ user, status: 'member' as const })),
    ...team.dropin_members.map((user) => ({
      user,
      status: 'standin' as const,
    })),
    ...team.left_members
      .filter((user) => user.pk !== captainPk)
      .map((user) => ({ user, status: 'dropout' as const })),
  ];
}

/** Players of placed teams who are on no live team and not on this roster. */
export function freePlayers(
  otherTeams: OtherTeamSummary[],
  labels: Map<number, CandidateStatus>,
  excludePks: number[],
  tournamentUsers: RosterUser[],
): RosterUser[] {
  const byPk = new Map(tournamentUsers.map((user) => [user.pk, user]));
  const skip = new Set(excludePks);
  const seen = new Set<number>();
  const free: RosterUser[] = [];
  for (const team of otherTeams) {
    if (team.placement == null) continue;
    for (const pk of teamPks(team)) {
      if (seen.has(pk) || skip.has(pk) || labels.get(pk)?.disabled) continue;
      seen.add(pk);
      const user = byPk.get(pk);
      if (user) free.push(user);
    }
  }
  return free;
}

export function matchesQuery(user: RosterUser, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return [DisplayName(user), user.username, user.nickname].some((value) =>
    value?.toLowerCase().includes(needle),
  );
}

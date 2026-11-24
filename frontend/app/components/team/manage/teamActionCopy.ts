import type {
  ManagedTeam,
  RosterUser,
} from '~/components/api/teamManagementAPI';
import { teamStatus } from '~/components/team/teamStatus';
import { DisplayName } from '~/components/user/avatar';
import type { PendingTeamAction } from './pendingTeamAction';

export const CAPTAIN_CHANGE_WARNING =
  'Ready and connected state resets for any live hero draft this team is in.';

const isOn = (list: RosterUser[], user: RosterUser): boolean =>
  list.some((u) => u.pk === user.pk);

export const isMember = (team: ManagedTeam, user: RosterUser): boolean =>
  isOn(team.members, user);

/** Mirrors successor_after_removal: the deputy first, else highest MMR. */
export function captainSuccessionWarning(
  team: ManagedTeam,
  removedPk: number,
): string {
  const deputy = team.deputy_captain;
  const successor =
    deputy && deputy.pk !== removedPk && isMember(team, deputy)
      ? `${DisplayName(deputy)} (deputy) becomes captain and the deputy slot is left empty.`
      : 'With no deputy, the remaining member with the highest MMR becomes captain.';
  return `${CAPTAIN_CHANGE_WARNING} ${successor} To choose who captains, use Replace captain.`;
}

export function reseatCaptainSummary(
  team: ManagedTeam,
  captain: RosterUser,
): string {
  const name = DisplayName(captain);
  if (isOn(team.left_members, captain)) {
    return `Restore ${name} (dropout) as a member and keep them captain`;
  }
  if (isOn(team.dropin_members, captain)) {
    return `Move ${name} from stand-in to member and keep them captain`;
  }
  return `Add ${name} back to the members and keep them captain`;
}

export function reseatCaptainRequest(
  team: ManagedTeam,
  captain: RosterUser,
): PendingTeamAction {
  return {
    action: { kind: 'set_captain', user: captain },
    title: 'Reseat captain?',
    summary: reseatCaptainSummary(team, captain),
    confirmText: 'Reseat',
  };
}

export function ghostCaptainNote(team: ManagedTeam): string | null {
  const captain = team.captain;
  if (!captain || isMember(team, captain)) return null;
  return `${DisplayName(captain)} is not a member, so they will no longer be connected to this team.`;
}

export function setCaptainRequest(
  team: ManagedTeam,
  user: RosterUser,
): PendingTeamAction {
  const note = ghostCaptainNote(team);
  const line = `Make ${DisplayName(user)} captain of ${team.name}.`;
  return {
    action: { kind: 'set_captain', user },
    title: 'Change captain?',
    summary: note ? `${line} ${note}` : line,
    confirmText: 'Make captain',
    warning: CAPTAIN_CHANGE_WARNING,
  };
}

export function setDeputyRequest(
  team: ManagedTeam,
  user: RosterUser,
): PendingTeamAction {
  return {
    action: { kind: 'set_deputy', user },
    title: 'Change deputy?',
    summary: `Make ${DisplayName(user)} deputy captain of ${team.name}.`,
    confirmText: 'Make deputy',
  };
}

export function clearDeputyRequest(team: ManagedTeam): PendingTeamAction {
  const deputy = team.deputy_captain;
  return {
    action: { kind: 'set_deputy', user: null },
    title: 'Clear deputy?',
    summary: deputy
      ? `Remove ${DisplayName(deputy)} as deputy captain of ${team.name}.`
      : `Leave ${team.name} without a deputy captain.`,
    confirmText: 'Clear deputy',
  };
}

export function markDropoutRequest(
  team: ManagedTeam,
  user: RosterUser,
): PendingTeamAction {
  const isCaptain = team.captain?.pk === user.pk;
  return {
    action: { kind: 'mark_dropout', user },
    title: 'Mark dropout?',
    summary: `Mark ${DisplayName(user)} as a dropout of ${team.name}.`,
    confirmText: 'Mark dropout',
    destructive: true,
    ...(isCaptain ? { warning: captainSuccessionWarning(team, user.pk) } : {}),
  };
}

export function restoreMemberRequest(
  team: ManagedTeam,
  user: RosterUser,
): PendingTeamAction {
  return {
    action: { kind: 'restore_member', user },
    title: 'Restore member?',
    summary: `Restore ${DisplayName(user)} as a member of ${team.name}.`,
    confirmText: 'Restore',
  };
}

export function removeStandinRequest(
  team: ManagedTeam,
  user: RosterUser,
): PendingTeamAction {
  return {
    action: { kind: 'remove_standin', user },
    title: 'Remove stand-in?',
    summary: `Remove ${DisplayName(user)} from the stand-ins of ${team.name}.`,
    confirmText: 'Remove',
    destructive: true,
  };
}

export function subInRequest(
  team: ManagedTeam,
  standin: RosterUser,
): PendingTeamAction {
  return {
    action: { kind: 'sub_in', standin, replacing: null },
    title: 'Sub in stand-in?',
    summary: `Sub ${DisplayName(standin)} into ${team.name}.`,
    confirmText: 'Sub in',
    withReplacing: true,
    ...(team.captain
      ? {
          replacingCaptain: {
            pk: team.captain.pk,
            warning: captainSuccessionWarning(team, team.captain.pk),
          },
        }
      : {}),
  };
}

export function addStandinRequest(
  team: ManagedTeam,
  user: RosterUser,
): PendingTeamAction {
  return {
    action: { kind: 'add_standin', user },
    title: 'Add stand-in?',
    summary: `Add ${DisplayName(user)} as a stand-in for ${team.name}.`,
    confirmText: 'Add stand-in',
  };
}

function placedTeamOf(team: ManagedTeam, user: RosterUser) {
  return team.other_teams?.find(
    (t) =>
      t.placement != null &&
      (t.member_pks.includes(user.pk) || t.dropin_pks.includes(user.pk)),
  );
}

const onThisTeam = (team: ManagedTeam, user: RosterUser): boolean =>
  isOn(team.members, user) ||
  isOn(team.dropin_members, user) ||
  isOn(team.left_members, user);

export function replaceCaptainRequest(
  team: ManagedTeam,
  user: RosterUser,
): PendingTeamAction {
  const lines = [`${DisplayName(user)} becomes captain of ${team.name}.`];
  const placed = placedTeamOf(team, user);
  if (placed) {
    const status =
      teamStatus(placed.placement) === 'winner' ? 'winner' : 'eliminated';
    lines.push(
      `They stay listed on ${placed.name} (${status}); that team is not changed.`,
    );
  }
  if (
    team.tournament &&
    !team.tournament.users.includes(user.pk) &&
    !onThisTeam(team, user)
  ) {
    lines.push("They join the tournament's players.");
  }
  const outgoing =
    team.captain && team.captain.pk !== user.pk && isMember(team, team.captain)
      ? team.captain
      : null;
  return {
    action: { kind: 'replace_captain', user },
    title: 'Replace captain?',
    summary: lines.join(' '),
    confirmText: 'Replace captain',
    destructive: false,
    warning: CAPTAIN_CHANGE_WARNING,
    ...(outgoing ? { outgoingDropout: { name: DisplayName(outgoing) } } : {}),
  };
}

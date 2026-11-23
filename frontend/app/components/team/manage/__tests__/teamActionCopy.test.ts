import { describe, expect, it } from 'vitest';

import type {
  ManagedTeam,
  RosterUser,
} from '~/components/api/teamManagementAPI';
import { DisplayName } from '~/components/user/avatar';
import {
  CAPTAIN_CHANGE_WARNING,
  CAPTAIN_SUCCESSION_WARNING,
  markDropoutRequest,
  replaceCaptainRequest,
  setCaptainRequest,
  subInRequest,
} from '../teamActionCopy';
import { ghostCaptainTeam, managedTeam, people } from './fixtures';

const HINT = 'use Replace captain';

// managedTeam.other_teams lists "Fallen" (placement 3) with member 21.
const fallenPlayer: RosterUser = {
  ...people.outsider,
  pk: 21,
  username: 'fallen_cap',
  nickname: null,
};

const withTournamentUsers = (
  team: ManagedTeam,
  users: number[],
): ManagedTeam =>
  team.tournament
    ? { ...team, tournament: { ...team.tournament, users } }
    : team;

describe('CAPTAIN_SUCCESSION_WARNING', () => {
  it('extends the captain change warning with the Replace captain hint', () => {
    expect(CAPTAIN_SUCCESSION_WARNING).toBe(
      `${CAPTAIN_CHANGE_WARNING} The new captain is picked automatically (highest MMR). To choose who captains, use Replace captain.`,
    );
  });
});

describe('captain-dropping actions point to Replace captain', () => {
  it('sub in replacing the captain carries the hint', () => {
    const request = subInRequest(managedTeam, people.standin);
    expect(request.replacingCaptain?.pk).toBe(people.captain.pk);
    expect(request.replacingCaptain?.warning).toBe(CAPTAIN_SUCCESSION_WARNING);
  });

  it('mark dropout of the captain carries the hint', () => {
    expect(markDropoutRequest(managedTeam, people.captain).warning).toBe(
      CAPTAIN_SUCCESSION_WARNING,
    );
  });

  it('mark dropout of a non-captain has no hint', () => {
    expect(markDropoutRequest(managedTeam, people.member).warning).toBe(
      undefined,
    );
  });

  it('set captain keeps the plain warning', () => {
    const warning = setCaptainRequest(managedTeam, people.member).warning;
    expect(warning).toBe(CAPTAIN_CHANGE_WARNING);
    expect(String(warning)).not.toContain(HINT);
  });
});

describe('replaceCaptainRequest', () => {
  it('builds the confirmation for a member', () => {
    const request = replaceCaptainRequest(managedTeam, people.member);
    expect(request.action).toEqual({
      kind: 'replace_captain',
      user: people.member,
    });
    expect(request.title).toBe('Replace captain?');
    expect(request.confirmText).toBe('Replace captain');
    expect(request.destructive).toBe(false);
    expect(request.warning).toBe(CAPTAIN_CHANGE_WARNING);
    expect(request.summary).toBe(
      `${DisplayName(people.member)} becomes captain of ${managedTeam.name}.`,
    );
    expect(request.outgoingDropout).toEqual({
      name: DisplayName(people.captain),
    });
  });

  it('notes that an eliminated team is not changed', () => {
    const team = withTournamentUsers(managedTeam, [
      ...managedTeam.tournament!.users,
      fallenPlayer.pk,
    ]);
    expect(replaceCaptainRequest(team, fallenPlayer).summary).toBe(
      `${DisplayName(fallenPlayer)} becomes captain of ${team.name}. They stay listed on Fallen (eliminated); that team is not changed.`,
    );
  });

  it('notes that a user outside the tournament joins its players', () => {
    expect(managedTeam.tournament!.users).not.toContain(people.outsider.pk);
    expect(replaceCaptainRequest(managedTeam, people.outsider).summary).toBe(
      `${DisplayName(people.outsider)} becomes captain of ${managedTeam.name}. They join the tournament's players.`,
    );
  });

  it('ignores live other teams for the eliminated line', () => {
    const livePlayer = managedTeam.other_teams![0].member_pks[0];
    const user = { ...people.outsider, pk: livePlayer };
    expect(replaceCaptainRequest(managedTeam, user).summary).toBe(
      `${DisplayName(user)} becomes captain of ${managedTeam.name}.`,
    );
  });

  it('omits outgoingDropout when the captain is not a member', () => {
    const request = replaceCaptainRequest(
      ghostCaptainTeam,
      ghostCaptainTeam.members[0],
    );
    expect(request.outgoingDropout).toBeUndefined();
  });

  it('omits outgoingDropout when there is no captain', () => {
    const request = replaceCaptainRequest(
      { ...managedTeam, captain: null },
      people.member,
    );
    expect(request.outgoingDropout).toBeUndefined();
  });
});

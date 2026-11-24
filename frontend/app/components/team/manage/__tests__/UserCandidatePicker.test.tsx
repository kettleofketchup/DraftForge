// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  OtherTeamSummary,
  RosterUser,
} from '~/components/api/teamManagementAPI';
import type { OrganizationType } from '~/components/organization/schemas';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import {
  candidateLabels,
  freePlayers,
  teamCandidateRows,
} from '../candidateStatus';
import { UserCandidatePicker } from '../UserCandidatePicker';
import { managedTeam } from './fixtures';
import { ORG_PK, stubRadix } from './manageDialogHarness';

const axiosMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('~/components/api/axios', () => ({ default: axiosMock }));

vi.mock('~/lib/logger', () => ({
  getLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}));

const VIEWER = 50;

const org: OrganizationType = {
  pk: ORG_PK,
  name: 'Org',
  owner_id: 1,
  admin_ids: [],
  staff_ids: [VIEWER],
} as unknown as OrganizationType;

const user = (pk: number, username: string): RosterUser => ({
  pk,
  username,
});

const otherTeams: OtherTeamSummary[] = [
  {
    pk: 2,
    name: 'TM Alpha',
    placement: null,
    member_pks: [20, 30],
    dropin_pks: [],
  },
  {
    pk: 3,
    name: 'TM Fallen',
    placement: 4,
    member_pks: [21, 30, 31, 4],
    dropin_pks: [32],
  },
  { pk: 5, name: 'TM Champs', placement: 1, member_pks: [33], dropin_pks: [] },
];
const otherTeamPks = [20, 30];

const tournamentUsers = [
  user(20, 'alpha_player'),
  user(21, 'spooney'),
  user(30, 'dual_guy'),
  user(32, 'fallen_sub'),
  user(33, 'champ'),
];

const teamRows = teamCandidateRows(managedTeam);
const rosterPks = [
  ...managedTeam.members,
  ...managedTeam.dropin_members,
  ...managedTeam.left_members,
].map((u) => u.pk);

const searchResults = [
  { pk: 20, username: 'alpha_player', membership: 'org' },
  { pk: 21, username: 'spooney', membership: 'org' },
  { pk: 30, username: 'dual_guy', membership: 'org' },
  { pk: 40, username: 'randomer', membership: 'other_org' },
];

function renderPicker(
  props: Partial<Parameters<typeof UserCandidatePicker>[0]> = {},
) {
  const onPick = vi.fn();
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <UserCandidatePicker
        mode="captain"
        testIdPrefix="team-captain"
        organization={org}
        leaguePk={3}
        excludePks={rosterPks}
        otherTeamPks={otherTeamPks}
        otherTeams={otherTeams}
        teamRows={teamRows}
        tournamentUsers={tournamentUsers}
        onPick={onPick}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { onPick };
}

async function openPicker() {
  fireEvent.click(screen.getByRole('button', { name: /replace captain/i }));
  return screen.findByTestId('team-captain-search');
}

async function type(text: string) {
  const input = await openPicker();
  fireEvent.change(input, { target: { value: text } });
}

beforeAll(stubRadix);

beforeEach(() => {
  vi.clearAllMocks();
  axiosMock.get.mockReset();
  useUserStore.setState({
    currentUser: { pk: VIEWER, username: 'viewer' } as UserType,
  });
  axiosMock.get.mockResolvedValue({ data: searchResults });
});

describe('candidateLabels', () => {
  const labels = candidateLabels(otherTeams, otherTeamPks);

  it('disables a live-team player with "On <team>"', () => {
    expect(labels.get(20)).toEqual({ label: 'On TM Alpha', disabled: true });
  });

  it('enables an eliminated-team player with the placement label', () => {
    expect(labels.get(21)).toEqual({
      label: 'TM Fallen · Eliminated · 4th',
      disabled: false,
    });
    expect(labels.get(33)).toEqual({
      label: 'TM Champs · Winner',
      disabled: false,
    });
  });

  it('lets the live team win for a player on both', () => {
    expect(labels.get(30)).toEqual({ label: 'On TM Alpha', disabled: true });
  });

  it('falls back to "On another team" when other_teams is stale', () => {
    const stale = candidateLabels(otherTeams, [21, 99]);
    expect(stale.get(21)).toEqual({
      label: 'On another team',
      disabled: true,
    });
    expect(stale.get(99)).toEqual({
      label: 'On another team',
      disabled: true,
    });
  });
});

describe('teamCandidateRows', () => {
  it('lists members minus the captain, stand-ins and dropouts', () => {
    const captainPk = managedTeam.captain!.pk;
    expect(teamRows.map((r) => r.user.pk)).not.toContain(captainPk);
    expect(teamRows.map((r) => [r.user.pk, r.status])).toEqual([
      ...managedTeam.members
        .filter((u) => u.pk !== captainPk)
        .map((u) => [u.pk, 'member']),
      ...managedTeam.dropin_members.map((u) => [u.pk, 'standin']),
      ...managedTeam.left_members.map((u) => [u.pk, 'dropout']),
    ]);
  });
});

describe('freePlayers', () => {
  it('skips live-team players, this roster and unknown users', () => {
    const labels = candidateLabels(otherTeams, otherTeamPks);
    expect(
      freePlayers(otherTeams, labels, rosterPks, tournamentUsers).map(
        (u) => u.pk,
      ),
    ).toEqual([21, 32, 33]);
  });
});

describe('UserCandidatePicker (captain mode)', () => {
  it('shows this team and free players before any search', async () => {
    renderPicker();
    await openPicker();
    expect(screen.getByText('This team')).toBeTruthy();
    for (const { user: u } of teamRows) {
      expect(screen.getByTestId(`team-captain-team-row-${u.pk}`)).toBeTruthy();
    }
    expect(
      screen.queryByTestId(`team-captain-team-row-${managedTeam.captain!.pk}`),
    ).toBeNull();
    expect(screen.getByText('Free players (eliminated teams)')).toBeTruthy();
    expect(screen.getByTestId('team-captain-free-row-21')).toHaveTextContent(
      'TM Fallen · Eliminated · 4th',
    );
    expect(screen.getByTestId('team-captain-free-row-33')).toHaveTextContent(
      'TM Champs · Winner',
    );
    expect(screen.queryByTestId('team-captain-free-row-30')).toBeNull();
    expect(screen.queryByTestId('team-captain-free-row-31')).toBeNull();
    expect(screen.queryByTestId('team-captain-free-row-4')).toBeNull();
    expect(screen.queryByTestId('team-captain-free-row-20')).toBeNull();
  });

  it('shows roster badges on this team rows', async () => {
    renderPicker();
    await openPicker();
    const standin = managedTeam.dropin_members[0];
    const dropout = managedTeam.left_members[0];
    expect(
      screen.getByTestId(`team-captain-team-row-${standin.pk}`),
    ).toHaveTextContent('Stand-in');
    expect(
      screen.getByTestId(`team-captain-team-row-${dropout.pk}`),
    ).toHaveTextContent('Dropout');
  });

  it.each(['m', 'roster_m1'])(
    'keeps a member visible while typing %s',
    async (text) => {
      renderPicker();
      await type(text);
      expect(screen.getByTestId('team-captain-team-row-4')).toBeTruthy();
      expect(
        screen.queryByTestId(
          `team-captain-team-row-${managedTeam.dropin_members[0].pk}`,
        ),
      ).toBeNull();
      await new Promise((r) => setTimeout(r, 400));
      expect(screen.queryByText('No users found')).toBeNull();
    },
  );

  it('filters free players as the user types', async () => {
    renderPicker();
    await type('spoo');
    expect(screen.getByTestId('team-captain-free-row-21')).toBeTruthy();
    expect(screen.queryByTestId('team-captain-free-row-32')).toBeNull();
    await screen.findByTestId('team-captain-result-40');
    expect(screen.queryByTestId('team-captain-result-21')).toBeNull();
  });

  it('labels search results from other_teams', async () => {
    renderPicker();
    await type('zzz');
    const live = await screen.findByTestId('team-captain-result-20');
    expect(live).toHaveTextContent('On TM Alpha');
    expect(live).toHaveAttribute('aria-disabled', 'true');
    const both = screen.getByTestId('team-captain-result-30');
    expect(both).toHaveTextContent('On TM Alpha');
    expect(both).not.toHaveTextContent('Eliminated');
    expect(both).toHaveAttribute('aria-disabled', 'true');
    const free = screen.getByTestId('team-captain-result-21');
    expect(free).toHaveTextContent('TM Fallen · Eliminated · 4th');
    expect(free).not.toHaveAttribute('aria-disabled', 'true');
  });

  it('picks from this team and from free players', async () => {
    const { onPick } = renderPicker();
    await openPicker();
    fireEvent.click(screen.getByTestId('team-captain-free-row-21'));
    expect(onPick).toHaveBeenCalledWith(
      expect.objectContaining({ pk: 21, username: 'spooney' }),
    );
    await openPicker();
    fireEvent.click(screen.getByTestId('team-captain-team-row-4'));
    expect(onPick).toHaveBeenLastCalledWith(expect.objectContaining({ pk: 4 }));
  });

  it('does not pick a disabled search result', async () => {
    const { onPick } = renderPicker();
    await type('zzz');
    fireEvent.click(await screen.findByTestId('team-captain-result-30'));
    expect(onPick).not.toHaveBeenCalled();
  });

  it('can be opened from outside', async () => {
    const onOpenChange = vi.fn();
    renderPicker({ open: true, onOpenChange });
    expect(await screen.findByTestId('team-captain-search')).toBeTruthy();
    fireEvent.click(screen.getByTestId('team-captain-team-row-4'));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('shows no free players group in stand-in mode', async () => {
    renderPicker({ mode: 'standin', testIdPrefix: 'team-standin' });
    fireEvent.click(screen.getByRole('button', { name: /add stand-in/i }));
    await screen.findByTestId('team-standin-search');
    expect(screen.queryByText('Free players (eliminated teams)')).toBeNull();
  });
});

// @vitest-environment jsdom
import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { EditUserScope } from '~/components/user/userCard/editUserSchema';
import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
import type { UserEntry } from '~/store/userCacheTypes';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';
import { hasErrors } from './hasErrors';

const captured = vi.hoisted(
  () => [] as Array<{ user: { pk?: number }; scope: EditUserScope }>,
);

vi.mock('~/components/user/userCard/editModal', () => ({
  default: (props: { user: { pk?: number }; scope: EditUserScope }) => {
    captured.push({ user: props.user, scope: props.scope });
    return null;
  },
}));

window.matchMedia = (() => ({
  matches: true,
  addEventListener() {},
  removeEventListener() {},
})) as unknown as typeof window.matchMedia;

function Harness() {
  return hasErrors();
}

const entry: UserEntry = {
  pk: 10,
  username: 'incomplete',
  steam_account_id: null,
  orgData: { 8: { id: 77, mmr: 0, _fetchedAt: 0 } },
  leagueData: { 8: { id: 77, mmr: 0, _fetchedAt: 0 } },
  _fetchedAt: 0,
};

function setTournament(organization_pk: number | null, league_pk: number | null) {
  useUserStore.setState({
    tournament: { pk: 1, organization_pk, league_pk, users: [10] },
  } as never);
}

function setStores(orgPk: number, leaguePk: number) {
  useOrgStore.setState({ currentOrg: { pk: orgPk, name: 'O' } as OrganizationType });
  useLeagueStore.setState({
    currentLeague: { pk: leaguePk, name: 'L', organization: { pk: orgPk } } as LeagueType,
  });
}

function lastScope(): EditUserScope {
  const forUser = captured.filter((c) => c.user.pk === 10);
  expect(forUser.length).toBeGreaterThan(0);
  return forUser.at(-1)!.scope;
}

describe('hasErrors incomplete-profile edit scope', () => {
  beforeEach(() => {
    captured.length = 0;
    useUserStore.setState({
      tournament: {},
      currentUser: { pk: 1, username: 'admin', is_superuser: true, is_staff: true },
    } as never);
    useUserCacheStore.setState({ entities: { 10: entry } } as never);
    useOrgStore.setState({ currentOrg: null });
    useLeagueStore.setState({ currentLeague: null });
  });

  it('store org/league that do not match the tournament -> global', () => {
    setTournament(8, 8);
    setStores(9, 9);
    render(<Harness />);
    expect(lastScope().kind).toBe('global');
  });

  it('org-less tournament with stale stores -> global', () => {
    setTournament(null, null);
    setStores(9, 9);
    render(<Harness />);
    expect(lastScope().kind).toBe('global');
  });

  it('switching to an org-less tournament drops a stale store scope', () => {
    setTournament(8, 8);
    setStores(8, 8);
    const { rerender } = render(<Harness />);
    expect(lastScope().kind).not.toBe('global');

    act(() => setTournament(null, null));
    rerender(<Harness />);
    expect(lastScope().kind).toBe('global');
  });
});

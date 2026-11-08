// @vitest-environment jsdom
import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  dispatchPatch,
  resolveOrgUserLink,
  type EditUserScope,
} from '~/components/user/userCard/editUserSchema';
import type { UserClassType } from '~/components/user/types';
import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
import type { UserEntry } from '~/store/userCacheTypes';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';
import { hasErrors } from './hasErrors';

const captured = vi.hoisted(
  () => [] as Array<{ user: { pk?: number; orgUserPk?: number }; scope: EditUserScope }>,
);

const updateOrgUser = vi.hoisted(() => vi.fn());
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  updateOrgUser,
}));

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

function lastCapture() {
  const forUser = captured.filter((c) => c.user.pk === 10);
  expect(forUser.length).toBeGreaterThan(0);
  return forUser.at(-1)!;
}

function lastScope(): EditUserScope {
  return lastCapture().scope;
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

describe('hasErrors scope identity (finding 5)', () => {
  beforeEach(() => {
    captured.length = 0;
    useUserStore.setState({
      tournament: {},
      currentUser: { pk: 1, username: 'admin', is_superuser: true, is_staff: true },
    } as never);
    useUserCacheStore.setState({ entities: { 10: entry } } as never);
  });

  it('rerender without a store change passes the same scope object', () => {
    setTournament(8, 8);
    setStores(8, 8);
    const { rerender } = render(<Harness />);
    const first = lastScope();
    rerender(<Harness />);
    expect(captured.filter((c) => c.user.pk === 10).length).toBeGreaterThan(1);
    expect(lastScope()).toBe(first);
  });
});

describe('hasErrors edit user carries the scope-gating link (finding 4)', () => {
  const CTX = { organizationId: 8, leagueId: 8 };

  beforeEach(() => {
    captured.length = 0;
    updateOrgUser.mockReset();
    useUserStore.setState({
      tournament: {},
      currentUser: { pk: 1, username: 'admin', is_superuser: true, is_staff: true },
    } as never);
    useOrgStore.setState({ currentOrg: null });
    useLeagueStore.setState({ currentLeague: null });
  });

  function seedEntry(e: UserEntry) {
    useUserCacheStore.setState({ entities: { 10: e } } as never);
  }

  it('a leagueData-only link gives league scope with that link on the user', () => {
    seedEntry({ ...entry, orgData: {}, leagueData: { 8: { id: 41, mmr: 0, _fetchedAt: 0 } } });
    setTournament(8, 8);
    useLeagueStore.setState({
      currentLeague: { pk: 8, name: 'L', organization: { pk: 8 } } as LeagueType,
    });
    render(<Harness />);
    const { user, scope } = lastCapture();
    expect(scope.kind).toBe('league');
    expect(scope.kind === 'league' && scope.orgId).toBe(8);
    expect(user.orgUserPk).toBe(41);
  });

  const rows: Array<{ name: string; source: UserEntry; store: 'org' | 'league' | 'both' }> = [
    {
      name: 'flat link',
      source: { ...entry, orgData: {}, leagueData: {}, orgUserPk: 170 } as unknown as UserEntry,
      store: 'org',
    },
    {
      name: 'orgData link',
      source: { ...entry, orgData: { 8: { id: 171, mmr: 0, _fetchedAt: 0 } }, leagueData: {} },
      store: 'org',
    },
    {
      name: 'leagueData link',
      source: { ...entry, orgData: {}, leagueData: { 8: { id: 172, mmr: 0, _fetchedAt: 0 } } },
      store: 'league',
    },
    {
      name: 'no link',
      source: { ...entry, orgData: {}, leagueData: {} },
      store: 'both',
    },
  ];

  it.each(rows)('$name: edit user link matches the resolver', async ({ name, source, store }) => {
    seedEntry(source);
    setTournament(8, 8);
    if (store !== 'league') {
      useOrgStore.setState({ currentOrg: { pk: 8, name: 'O' } as OrganizationType });
    }
    if (store !== 'org') {
      useLeagueStore.setState({
        currentLeague: { pk: 8, name: 'L', organization: { pk: 8 } } as LeagueType,
      });
    }
    render(<Harness />);
    const { user, scope } = lastCapture();
    if (name === 'no link') {
      expect(scope.kind).toBe('global');
      return;
    }
    expect(scope.kind).not.toBe('global');
    const link = resolveOrgUserLink(source, CTX);
    expect(user.orgUserPk).toBe(link);
    updateOrgUser.mockResolvedValue({ pk: 10, username: 'incomplete' });
    await dispatchPatch(user as UserClassType, scope, { nickname: 'x' });
    expect(updateOrgUser).toHaveBeenCalledWith(8, link, { nickname: 'x' });
  });
});

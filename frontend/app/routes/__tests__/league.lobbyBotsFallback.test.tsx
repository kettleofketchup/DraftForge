// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
import type { UserType } from '~/components/user/types';
import { useOrgStore } from '~/store/orgStore';
import { useUserStore } from '~/store/userStore';
import { resetGameType } from '~/test-utils/gameType';
import LeaguePage from '../league';

const leagueState: { league: LeagueType | null } = { league: null };

vi.mock('~/components/league', () => ({
  useLeague: () => ({
    league: leagueState.league,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
  LeagueTabs: ({
    activeTab,
    canManageLobbyBots,
  }: {
    activeTab: string;
    canManageLobbyBots: boolean;
  }) => (
    <div
      data-testid="tabs-stub"
      data-active={activeTab}
      data-can-manage={String(canManageLobbyBots)}
    />
  ),
  EditLeagueModal: () => null,
}));
vi.mock('~/components/organization/hooks/useOrganization', () => ({
  useCurrentOrganization: () => undefined,
}));
vi.mock('~/hooks/useMemberAccess', () => ({
  useMemberAccess: () => ({ canView: false, settled: false }),
}));
vi.mock('~/hooks/usePageNav', () => ({ usePageNav: () => undefined }));

const ORG_PK = 7;
const ADMIN_PK = 11;
const OTHER_PK = 12;

const orgLeague = {
  pk: 3,
  name: 'Org League',
  organization: { pk: ORG_PK, name: 'Org' },
  admin_ids: [],
} as unknown as LeagueType;

const orglessLeague = {
  pk: 3,
  name: 'Solo League',
  organization: null,
  admin_ids: [ADMIN_PK],
} as unknown as LeagueType;

const fullOrg = (adminIds: number[]) =>
  ({
    pk: ORG_PK,
    name: 'Org',
    admin_ids: adminIds,
  }) as unknown as OrganizationType;

const user = (pk: number, extra: Partial<UserType> = {}) =>
  ({ pk, username: `u${pk}`, ...extra }) as UserType;

const setUser = (
  status: 'loading' | 'resolved',
  currentUser: UserType | null,
) =>
  act(() => {
    useUserStore.setState({
      currentUser: currentUser ?? ({} as UserType),
      currentUserStatus: status,
    } as never);
  });

const setOrg = (org: OrganizationType | null) =>
  act(() => {
    useOrgStore.setState({ currentOrg: org });
  });

const renderPage = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={['/leagues/3/lobby-bots']}>
        <Routes>
          <Route path="leagues/:leagueId/:tab?" element={<LeaguePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

const activeTab = () =>
  screen.getByTestId('tabs-stub').getAttribute('data-active');

beforeEach(() => {
  useUserStore.setState({
    tournaments: [],
    getTournaments: vi.fn(async () => {}),
    currentUser: {} as UserType,
    currentUserStatus: 'loading',
  } as never);
  useOrgStore.setState({ currentOrg: null });
});

afterEach(() => {
  cleanup();
  resetGameType();
  leagueState.league = null;
});

describe('LeaguePage lobby bots deep link (org league)', () => {
  beforeEach(() => {
    leagueState.league = orgLeague;
  });

  it('stays on lobby-bots while the org is loading', () => {
    renderPage();
    setUser('resolved', user(OTHER_PK));
    expect(activeTab()).toBe('lobby-bots');
  });

  it('falls back to info once the org loads and the user is not an admin', () => {
    renderPage();
    setUser('resolved', user(OTHER_PK));
    setOrg(fullOrg([ADMIN_PK]));
    expect(activeTab()).toBe('info');
  });

  it('stays for an org admin once the org loads', () => {
    renderPage();
    setUser('resolved', user(ADMIN_PK));
    setOrg(fullOrg([ADMIN_PK]));
    expect(activeTab()).toBe('lobby-bots');
    expect(
      screen.getByTestId('tabs-stub').getAttribute('data-can-manage'),
    ).toBe('true');
  });

  it('stays while the user is loading even with the org loaded', () => {
    renderPage();
    setOrg(fullOrg([ADMIN_PK]));
    expect(activeTab()).toBe('lobby-bots');
    setUser('resolved', user(OTHER_PK));
    expect(activeTab()).toBe('info');
  });
});

describe('LeaguePage lobby bots deep link (org-less league)', () => {
  beforeEach(() => {
    leagueState.league = orglessLeague;
  });

  it('stays on lobby-bots while the user is loading', () => {
    renderPage();
    expect(activeTab()).toBe('lobby-bots');
  });

  it('stays for a direct league admin', () => {
    renderPage();
    setUser('resolved', user(ADMIN_PK));
    expect(activeTab()).toBe('lobby-bots');
  });

  it('stays for site staff', () => {
    renderPage();
    setUser('resolved', user(OTHER_PK, { is_staff: true }));
    expect(activeTab()).toBe('lobby-bots');
  });

  it('falls back to info for a non-admin', () => {
    renderPage();
    setUser('resolved', user(OTHER_PK));
    expect(activeTab()).toBe('info');
  });
});

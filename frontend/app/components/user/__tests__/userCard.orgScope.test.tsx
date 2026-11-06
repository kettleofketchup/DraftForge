// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { UserCard } from '~/components/user/userCard';
import type { UserClassType } from '~/components/user/types';
import type { OrganizationType } from '~/components/organization/schemas';
import type { LeagueType } from '~/components/league/schemas';
import { resolveOrgUserLink } from '~/components/user/userCard/editUserSchema';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import type { UserEntry } from '~/store/userCacheTypes';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';

vi.mock('~/components/ui/shared-popover-context', () => ({
  useSharedPopoverActions: () => ({ openPlayerModal: vi.fn() }),
}));

const updateOrgUser = vi.hoisted(() => vi.fn());
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  updateOrgUser,
}));

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

beforeEach(() => {
  vi.clearAllMocks();
});

// FormDialog renders a Radix ScrollArea, which jsdom cannot satisfy.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

const ORG_PK = 5;

// Tournament players are plain hydrated users, not cache entries.
const tournamentUser = {
  pk: 42,
  username: 'signup',
  nickname: 'Signup',
  mmr: 4200,
  orgUserPk: 77,
} as UserClassType;

function renderCard(organizationId?: number) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <MemoryRouter>
          <UserCard user={tournamentUser} organizationId={organizationId} />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

describe('UserCard org-scoped edit for tournament players', () => {
  beforeEach(() => {
    useUserCacheStore.getState().reset?.();
    useUserStore.setState({
      currentUser: { pk: 1, username: 'admin', is_superuser: true, is_staff: true },
    } as never);
    useOrgStore.setState({
      currentOrg: { pk: ORG_PK, name: 'Org' } as OrganizationType,
    });
    useLeagueStore.setState({ currentLeague: null });
    useUserCacheStore.getState().upsert([tournamentUser], { orgId: ORG_PK });
  });

  it('shows the MMR field when the card has org context', () => {
    renderCard(ORG_PK);
    fireEvent.click(screen.getByTestId('edit-user-btn'));
    expect(screen.getByTestId('edit-user-mmr')).toHaveProperty('value', '4200');
  });

  it('reopens with the saved values after an org-scoped save', async () => {
    updateOrgUser.mockResolvedValue({ ...tournamentUser, nickname: 'Renamed' });
    renderCard(ORG_PK);
    fireEvent.click(screen.getByTestId('edit-user-btn'));
    fireEvent.change(screen.getByTestId('edit-user-nickname'), {
      target: { value: 'Renamed' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => expect(screen.queryByTestId('edit-user-nickname')).toBeNull());
    expect(updateOrgUser).toHaveBeenCalledWith(ORG_PK, 77, { nickname: 'Renamed' });

    fireEvent.click(screen.getByTestId('edit-user-btn'));
    expect(screen.getByTestId('edit-user-nickname')).toHaveProperty('value', 'Renamed');
  });

  it('hides the MMR field without org context', () => {
    renderCard(undefined);
    fireEvent.click(screen.getByTestId('edit-user-btn'));
    expect(screen.queryByTestId('edit-user-mmr')).toBeNull();
  });
});

describe('UserCard with a stale store org (finding 3)', () => {
  const STALE_ORG_PK = 9;
  const staleEntry = {
    pk: 43,
    username: 'stale',
    nickname: 'Stale',
    orgData: { [STALE_ORG_PK]: { id: 88, mmr: 3000, _fetchedAt: 0 } },
    leagueData: {},
    _fetchedAt: 0,
  } as UserEntry;

  function renderStale(organizationId?: number) {
    return render(
      <QueryClientProvider client={new QueryClient()}>
        <TooltipProvider>
          <MemoryRouter>
            <UserCard
              user={staleEntry as unknown as UserClassType}
              organizationId={organizationId}
            />
          </MemoryRouter>
        </TooltipProvider>
      </QueryClientProvider>,
    );
  }

  function viewer(superuser: boolean) {
    useUserStore.setState({
      currentUser: { pk: 1021, username: 'v', is_superuser: superuser, is_staff: false },
    } as never);
  }

  beforeEach(() => {
    useUserCacheStore.getState().reset?.();
    useOrgStore.setState({
      currentOrg: {
        pk: STALE_ORG_PK, name: 'Stale', staff_ids: [1021],
      } as unknown as OrganizationType,
    });
    useLeagueStore.setState({ currentLeague: null });
  });

  it('org staff of the stale org cannot edit in org 8; MMR error ring shows', () => {
    viewer(false);
    const { container } = renderStale(8);
    expect(screen.queryByTestId('edit-user-btn')).toBeNull();
    expect(container.querySelector('.animate-ping')).not.toBeNull();
  });

  it('org staff of the stale org cannot edit without org context; no error ring', () => {
    viewer(false);
    const { container } = renderStale(undefined);
    expect(screen.queryByTestId('edit-user-btn')).toBeNull();
    expect(container.querySelector('.animate-ping')).toBeNull();
  });

  it.each([8, undefined])('superuser in org %s gets global scope (no MMR field)', (orgId) => {
    viewer(true);
    renderStale(orgId);
    fireEvent.click(screen.getByTestId('edit-user-btn'));
    expect(screen.getByTestId('edit-user-nickname')).toBeTruthy();
    expect(screen.queryByTestId('edit-user-mmr')).toBeNull();
  });
});

function renderEntryCard(
  user: UserEntry | UserClassType,
  organizationId?: number,
  leagueId?: number,
) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <MemoryRouter>
          <UserCard
            user={user as unknown as UserClassType}
            organizationId={organizationId}
            leagueId={leagueId}
          />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

function seed(entry: UserEntry): UserEntry {
  useUserCacheStore.setState({ entities: { [entry.pk]: entry } } as never);
  return useUserCacheStore.getState().entities[entry.pk];
}

function setLeague(pk: number, orgPk: number) {
  useLeagueStore.setState({
    currentLeague: { pk, name: 'L', organization: { pk: orgPk } } as LeagueType,
  });
}

async function saveNickname(nickname: string) {
  fireEvent.click(screen.getByTestId('edit-user-btn'));
  fireEvent.change(screen.getByTestId('edit-user-nickname'), {
    target: { value: nickname },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
  await waitFor(() =>
    expect(
      updateOrgUser.mock.calls.length + vi.mocked(toast.error).mock.calls.length,
    ).toBeGreaterThan(0),
  );
}

describe('UserCard edit for cache entries (finding 4)', () => {
  const LEAGUE_PK = 3;

  beforeEach(() => {
    useUserCacheStore.getState().reset?.();
    useUserStore.setState({
      currentUser: { pk: 1, username: 'admin', is_superuser: true, is_staff: true },
    } as never);
    useOrgStore.setState({ currentOrg: null });
    useLeagueStore.setState({ currentLeague: null });
  });

  it('org scope shows the MMR field and reopens with the saved MMR', async () => {
    useOrgStore.setState({ currentOrg: { pk: ORG_PK, name: 'Org' } as OrganizationType });
    const entry = seed({
      pk: 50, username: 'org', nickname: 'Org',
      orgData: { [ORG_PK]: { id: 60, mmr: 3000, _fetchedAt: 0 } },
      leagueData: {}, _fetchedAt: 0,
    });
    updateOrgUser.mockResolvedValue({ pk: 50, username: 'org', mmr: 3500, orgUserPk: 60 });
    renderEntryCard(entry, ORG_PK);
    fireEvent.click(screen.getByTestId('edit-user-btn'));
    expect(screen.getByTestId('edit-user-mmr')).toHaveProperty('value', '3000');
    fireEvent.change(screen.getByTestId('edit-user-mmr'), { target: { value: '3500' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => expect(screen.queryByTestId('edit-user-mmr')).toBeNull());
    expect(updateOrgUser).toHaveBeenCalledWith(ORG_PK, 60, { mmr: 3500 });

    fireEvent.click(screen.getByTestId('edit-user-btn'));
    expect(screen.getByTestId('edit-user-mmr')).toHaveProperty('value', '3500');
  });

  it('league scope with an orgData link PATCHes the parent org and labels Org MMR', async () => {
    setLeague(LEAGUE_PK, ORG_PK);
    const entry = seed({
      pk: 51, username: 'lg', nickname: 'Lg',
      orgData: { [ORG_PK]: { id: 61, mmr: 2000, _fetchedAt: 0 } },
      leagueData: {}, _fetchedAt: 0,
    });
    updateOrgUser.mockResolvedValue({ pk: 51, username: 'lg', nickname: 'New Nick' });
    renderEntryCard(entry, ORG_PK, LEAGUE_PK);
    fireEvent.click(screen.getByTestId('edit-user-btn'));
    expect(screen.getByLabelText(/Org MMR/)).toBe(screen.getByTestId('edit-user-mmr'));
    fireEvent.change(screen.getByTestId('edit-user-nickname'), {
      target: { value: 'New Nick' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => expect(updateOrgUser).toHaveBeenCalled());
    expect(updateOrgUser).toHaveBeenCalledWith(ORG_PK, 61, { nickname: 'New Nick' });
  });

  it('a leagueData-only link opens league scope, does not prefill MMR, and saves', async () => {
    setLeague(LEAGUE_PK, ORG_PK);
    const entry = seed({
      pk: 52, username: 'lonly', nickname: 'Lonly',
      orgData: {},
      leagueData: { [LEAGUE_PK]: { id: 41, mmr: 1200, _fetchedAt: 0 } },
      _fetchedAt: 0,
    });
    updateOrgUser.mockResolvedValue({ pk: 52, username: 'lonly', nickname: 'New Nick' });
    renderEntryCard(entry, ORG_PK, LEAGUE_PK);
    fireEvent.click(screen.getByTestId('edit-user-btn'));
    expect(screen.getByTestId('edit-user-mmr')).toHaveProperty('value', '');
    fireEvent.change(screen.getByTestId('edit-user-nickname'), {
      target: { value: 'New Nick' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() =>
      expect(
        updateOrgUser.mock.calls.length + vi.mocked(toast.error).mock.calls.length,
      ).toBeGreaterThan(0),
    );
    expect(toast.error).not.toHaveBeenCalled();
    expect(updateOrgUser).toHaveBeenCalledWith(ORG_PK, 41, { nickname: 'New Nick' });
  });

  it('a leagueData link for a different league falls back to global scope', () => {
    setLeague(LEAGUE_PK, ORG_PK);
    const entry = seed({
      pk: 53, username: 'other', nickname: 'Other',
      orgData: {},
      leagueData: { 4: { id: 44, mmr: 1500, _fetchedAt: 0 } },
      _fetchedAt: 0,
    });
    renderEntryCard(entry, undefined, LEAGUE_PK);
    fireEvent.click(screen.getByTestId('edit-user-btn'));
    expect(screen.getByTestId('edit-user-nickname')).toBeTruthy();
    expect(screen.queryByTestId('edit-user-mmr')).toBeNull();
  });
});

describe('UserCard edit user carries the scope-gating link', () => {
  const CTX = { organizationId: 8, leagueId: 8 };
  type Row = {
    name: string;
    source: UserEntry | UserClassType;
    store: 'org' | 'league' | 'both';
  };
  const rows: Row[] = [
    {
      name: 'flat link',
      source: { pk: 70, username: 'flat', nickname: 'Flat', orgUserPk: 170 } as UserClassType,
      store: 'org',
    },
    {
      name: 'orgData link',
      source: {
        pk: 71, username: 'org', nickname: 'Org',
        orgData: { 8: { id: 171, mmr: 1000, _fetchedAt: 0 } }, leagueData: {}, _fetchedAt: 0,
      },
      store: 'org',
    },
    {
      name: 'leagueData link',
      source: {
        pk: 72, username: 'lg', nickname: 'Lg',
        orgData: {}, leagueData: { 8: { id: 172, mmr: 1000, _fetchedAt: 0 } }, _fetchedAt: 0,
      },
      store: 'league',
    },
  ];

  beforeEach(() => {
    useUserCacheStore.getState().reset?.();
    useUserStore.setState({
      currentUser: { pk: 1, username: 'admin', is_superuser: true, is_staff: true },
    } as never);
    useOrgStore.setState({ currentOrg: null });
    useLeagueStore.setState({ currentLeague: null });
  });

  function applyStore(store: Row['store']) {
    if (store !== 'league') {
      useOrgStore.setState({ currentOrg: { pk: 8, name: 'O' } as OrganizationType });
    }
    if (store !== 'org') setLeague(8, 8);
  }

  it.each(rows)('$name: PATCH uses the resolved link', async ({ source, store }) => {
    applyStore(store);
    const user = 'orgData' in source ? seed(source as UserEntry) : source;
    updateOrgUser.mockResolvedValue({ pk: source.pk, username: 'u', nickname: 'x' });
    renderEntryCard(user, CTX.organizationId, CTX.leagueId);
    await saveNickname('xx');
    expect(toast.error).not.toHaveBeenCalled();
    expect(updateOrgUser).toHaveBeenCalledWith(
      8,
      resolveOrgUserLink(source as UserEntry, CTX),
      { nickname: 'xx' },
    );
  });

  it('no link: global scope, no MMR field', () => {
    applyStore('both');
    const user = seed({
      pk: 73, username: 'none', nickname: 'None',
      orgData: {}, leagueData: {}, _fetchedAt: 0,
    });
    renderEntryCard(user, CTX.organizationId, CTX.leagueId);
    fireEvent.click(screen.getByTestId('edit-user-btn'));
    expect(screen.queryByTestId('edit-user-mmr')).toBeNull();
  });
});

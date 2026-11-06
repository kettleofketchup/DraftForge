// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { UserCard } from '~/components/user/userCard';
import type { UserClassType } from '~/components/user/types';
import type { OrganizationType } from '~/components/organization/schemas';
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

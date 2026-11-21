// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OrganizationType } from '~/components/organization/schemas';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserClassType } from '~/components/user/types';
import { UserCard } from '~/components/user/userCard';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';

const openPlayerModal = vi.hoisted(() => vi.fn());
vi.mock('~/components/ui/shared-popover-context', () => ({
  useSharedPopoverActions: () => ({ openPlayerModal }),
}));

const updateOrgUser = vi.hoisted(() => vi.fn());
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  updateOrgUser,
}));

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

const ORG_PK = 5;

function deadlockPlayer(): UserClassType {
  return {
    pk: 42,
    username: 'dl',
    nickname: 'Dl',
    mmr: 2500,
    mmr_game_type: 2,
    orgUserPk: 77,
  } as UserClassType;
}

function renderCard(user: UserClassType) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <MemoryRouter>
          <UserCard user={user} organizationId={ORG_PK} gameType={2} />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

describe('UserCard in a Deadlock tournament', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useUserCacheStore.getState().reset?.();
    useUserStore.setState({
      currentUser: {
        pk: 1,
        username: 'admin',
        is_superuser: true,
        is_staff: true,
      },
    } as never);
    useOrgStore.setState({
      currentOrg: { pk: ORG_PK, name: 'Org' } as OrganizationType,
    });
    useLeagueStore.setState({ currentLeague: null });
  });

  it('shows only the Deadlock tile and field', () => {
    const user = deadlockPlayer();
    useUserCacheStore.getState().upsert([user], { orgId: ORG_PK });
    renderCard(user);
    expect(screen.getByTestId('usercard-org-mmr-deadlock').textContent).toMatch(
      /Deadlock.*2500/,
    );
    expect(screen.queryByTestId('usercard-org-mmr-dota2')).toBeNull();
    fireEvent.click(screen.getByTestId('edit-user-btn'));
    expect(screen.getByTestId('edit-user-mmr-deadlock')).toHaveProperty(
      'value',
      '2500',
    );
    expect(screen.queryByTestId('edit-user-mmr')).toBeNull();
  });

  it('flags missing MMR for the tournament game only', () => {
    const user = { ...deadlockPlayer(), mmr: 0 } as UserClassType;
    useUserCacheStore.getState().upsert([user], { orgId: ORG_PK });
    renderCard(user);
    expect(screen.getByText('MMR: Not added')).toBeTruthy();
  });

  it('saves with ?game_type=2 and keeps the Deadlock mmr on the user', async () => {
    const user = deadlockPlayer();
    useUserCacheStore.getState().upsert([user], { orgId: ORG_PK });
    updateOrgUser.mockResolvedValue({
      ...user,
      mmr: 3000,
      mmr_game_type: 2,
      game_mmrs: { '1': 4200, '2': 3000 },
    });
    renderCard(user);
    fireEvent.click(screen.getByTestId('edit-user-btn'));
    fireEvent.change(screen.getByTestId('edit-user-mmr-deadlock'), {
      target: { value: '3000' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() =>
      expect(screen.queryByTestId('edit-user-mmr-deadlock')).toBeNull(),
    );
    expect(updateOrgUser).toHaveBeenCalledWith(
      ORG_PK,
      77,
      { game_mmrs: { 2: 3000 } },
      2,
    );
    expect(
      useUserCacheStore.getState().entities[42]?.orgData[ORG_PK]?.mmrs,
    ).toEqual({ 1: 4200, 2: 3000 });
    await waitFor(() =>
      expect(
        screen.getByTestId('usercard-org-mmr-deadlock').textContent,
      ).toContain('3000'),
    );
    fireEvent.click(screen.getByTestId('edit-user-btn'));
    expect(screen.getByTestId('edit-user-mmr-deadlock')).toHaveProperty(
      'value',
      '3000',
    );
  });

  it('opens the player modal with the tournament game', () => {
    renderCard(deadlockPlayer());
    fireEvent.click(screen.getByRole('button', { name: /View Profile/ }));
    expect(openPlayerModal).toHaveBeenCalledWith(
      expect.objectContaining({ pk: 42 }),
      expect.objectContaining({ organizationId: ORG_PK, gameType: 2 }),
    );
  });
});

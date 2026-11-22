// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GAME_TYPE, type GameTypeValue } from '~/components/game/constants';
import type { OrganizationType } from '~/components/organization/schemas';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserClassType } from '~/components/user/types';
import { UserCard } from '~/components/user/userCard';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';
import { resetGameType, withGameType } from '~/test-utils/gameType';

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

const LEAGUE_PK = 9;

function renderCard(
  user: UserClassType,
  opts: { gameType?: GameTypeValue; leagueId?: number } = {},
) {
  const { gameType = GAME_TYPE.DEADLOCK, leagueId } = opts;
  withGameType(gameType);
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <MemoryRouter>
          <UserCard user={user} organizationId={ORG_PK} leagueId={leagueId} />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

describe('UserCard in a Deadlock tournament', () => {
  afterEach(resetGameType);

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

  it('hides the Dota-seeded league MMR tile', () => {
    const user = { ...deadlockPlayer(), league_mmr: 2000 } as UserClassType;
    renderCard(user, { leagueId: LEAGUE_PK });
    expect(screen.getByTestId('usercard-org-mmr-deadlock')).toBeTruthy();
    expect(screen.queryByText('League MMR')).toBeNull();
  });

  it('keeps the league MMR tile in a Dota tournament', () => {
    const user = {
      ...deadlockPlayer(),
      mmr: 4200,
      mmr_game_type: 1,
      league_mmr: 2000,
    } as UserClassType;
    renderCard(user, { gameType: GAME_TYPE.DOTA2, leagueId: LEAGUE_PK });
    expect(screen.getByText('League MMR').parentElement?.textContent).toContain(
      '2000',
    );
  });

  it('opens the player modal, which reads the page game itself', () => {
    renderCard(deadlockPlayer());
    fireEvent.click(screen.getByRole('button', { name: /View Profile/ }));
    expect(openPlayerModal).toHaveBeenCalledWith(
      expect.objectContaining({ pk: 42 }),
      expect.objectContaining({ organizationId: ORG_PK }),
    );
    expect(openPlayerModal.mock.calls[0][1]).not.toHaveProperty('gameType');
  });
});

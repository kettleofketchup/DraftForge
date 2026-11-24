// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserClassType } from '~/components/user/types';
import { UserCard } from '~/components/user/userCard';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { useUserStore } from '~/store/userStore';

const openPlayerModal = vi.hoisted(() => vi.fn());
vi.mock('~/components/ui/shared-popover-context', () => ({
  useSharedPopoverActions: () => ({ openPlayerModal }),
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const player = {
  pk: 42,
  username: 'alice',
  nickname: 'Alice',
  steam_account_id: 123456,
  steam_account_verified: false,
  steam_account_exists_checked: false,
} as UserClassType;

function renderCard(props: Partial<ComponentProps<typeof UserCard>>) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <MemoryRouter>
          <UserCard user={player} compact {...props} />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useUserStore.setState({
    currentUser: { pk: 1, username: 'admin', is_staff: true },
  } as never);
  useOrgStore.setState({ currentOrg: null });
  useLeagueStore.setState({ currentLeague: null });
});

afterEach(() => cleanup());

describe('UserCard Friend ID verification', () => {
  it('shows no badge by default', () => {
    renderCard({});
    expect(screen.getByText('123456')).toBeTruthy();
    expect(screen.queryByTestId('steam-verification-unverified')).toBeNull();
  });

  it('admin list badges the Friend ID without an inline Verify', () => {
    renderCard({ showSteamVerification: true });
    const badge = screen.getByTestId('steam-verification-unverified');
    expect(badge.getAttribute('title')).toBe(
      'Self-reported. Not checked against Steam.',
    );
    expect(screen.queryByTestId('steam-verify-button')).toBeNull();
  });

  it('clicking the badge opens the player modal', () => {
    renderCard({ showSteamVerification: true });
    fireEvent.click(screen.getByTestId('steam-verification-unverified'));
    expect(openPlayerModal).toHaveBeenCalledWith(
      player,
      expect.objectContaining({}),
    );
  });

  it('uses onSteamBadgeClick when given', () => {
    const onSteamBadgeClick = vi.fn();
    renderCard({ showSteamVerification: true, onSteamBadgeClick });
    fireEvent.click(screen.getByTestId('steam-verification-unverified'));
    expect(onSteamBadgeClick).toHaveBeenCalledWith(42);
    expect(openPlayerModal).not.toHaveBeenCalled();
  });
});

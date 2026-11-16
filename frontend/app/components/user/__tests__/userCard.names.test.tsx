// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserClassType } from '~/components/user/types';
import { UserCard } from '~/components/user/userCard';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';

vi.mock('~/components/ui/shared-popover-context', () => ({
  useSharedPopoverActions: () => ({ openPlayerModal: vi.fn() }),
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  updateOrgUser: vi.fn(),
}));

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const dragon = {
  pk: 1,
  username: 'dc_handle',
  discordNickname: 'GwaihirTheWindlord',
} as UserClassType;

function renderCard(organizationId?: number) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <MemoryRouter>
          <UserCard user={dragon} organizationId={organizationId} />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useUserCacheStore.getState().reset();
  useUserStore.setState({
    currentUser: { pk: 2, username: 'viewer' },
  } as never);
  useOrgStore.setState({ currentOrg: null });
  useLeagueStore.setState({ currentLeague: null });
  act(() =>
    useUserCacheStore
      .getState()
      .upsert({ ...dragon, guildNickname: 'DragonClaw' } as never, {
        orgId: 7,
      }),
  );
});

describe('UserCard names', () => {
  it('shows the server nickname in org context', () => {
    renderCard(7);
    expect(screen.getByTestId('usercard-display-name').textContent).toBe(
      'DragonClaw',
    );
  });

  it('shows the global name without org context', () => {
    renderCard(undefined);
    expect(screen.getByTestId('usercard-display-name').textContent).toBe(
      'GwaihirTheWindlord',
    );
  });

  it('shows @username under a name that differs from it', () => {
    renderCard(7);
    expect(screen.getByText('@dc_handle')).toBeTruthy();
    expect(screen.queryByText('Nickname')).toBeNull();
  });
});

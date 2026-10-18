// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { UserCard } from '~/components/user/userCard';
import type { UserClassType } from '~/components/user/types';
import type { OrganizationType } from '~/components/organization/schemas';
import { useOrgStore } from '~/store/orgStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';

vi.mock('~/components/ui/shared-popover-context', () => ({
  useSharedPopoverActions: () => ({ openPlayerModal: vi.fn() }),
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
    useUserCacheStore.getState().upsert([tournamentUser], { orgId: ORG_PK });
  });

  it('shows the MMR field when the card has org context', () => {
    renderCard(ORG_PK);
    fireEvent.click(screen.getByTestId('edit-user-btn'));
    expect(screen.getByTestId('edit-user-mmr')).toHaveProperty('value', '4200');
  });

  it('hides the MMR field without org context', () => {
    renderCard(undefined);
    fireEvent.click(screen.getByTestId('edit-user-btn'));
    expect(screen.queryByTestId('edit-user-mmr')).toBeNull();
  });
});

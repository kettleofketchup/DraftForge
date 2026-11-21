// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { OrganizationType } from '~/components/organization/schemas';
import type { TournamentType } from '~/components/tournament/types';
import type { PlayerModalContext } from '~/components/ui/shared-popover-context';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import type { EditUserScope } from '~/components/user/userCard/editUserSchema';
import { useOrgStore } from '~/store/orgStore';
import { useUserStore } from '~/store/userStore';
import { PlayerModal } from '../PlayerModal';

const modalCtx = vi.hoisted(() => ({ value: {} as PlayerModalContext }));
const scopes = vi.hoisted(() => ({ seen: [] as EditUserScope[] }));

vi.mock('~/components/ui/shared-popover-context', () => ({
  useSharedPopover: () => ({
    playerModalState: { player: null, open: true, context: modalCtx.value },
  }),
  useSharedPopoverActions: () => ({
    showPlayerPopover: vi.fn(),
    hidePopover: vi.fn(),
    openPlayerModal: vi.fn(),
    openTeamModal: vi.fn(),
  }),
}));

vi.mock('~/components/user/userCard/editModal', () => ({
  default: ({ scope }: { scope: EditUserScope }) => {
    scopes.seen.push(scope);
    return null;
  },
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  fetchUser: vi.fn(async () => player),
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

const player = { pk: 42, username: 'alice', nickname: 'Alice' } as UserType;
const org = { pk: 3, name: 'Org' } as OrganizationType;

function renderModal() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <TooltipProvider>
          <PlayerModal
            player={player}
            open
            onOpenChange={vi.fn()}
            organizationId={3}
          />
        </TooltipProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  scopes.seen = [];
  modalCtx.value = { organizationId: 3 };
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response('{}', {
      status: 404,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
  useOrgStore.setState({ currentOrg: org });
  useUserStore.setState({
    currentUser: { pk: 1, username: 'admin', is_staff: true } as UserType,
  });
});

afterEach(() => {
  useUserStore.setState({ tournament: {} as TournamentType });
  vi.restoreAllMocks();
});

describe('PlayerModal org MMR game', () => {
  it('carries the Deadlock tournament game into the org edit scope', async () => {
    useUserStore.setState({
      tournament: { pk: 9, organization_pk: 3, game_type: 2 } as TournamentType,
    });
    renderModal();
    await waitFor(() => expect(scopes.seen.length).toBeGreaterThan(0));
    expect(scopes.seen.at(-1)).toMatchObject({ kind: 'org', gameType: 2 });
  });

  it('leaves the game unset outside a tournament of that org', async () => {
    useUserStore.setState({
      tournament: {
        pk: 9,
        organization_pk: 99,
        game_type: 2,
      } as TournamentType,
    });
    renderModal();
    await waitFor(() => expect(scopes.seen.length).toBeGreaterThan(0));
    expect(scopes.seen.at(-1)).toEqual({ kind: 'org', organization: org });
  });
});

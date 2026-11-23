// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { LeagueType } from '~/components/league/schemas';
import { SharedPopoverProvider } from '~/components/ui/shared-popover-context';
import { SharedPopoverRenderer } from '~/components/ui/shared-popover-renderer';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import type { UserEntry } from '~/store/userCacheTypes';
import { useUserStore } from '~/store/userStore';
import { PlayerPopoverTrigger } from '../PlayerPopoverTrigger';

const api = vi.hoisted(() => ({ fetchUser: vi.fn() }));
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  fetchUser: api.fetchUser,
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('~/components/player/PlayerLeagueSummary', () => ({
  PlayerLeagueSummary: () => null,
}));
vi.mock('~/components/team/TeamModal', () => ({ TeamModal: () => null }));
vi.mock('~/components/team/TeamPopoverContent', () => ({
  TeamPopoverContent: () => null,
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

const ORG_PK = 3;
const LEAGUE_PK = 10;
const player = { pk: 42, username: 'alice', nickname: 'Alice' } as UserType;

function openOnLeaguePage(currentUser: Partial<UserType>) {
  useUserStore.setState({
    currentUser: { pk: 1, username: 'me', ...currentUser } as UserType,
  });
  render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient()}>
        <TooltipProvider>
          <SharedPopoverProvider>
            <PlayerPopoverTrigger player={player}>open</PlayerPopoverTrigger>
            <SharedPopoverRenderer />
          </SharedPopoverProvider>
        </TooltipProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  fireEvent.click(
    screen.getByRole('button', { name: 'View profile for Alice' }),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchUser.mockResolvedValue(player);
  useUserCacheStore.setState({
    entities: {
      42: {
        ...player,
        orgData: { [ORG_PK]: { id: 142, mmrs: {}, _fetchedAt: 0 } },
        leagueData: {},
        _fetchedAt: 0,
      } as UserEntry,
    },
  } as never);
  useOrgStore.setState({ currentOrg: null });
  useLeagueStore.setState({
    currentLeague: {
      pk: LEAGUE_PK,
      name: 'League',
      organization: { pk: ORG_PK },
    } as unknown as LeagueType,
  });
});

afterEach(async () => {
  cleanup();
  await new Promise((resolve) => setTimeout(resolve, 0));
  useLeagueStore.setState({ currentLeague: null });
});

describe('PlayerModal edit button for org staff', () => {
  it('shows edit to staff of the league parent org', async () => {
    openOnLeaguePage({ staff_organization_ids: [ORG_PK] });
    expect(await screen.findByTestId('edit-user-btn')).toBeTruthy();
  });

  it('hides edit from a user with no org role', async () => {
    openOnLeaguePage({});
    await screen.findByText('alice');
    expect(screen.queryByTestId('edit-user-btn')).toBeNull();
  });
});

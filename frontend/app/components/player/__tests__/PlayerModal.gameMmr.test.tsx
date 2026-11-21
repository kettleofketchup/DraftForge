// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { GameTypeValue } from '~/components/game/constants';
import type { OrganizationType } from '~/components/organization/schemas';
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

const api = vi.hoisted(() => ({
  fetchUser: vi.fn(),
  updateOrgUser: vi.fn(),
}));
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  fetchUser: api.fetchUser,
  updateOrgUser: api.updateOrgUser,
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
const player = { pk: 42, username: 'alice', nickname: 'Alice' } as UserType;

function seedEntry(mmrs: Partial<Record<GameTypeValue, number>>) {
  useUserCacheStore.setState({
    entities: {
      42: {
        ...player,
        orgData: { [ORG_PK]: { id: 142, mmrs, _fetchedAt: 0 } },
        leagueData: {},
        _fetchedAt: 0,
      } as UserEntry,
    },
  } as never);
}

function openFromTrigger(gameType?: GameTypeValue) {
  render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient()}>
        <TooltipProvider>
          <SharedPopoverProvider>
            <PlayerPopoverTrigger player={player} gameType={gameType}>
              open
            </PlayerPopoverTrigger>
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
  useUserCacheStore.getState().reset?.();
  useOrgStore.setState({
    currentOrg: { pk: ORG_PK, name: 'Org' } as OrganizationType,
  });
  useLeagueStore.setState({ currentLeague: null });
  useUserStore.setState({
    currentUser: {
      pk: 1,
      username: 'admin',
      is_staff: true,
      is_superuser: true,
    } as UserType,
  });
});

afterEach(async () => {
  cleanup();
  await new Promise((resolve) => setTimeout(resolve, 0));
  useOrgStore.setState({ currentOrg: null });
});

describe('PlayerModal per-game org MMR', () => {
  it('org scope shows one line per cached game', async () => {
    seedEntry({ 1: 4200, 2: 2500 });
    openFromTrigger();
    expect(
      (await screen.findByTestId('player-modal-org-mmr-dota2')).textContent,
    ).toContain('4200');
    expect(
      screen.getByTestId('player-modal-org-mmr-deadlock').textContent,
    ).toContain('2500');
  });

  it('org scope shows no line for a game the cache never received', async () => {
    seedEntry({ 2: 2500 });
    openFromTrigger();
    expect(
      (await screen.findByTestId('player-modal-org-mmr-deadlock')).textContent,
    ).toContain('2500');
    expect(screen.queryByTestId('player-modal-org-mmr-dota2')).toBeNull();
  });

  it('a Deadlock context shows and edits only the Deadlock value', async () => {
    seedEntry({ 1: 4200, 2: 2500 });
    api.updateOrgUser.mockResolvedValue({
      ...player,
      orgUserPk: 142,
      mmr: 3000,
      mmr_game_type: 2,
      game_mmrs: { '1': 4200, '2': 3000 },
    });
    openFromTrigger(2);
    expect(
      (await screen.findByTestId('player-modal-org-mmr-deadlock')).textContent,
    ).toContain('2500');
    expect(screen.queryByTestId('player-modal-org-mmr-dota2')).toBeNull();

    fireEvent.click(await screen.findByTestId('edit-user-btn'));
    expect(screen.queryByTestId('edit-user-mmr')).toBeNull();
    fireEvent.change(screen.getByTestId('edit-user-mmr-deadlock'), {
      target: { value: '3000' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => expect(api.updateOrgUser).toHaveBeenCalled());
    expect(api.updateOrgUser).toHaveBeenCalledWith(
      ORG_PK,
      142,
      { game_mmrs: { 2: 3000 } },
      2,
    );
  });
});

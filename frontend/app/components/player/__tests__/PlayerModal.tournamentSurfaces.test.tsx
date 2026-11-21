// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GAME_TYPE } from '~/components/game/constants';
import type { OrganizationType } from '~/components/organization/schemas';
import { TeamModal } from '~/components/team/TeamModal';
import { DraftTable } from '~/components/teamdraft/roundView/draftTable';
import type { TeamType, TournamentType } from '~/components/tournament/types';
import { SharedPopoverProvider } from '~/components/ui/shared-popover-context';
import { SharedPopoverRenderer } from '~/components/ui/shared-popover-renderer';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import type { UserEntry } from '~/store/userCacheTypes';
import { useUserStore } from '~/store/userStore';

const api = vi.hoisted(() => ({ fetchUser: vi.fn() }));
vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  fetchUser: api.fetchUser,
}));
vi.mock('~/components/api/axios', () => ({
  default: { get: () => new Promise(() => {}), post: vi.fn() },
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('~/components/player/PlayerLeagueSummary', () => ({
  PlayerLeagueSummary: () => null,
}));
vi.mock('~/components/user/positions', () => ({ RolePositions: () => null }));
vi.mock('~/components/teamdraft/buttons/choosePlayerButtons', () => ({
  ChoosePlayerButton: () => null,
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

const ORG_PK = 3;
const TOURNAMENT_PK = 77;
const player = {
  pk: 42,
  username: 'alice',
  nickname: 'Alice',
  mmr: 2500,
  mmr_game_type: GAME_TYPE.DEADLOCK,
} as UserType;

const team = {
  pk: 9,
  name: 'Team A',
  captain: null,
  members: [player],
  tournament: TOURNAMENT_PK,
} as unknown as TeamType;

function harness(children: ReactNode) {
  render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient()}>
        <TooltipProvider>
          <SharedPopoverProvider>
            {children}
            <SharedPopoverRenderer />
          </SharedPopoverProvider>
        </TooltipProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

async function expectDeadlockOnlyEdit(scope: HTMLElement) {
  fireEvent.click(
    within(scope).getByRole('button', { name: 'View profile for Alice' }),
  );
  expect(
    (await screen.findByTestId('player-modal-org-mmr-deadlock')).textContent,
  ).toContain('2500');
  expect(screen.queryByTestId('player-modal-org-mmr-dota2')).toBeNull();
  fireEvent.click(await screen.findByTestId('edit-user-btn'));
  expect(await screen.findByTestId('edit-user-mmr-deadlock')).toBeTruthy();
  expect(screen.queryByTestId('edit-user-mmr')).toBeNull();
}

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchUser.mockResolvedValue(player);
  useUserCacheStore.getState().reset?.();
  useUserCacheStore.setState({
    entities: {
      42: {
        ...player,
        orgData: {
          [ORG_PK]: {
            id: 142,
            mmrs: { [GAME_TYPE.DEADLOCK]: 2500 },
            _fetchedAt: 0,
          },
        },
        leagueData: {},
        _fetchedAt: 0,
      } as UserEntry,
    },
  } as never);
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
    tournament: {
      pk: TOURNAMENT_PK,
      organization_pk: ORG_PK,
      game_type: GAME_TYPE.DEADLOCK,
      teams: [team],
      draft: { users_remaining: [player] },
    } as unknown as TournamentType,
    draft: { users_remaining: [player] } as never,
  });
});

afterEach(() => {
  useOrgStore.setState({ currentOrg: null });
  useUserStore.setState({ tournament: null as never, draft: null as never });
});

describe('PlayerModal opened from Deadlock tournament surfaces', () => {
  it('draft table edits only the Deadlock org MMR', async () => {
    harness(
      <div data-testid="surface">
        <DraftTable />
      </div>,
    );
    await expectDeadlockOnlyEdit(screen.getByTestId('surface'));
  });

  it('team modal edits only the Deadlock org MMR', async () => {
    harness(<TeamModal team={team} open onOpenChange={() => {}} />);
    await expectDeadlockOnlyEdit(screen.getByTestId('team-modal'));
  });
});

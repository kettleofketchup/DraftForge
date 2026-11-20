// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { managedTeam } from '~/components/team/manage/__tests__/fixtures';
import {
  requestRowAction,
  routeGets,
  stubRadix,
} from '~/components/team/manage/__tests__/manageDialogHarness';
import type { TeamType, TournamentType } from '~/components/tournament/types';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import {
  SharedPopoverProvider,
  useSharedPopoverActions,
} from '../shared-popover-context';
import { SharedPopoverRenderer } from '../shared-popover-renderer';

const axiosMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('~/components/api/axios', () => ({ default: axiosMock }));
vi.mock('~/components/user/positions', () => ({ RolePositions: () => null }));
vi.mock('~/components/player/PlayerModal', () => ({ PlayerModal: () => null }));

const user = (pk: number, username: string) =>
  ({ pk, username }) as unknown as UserType;

const snapshot = (overrides: Partial<TeamType> = {}): TeamType =>
  ({
    pk: 1,
    name: 'Rostered',
    captain: user(2, 'roster_c'),
    deputy_captain: user(3, 'roster_d'),
    members: [user(2, 'roster_c'), user(3, 'roster_d'), user(4, 'roster_m1')],
    dropin_members: [],
    left_members: [],
    ...overrides,
  }) as unknown as TeamType;

let actions: ReturnType<typeof useSharedPopoverActions>;
function CaptureActions() {
  actions = useSharedPopoverActions();
  return null;
}

function renderRenderer() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <TooltipProvider>
          <SharedPopoverProvider>
            <CaptureActions />
            <SharedPopoverRenderer />
          </SharedPopoverProvider>
        </TooltipProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const setStoreTeams = (teams: TeamType[]) =>
  useUserStore.setState({
    tournament: {
      pk: managedTeam.tournament!.pk,
      organization_pk: 7,
      league: 3,
      teams,
    } as unknown as TournamentType,
  });

beforeAll(stubRadix);

beforeEach(() => {
  vi.clearAllMocks();
  useUserStore.setState({ currentUser: user(50, 'viewer') });
  setStoreTeams([]);
  routeGets(axiosMock, { team: managedTeam, org: { pk: 7, admin_ids: [] } });
});

describe('SharedPopoverRenderer team modal', () => {
  it('opens the team modal for a team without a captain', async () => {
    renderRenderer();
    act(() => actions.openTeamModal(snapshot({ captain: null })));
    expect(await screen.findByTestId('team-modal')).toBeTruthy();
  });

  it('keeps the manage dialog and its reason when a player popover opens', async () => {
    renderRenderer();
    act(() => actions.openTeamModal(snapshot()));
    fireEvent.click(await screen.findByTestId('team-manage-button'));
    await requestRowAction('team-member-row-4', 'Make captain');
    fireEvent.change(screen.getByTestId('team-action-reason'), {
      target: { value: 'Typed before hover' },
    });

    const anchor = document.createElement('span');
    document.body.appendChild(anchor);
    act(() => actions.showPlayerPopover(user(4, 'roster_m1'), anchor));
    expect(await screen.findByRole('tooltip')).toBeTruthy();

    expect(screen.getByTestId('team-manage-dialog')).toBeTruthy();
    expect(
      (screen.getByTestId('team-action-reason') as HTMLTextAreaElement).value,
    ).toBe('Typed before hover');
  });

  it('shows the live store team rather than the opening snapshot', async () => {
    setStoreTeams([snapshot()]);
    renderRenderer();
    act(() => actions.openTeamModal(snapshot()));
    await screen.findByTestId('team-modal');
    expect(
      within(screen.getByTestId('team-modal-captain')).getByText('roster_c'),
    ).toBeTruthy();

    act(() => setStoreTeams([snapshot({ captain: user(4, 'roster_m1') })]));
    await waitFor(() =>
      expect(
        within(screen.getByTestId('team-modal-captain')).getByText('roster_m1'),
      ).toBeTruthy(),
    );
  });
});

// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ManagedTeam } from '~/components/api/teamManagementAPI';
import type { TeamType, TournamentType } from '~/components/tournament/types';
import { SharedPopoverProvider } from '~/components/ui/shared-popover-context';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import { ghostCaptainTeam, managedTeam } from '../manage/__tests__/fixtures';
import { stubRadix } from '../manage/__tests__/manageDialogHarness';
import type { TeamManageDialogProps } from '../manage/TeamManageDialog';
import { TeamModal } from '../TeamModal';

const axiosMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('~/components/api/axios', () => ({ default: axiosMock }));
vi.mock('~/components/user/positions', () => ({ RolePositions: () => null }));

const dialogProps = vi.hoisted(() => ({
  last: null as TeamManageDialogProps | null,
}));
vi.mock('../manage/TeamManageDialog', () => ({
  TeamManageDialog: (props: TeamManageDialogProps) => {
    dialogProps.last = props;
    return props.open ? (
      <div data-testid="team-manage-dialog">
        <button type="button" onClick={props.onTeamGone}>
          gone
        </button>
      </div>
    ) : null;
  },
}));

const TOURNAMENT_PK = managedTeam.tournament!.pk;
const user = (pk: number, username: string) =>
  ({ pk, username }) as unknown as UserType;

function storeTeam(overrides: Partial<TeamType> = {}): TeamType {
  return {
    pk: 1,
    name: 'Rostered',
    captain: user(2, 'roster_c'),
    deputy_captain: user(3, 'roster_d'),
    members: [user(2, 'roster_c'), user(3, 'roster_d'), user(4, 'roster_m1')],
    dropin_members: [user(12, 'roster_s')],
    left_members: [user(5, 'roster_m2')],
    ...overrides,
  } as unknown as TeamType;
}

function serve(team: ManagedTeam) {
  axiosMock.get.mockImplementation((url: string) =>
    url === '/teams/1/'
      ? Promise.resolve({ data: team })
      : Promise.reject(new Error(`unexpected GET ${url}`)),
  );
}

function renderModal(team: TeamType = storeTeam()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
  const onOpenChange = vi.fn();
  const element = (t: TeamType) => (
    <QueryClientProvider client={queryClient}>
      <SharedPopoverProvider>
        <TooltipProvider>
          <TeamModal team={t} open onOpenChange={onOpenChange} />
        </TooltipProvider>
      </SharedPopoverProvider>
    </QueryClientProvider>
  );
  const utils = render(element(team));
  return {
    ...utils,
    invalidate,
    onOpenChange,
    rerenderTeam: (t: TeamType) => utils.rerender(element(t)),
  };
}

const teamGets = () =>
  axiosMock.get.mock.calls.filter(([url]) => String(url).startsWith('/teams/'));

beforeAll(stubRadix);

beforeEach(() => {
  vi.clearAllMocks();
  dialogProps.last = null;
  useUserStore.setState({
    currentUser: user(50, 'viewer'),
    tournament: {
      pk: TOURNAMENT_PK,
      organization_pk: 7,
      league: { pk: 3 },
    } as unknown as TournamentType,
  });
  serve(managedTeam);
});

describe('TeamModal manage entry point', () => {
  it('hides the Manage button when the server says the viewer cannot manage', async () => {
    serve({ ...managedTeam, can_manage_team: false });
    renderModal();
    await waitFor(() => expect(teamGets()).toHaveLength(1));
    expect(screen.queryByTestId('team-manage-button')).toBeNull();
  });

  it('sends no GET and hides the button for the anonymous store default user', async () => {
    useUserStore.setState({
      currentUser: useUserStore.getInitialState().currentUser,
    });
    expect(useUserStore.getState().currentUser).toBeTruthy();
    renderModal();
    await screen.findByText('Rostered');
    expect(teamGets()).toHaveLength(0);
    expect(screen.queryByTestId('team-manage-button')).toBeNull();
  });

  it('sends no GET for a team without a pk', async () => {
    renderModal(storeTeam({ pk: null }));
    await screen.findByText('Rostered');
    expect(teamGets()).toHaveLength(0);
  });

  it('shows the Manage button when the viewer can manage, and opens the dialog', async () => {
    renderModal();
    const button = await screen.findByTestId('team-manage-button');
    expect(screen.queryByTestId('team-manage-dialog')).toBeNull();
    fireEvent.click(button);
    expect(screen.getByTestId('team-manage-dialog')).toBeTruthy();
    expect(dialogProps.last).toMatchObject({
      teamId: 1,
      tournamentPk: TOURNAMENT_PK,
      organizationPk: 7,
      leaguePk: 3,
    });
  });

  it('closes the team modal when the team is gone', async () => {
    const { onOpenChange } = renderModal();
    fireEvent.click(await screen.findByTestId('team-manage-button'));
    fireEvent.click(screen.getByText('gone'));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('renders a team without a captain', async () => {
    renderModal(storeTeam({ name: null, captain: null, deputy_captain: null }));
    expect(await screen.findByRole('heading', { name: 'Team' })).toBeTruthy();
    expect(await screen.findByTestId('team-manage-button')).toBeTruthy();
  });

  it('hides leadership flags when the viewer cannot manage', async () => {
    serve({ ...ghostCaptainTeam, can_manage_team: false });
    renderModal(storeTeam({ captain: user(7, 'ghost') }));
    await waitFor(() => expect(teamGets()).toHaveLength(1));
    expect(screen.queryByTestId('team-leadership-problem')).toBeNull();
    expect(screen.queryByTestId('team-modal-leadership-problems')).toBeNull();
  });

  it('shows leadership flags when the server lets the viewer manage', async () => {
    // A league admin who is not org staff: only the server knows.
    useUserStore.setState({ tournament: {} as TournamentType });
    serve(ghostCaptainTeam);
    renderModal(storeTeam({ captain: user(7, 'ghost') }));
    expect(await screen.findByTestId('team-leadership-problem')).toBeTruthy();
    expect(
      screen.getByTestId('team-modal-leadership-problems').textContent,
    ).toContain('is not a member of this team.');
  });

  it('marks the deputy and lists stand-ins and dropouts', async () => {
    renderModal();
    const modal = await screen.findByTestId('team-modal');
    expect(
      within(screen.getByTestId('team-modal-deputy')).getByTestId(
        'roster-status-deputy',
      ),
    ).toBeTruthy();
    const standin = within(modal).getByTestId('team-modal-standin-12');
    expect(within(standin).getByTestId('roster-status-standin')).toBeTruthy();
    expect(within(standin).getByText('roster_s')).toBeTruthy();
    const dropout = within(modal).getByTestId('team-modal-dropout-5');
    expect(within(dropout).getByTestId('roster-status-dropout')).toBeTruthy();
    expect(within(dropout).getByText('roster_m2')).toBeTruthy();
  });

  it('invalidates the team queries when the live roster changes', async () => {
    const { invalidate, rerenderTeam } = renderModal();
    await screen.findByTestId('team-manage-button');
    invalidate.mockClear();
    rerenderTeam(storeTeam({ deputy_captain: user(4, 'roster_m1') }));
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ['team', 1] }),
    );
  });

  it('takes org and league from the team payload, not the store tournament', async () => {
    useUserStore.setState({
      tournament: {
        pk: TOURNAMENT_PK + 1,
        organization_pk: 99,
        league: 98,
      } as unknown as TournamentType,
    });
    serve({ ...managedTeam, organization_pk: 7, league_pk: 3 });
    renderModal();
    fireEvent.click(await screen.findByTestId('team-manage-button'));
    expect(dialogProps.last).toMatchObject({
      tournamentPk: TOURNAMENT_PK,
      organizationPk: 7,
      leaguePk: 3,
    });
  });

  it('passes no org or league when the payload has none', async () => {
    serve({ ...managedTeam, organization_pk: null, league_pk: null });
    renderModal();
    fireEvent.click(await screen.findByTestId('team-manage-button'));
    expect(dialogProps.last).toMatchObject({
      organizationPk: null,
      leaguePk: null,
    });
  });
});

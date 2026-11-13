// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { TournamentType } from '~/components/tournament/types';
import {
  useArchivedTournaments,
  useUpcomingTournaments,
} from '~/hooks/useTournamentList';
import { useMembership } from '../useMembership';
import TournamentsPage from '../tournaments';

vi.mock('~/hooks/useTournamentList', () => ({
  useUpcomingTournaments: vi.fn(),
  useArchivedTournaments: vi.fn(),
}));

vi.mock('../useMembership', () => ({
  useMembership: vi.fn(),
}));

vi.mock('~/components/organization', () => ({
  useOrganizations: () => ({
    organizations: [
      { pk: 30, name: 'Discovery Home' },
      { pk: 31, name: 'Discovery Away' },
    ],
    isLoading: false,
    refetch: vi.fn(),
  }),
}));

vi.mock('~/components/league', () => ({
  useLeagues: () => ({
    leagues: [{ pk: 30, name: 'Home League', organization: { pk: 30 } }],
    isLoading: false,
    refetch: vi.fn(),
  }),
}));

vi.mock('~/components/tournament/create/createModal', () => ({
  TournamentCreateModal: () => null,
}));

vi.mock('~/components/tournament/card/TournamentEditModal', () => ({
  TournamentEditModal: () => null,
}));

vi.mock('~/components/api/api', () => ({
  deleteTournament: vi.fn(),
}));

vi.mock('~/store/userStore', async () => {
  const { create } = await import('zustand');
  return {
    useUserStore: create(() => ({
      currentUser: {},
      isStaff: () => false,
      delTournament: () => undefined,
    })),
  };
});

const upcomingMock = vi.mocked(useUpcomingTournaments);
const archivedMock = vi.mocked(useArchivedTournaments);
const membershipMock = vi.mocked(useMembership);

function tournament(
  pk: number,
  orgId: number,
  state: TournamentType['state'] = 'future',
): TournamentType {
  return {
    pk,
    name: `Cup ${pk}`,
    date_played: '2099-11-20T18:00:00Z',
    timezone: 'UTC',
    tournament_type: 'double_elimination',
    state,
    user_count: 4,
    league: {
      pk: orgId,
      name: `League ${orgId}`,
      organization_name: `Org ${orgId}`,
      organization_id: orgId,
      organization_logo: null,
    },
  } as TournamentType;
}

interface UpcomingStub {
  data: TournamentType[] | undefined;
  isError: boolean;
  isFetching: boolean;
  refetch: ReturnType<typeof vi.fn>;
}

interface ArchivedStub {
  data: { pages: unknown[]; pageParams: unknown[] } | undefined;
  tournaments: TournamentType[];
  isError: boolean;
  isFetching: boolean;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  isFetchNextPageError: boolean;
  fetchNextPage: ReturnType<typeof vi.fn>;
  refetch: ReturnType<typeof vi.fn>;
}

function stubUpcoming(over: Partial<UpcomingStub> = {}): UpcomingStub {
  const stub: UpcomingStub = {
    data: [],
    isError: false,
    isFetching: false,
    refetch: vi.fn(),
    ...over,
  };
  upcomingMock.mockReturnValue(stub as never);
  return stub;
}

function stubArchived(over: Partial<ArchivedStub> = {}): ArchivedStub {
  const tournaments = over.tournaments ?? [];
  const stub: ArchivedStub = {
    data: { pages: [{ results: tournaments }], pageParams: [1] },
    tournaments,
    isError: false,
    isFetching: false,
    hasNextPage: false,
    isFetchingNextPage: false,
    isFetchNextPageError: false,
    fetchNextPage: vi.fn(),
    refetch: vi.fn(),
    ...over,
  };
  archivedMock.mockReturnValue(stub as never);
  return stub;
}

function stubMembership(
  memberOrgIds: number[] | undefined = [30],
  over: Partial<ReturnType<typeof useMembership>> = {},
) {
  membershipMock.mockReturnValue({
    memberOrgIds,
    isLoggedIn: true,
    membershipPending: false,
    ...over,
  });
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location-search">{location.search}</output>;
}

function renderPage(entry = '/tournaments') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <QueryClientProvider client={qc}>
        <TooltipProvider>
          <Routes>
            <Route
              path="/tournaments"
              element={
                <>
                  <TournamentsPage />
                  <LocationProbe />
                </>
              }
            />
          </Routes>
        </TooltipProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function locationParams(): URLSearchParams {
  return new URLSearchParams(screen.getByTestId('location-search').textContent ?? '');
}

beforeEach(() => {
  vi.clearAllMocks();
  stubUpcoming();
  stubArchived();
  stubMembership();
});

describe('tournaments page tabs', () => {
  it('enables only the upcoming query on /tournaments', () => {
    renderPage();
    expect(upcomingMock).toHaveBeenLastCalledWith(expect.anything(), { enabled: true });
    expect(archivedMock).toHaveBeenLastCalledWith(expect.anything(), { enabled: false });
    expect(screen.getByTestId('tournaments-tab-upcoming')).toBeInTheDocument();
    expect(screen.getByTestId('tournaments-tab-archived')).toBeInTheDocument();
  });

  it('enables only the archived query on ?tab=archived', () => {
    renderPage('/tournaments?tab=archived');
    expect(upcomingMock).toHaveBeenLastCalledWith(expect.anything(), { enabled: false });
    expect(archivedMock).toHaveBeenLastCalledWith(expect.anything(), { enabled: true });
  });

  it('renders upcoming for an unknown tab value', () => {
    renderPage('/tournaments?tab=bogus');
    expect(upcomingMock).toHaveBeenLastCalledWith(expect.anything(), { enabled: true });
    expect(screen.getByTestId('tournaments-panel-upcoming')).toBeInTheDocument();
  });

  it('passes parsed org and league filters and ignores invalid ones', () => {
    renderPage('/tournaments?organization=30&league=abc');
    expect(upcomingMock).toHaveBeenLastCalledWith(
      { organization: 30, league: undefined, search: '' },
      { enabled: true },
    );
  });
});

describe('upcoming tiers', () => {
  it('splits into yours and others with counts', () => {
    stubUpcoming({ data: [tournament(1, 30), tournament(2, 31), tournament(3, 31)] });
    renderPage();
    expect(screen.getByTestId('tournaments-tier-yours')).toHaveTextContent(
      /Your organizations\s*\(1\)/,
    );
    expect(screen.getByTestId('tournaments-tier-others')).toHaveTextContent(
      /Other organizations\s*\(2\)/,
    );
    const yours = screen.getByTestId('tournaments-tier-yours').closest('section');
    expect(yours).toHaveAttribute('data-tier', 'yours');
    expect(within(yours as HTMLElement).getByTestId('tournament-card-1')).toBeInTheDocument();
  });

  it('renders a flat list with an organization filter', () => {
    stubUpcoming({ data: [tournament(1, 30), tournament(2, 31)] });
    renderPage('/tournaments?organization=30');
    expect(screen.queryByTestId('tournaments-tier-yours')).toBeNull();
    expect(screen.queryByTestId('tournaments-tier-others')).toBeNull();
    expect(screen.getByTestId('tournament-card-1')).toBeInTheDocument();
    expect(screen.getByTestId('tournament-card-2')).toBeInTheDocument();
  });

  it('omits the others tier when it is empty', () => {
    stubUpcoming({ data: [tournament(1, 30)] });
    renderPage();
    expect(screen.getByTestId('tournaments-tier-yours')).toBeInTheDocument();
    expect(screen.queryByTestId('tournaments-tier-others')).toBeNull();
  });

  it('offers the archive when your organizations have nothing upcoming', async () => {
    stubUpcoming({ data: [tournament(2, 31)] });
    renderPage();
    expect(screen.getByTestId('tournaments-tier-yours')).toBeInTheDocument();
    expect(
      screen.getByText('No upcoming tournaments in your organizations.'),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('tournaments-empty-yours-archived-link'));
    expect(locationParams().get('tab')).toBe('archived');
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByTestId('tournaments-tab-archived')),
    );
  });

  it('shows the live badge on an in-progress upcoming card', () => {
    stubUpcoming({ data: [tournament(1, 30, 'in_progress')] });
    renderPage();
    expect(screen.getByTestId('tournament-live-badge')).toHaveTextContent('Live');
  });
});

describe('upcoming states', () => {
  it('shows the error box only when there is no data', () => {
    const stub = stubUpcoming({ isError: true, data: undefined });
    renderPage();
    const box = screen.getByTestId('tournaments-error-upcoming');
    expect(box.classList.contains('from-red-900/40')).toBe(true);
    expect(box.classList.contains('to-violet-900/40')).toBe(true);
    expect(box.querySelector('.text-error')).not.toBeNull();
    fireEvent.click(within(box).getByRole('button', { name: /retry/i }));
    expect(stub.refetch).toHaveBeenCalled();
  });

  it('keeps the grid when a background refetch fails', () => {
    stubUpcoming({ isError: true, data: [tournament(1, 30)] });
    renderPage();
    expect(screen.queryByTestId('tournaments-error-upcoming')).toBeNull();
    expect(screen.getByTestId('tournament-card-1')).toBeInTheDocument();
  });

  it('suggests clearing filters on an empty filtered result', () => {
    stubUpcoming({ data: [] });
    renderPage('/tournaments?organization=30');
    const empty = screen.getByTestId('tournaments-empty-upcoming');
    expect(empty).toHaveTextContent('No upcoming tournaments');
    expect(empty).toHaveTextContent('Try clearing filters');
    expect(screen.queryByTestId('tournaments-tier-yours')).toBeNull();
  });

  it('does not suggest clearing filters without filters', () => {
    stubUpcoming({ data: [] });
    renderPage();
    expect(screen.getByTestId('tournaments-empty-upcoming')).toHaveTextContent(
      'No upcoming tournaments',
    );
    expect(screen.queryByText('Try clearing filters')).toBeNull();
  });

  it('keeps one panel wrapper with fetch markers for every view', () => {
    stubUpcoming({ data: undefined, isFetching: true });
    const { unmount } = renderPage();
    let panel = screen.getByTestId('tournaments-panel-upcoming');
    expect(panel).toHaveAttribute('data-fetching', 'true');
    expect(panel).toHaveAttribute('aria-busy', 'true');
    expect(screen.queryByTestId('tournaments-tier-yours')).toBeNull();
    unmount();

    stubUpcoming({ data: [] });
    const second = renderPage();
    panel = screen.getByTestId('tournaments-panel-upcoming');
    expect(panel).toHaveAttribute('data-fetching', 'false');
    expect(within(panel).getByTestId('tournaments-empty-upcoming')).toBeInTheDocument();
    second.unmount();

    stubUpcoming({ data: [tournament(1, 30), tournament(2, 31)], isFetching: true });
    renderPage();
    panel = screen.getByTestId('tournaments-panel-upcoming');
    expect(panel).toHaveAttribute('data-fetching', 'true');
    expect(within(panel).getByTestId('tournaments-tier-others')).toBeInTheDocument();
  });

  it('shows the skeleton while membership is pending', () => {
    stubUpcoming({ data: [tournament(1, 30)] });
    stubMembership(undefined, { membershipPending: true });
    renderPage();
    expect(screen.getByTestId('tournaments-panel-upcoming')).toBeInTheDocument();
    expect(screen.queryByTestId('tournament-card-1')).toBeNull();
    expect(screen.queryByTestId('tournaments-tier-yours')).toBeNull();
  });
});

describe('archived tab', () => {
  it('disables load more while the next page is fetching', () => {
    stubArchived({ tournaments: [tournament(5, 31, 'past')], hasNextPage: true, isFetchingNextPage: true });
    renderPage('/tournaments?tab=archived');
    expect(screen.getByTestId('tournaments-load-more')).toBeDisabled();
    expect(screen.getByTestId('tournament-card-5')).toBeInTheDocument();
  });

  it('loads the next page on click', () => {
    const stub = stubArchived({ tournaments: [tournament(5, 31, 'past')], hasNextPage: true });
    renderPage('/tournaments?tab=archived');
    fireEvent.click(screen.getByTestId('tournaments-load-more'));
    expect(stub.fetchNextPage).toHaveBeenCalled();
  });

  it('hides load more without a next page', () => {
    stubArchived({ tournaments: [tournament(5, 31, 'past')], hasNextPage: false });
    renderPage('/tournaments?tab=archived');
    expect(screen.queryByTestId('tournaments-load-more')).toBeNull();
  });

  it('shows an inline error and retry for a failed load more', () => {
    const stub = stubArchived({
      tournaments: [tournament(5, 31, 'past')],
      hasNextPage: true,
      isFetchNextPageError: true,
    });
    renderPage('/tournaments?tab=archived');
    const panel = screen.getByTestId('tournaments-panel-archived');
    expect(panel.querySelector('.text-error')).not.toBeNull();
    fireEvent.click(within(panel).getByRole('button', { name: /retry/i }));
    expect(stub.fetchNextPage).toHaveBeenCalled();
    expect(screen.getByTestId('tournament-card-5')).toBeInTheDocument();
  });

  it('shows the archived error box when the first page fails', () => {
    const stub = stubArchived({ isError: true, data: undefined, tournaments: [] });
    renderPage('/tournaments?tab=archived');
    const box = screen.getByTestId('tournaments-error-archived');
    expect(box.querySelector('.text-error')).not.toBeNull();
    fireEvent.click(within(box).getByRole('button', { name: /retry/i }));
    expect(stub.refetch).toHaveBeenCalled();
  });

  it('shows the archived empty state', () => {
    stubArchived({ tournaments: [] });
    renderPage('/tournaments?tab=archived');
    expect(screen.getByTestId('tournaments-empty-archived')).toHaveTextContent(
      'No archived tournaments',
    );
  });

  it('labels archived cards from the archived bucket', () => {
    stubArchived({ tournaments: [tournament(6, 31, 'in_progress')] });
    renderPage('/tournaments?tab=archived');
    expect(screen.queryByTestId('tournament-live-badge')).toBeNull();
    expect(screen.getByTestId('tournament-card-state')).toHaveTextContent('Past (not closed)');
  });
});

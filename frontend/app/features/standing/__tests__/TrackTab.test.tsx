// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { periodOptions } from '~/features/contributions/timezone';
import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { getStandingLeaderboard } from '../api';
import { TRACK_PANELS } from '../panels';
import type {
  Metric,
  StandingLeaderboard,
  StandingRow,
  TrackInfo,
} from '../schemas';
import { TrackTab } from '../TrackTab';

vi.mock('../api', () => ({
  getStandingLeaderboard: vi.fn(),
}));

vi.mock('~/features/contributions/api', () => ({
  getMemberBreakdown: vi.fn(),
  getPointValues: vi.fn(async () => []),
  getEntries: vi.fn(async () => ({
    count: 0,
    limit: 50,
    offset: 0,
    results: [],
  })),
  setPointValue: vi.fn(),
  createManualAward: vi.fn(),
  updateManualAward: vi.fn(),
  deleteManualAward: vi.fn(),
}));

vi.mock('~/components/api/eventsAPI', () => ({
  getEvents: vi.fn(async () => []),
}));

vi.mock('~/components/user/AddUserModal', () => ({
  AddUserModal: () => null,
  findSearchedUser: () => null,
}));

vi.mock('~/store/orgStore', () => ({
  useOrgStore: (select: (s: { currentOrg: null }) => unknown) =>
    select({ currentOrg: null }),
}));

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
});

const POINTS: Metric = {
  key: 'points',
  label: 'Points',
  format: 'int',
  periodic: true,
  default: true,
};
const ENTRIES: Metric = {
  key: 'entries',
  label: 'Entries',
  format: 'int',
  periodic: true,
  default: false,
};
const SHOW_RATE: Metric = {
  key: 'show_rate',
  label: 'Show rate',
  format: 'percent',
  periodic: false,
  default: true,
};
const SCORE: Metric = {
  key: 'score',
  label: 'Score',
  format: 'score5',
  periodic: true,
  default: false,
};

function track(overrides: Partial<TrackInfo> = {}): TrackInfo {
  return {
    key: 'contribution',
    label: 'Contributions',
    metrics: [POINTS, ENTRIES],
    can_view_rows: true,
    can_view_own: true,
    board_open: true,
    can_manage: false,
    ...overrides,
  };
}

function row(orgUserPk: number, value: number): StandingRow {
  return {
    member: {
      org_user_pk: orgUserPk,
      user_pk: orgUserPk + 100,
      username: `user${orgUserPk}`,
      nickname: null,
      avatarUrl: null,
    },
    value,
    sample: 2,
    status: 'ranked',
  };
}

const access: OrgFeatureAccess = makeOrgFeatureAccess({
  viewerPk: 105,
  canViewContributions: true,
  canViewContributors: true,
});

function respond(base: Partial<StandingLeaderboard> = {}) {
  vi.mocked(getStandingLeaderboard).mockImplementation(
    async (_orgId, trackKey, metric, period) => ({
      track: trackKey,
      metric,
      period,
      total: 20,
      rows: [row(1, 12), row(2, 8)],
      rows_visible: true,
      own_row: null,
      ...base,
    }),
  );
}

function renderTab(t: TrackInfo, viewer: OrgFeatureAccess = access) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <TooltipProvider>{children}</TooltipProvider>
    </QueryClientProvider>
  );
  return render(
    <TrackTab
      orgId={7}
      track={t}
      timeZone="UTC"
      membersPrivate={false}
      access={viewer}
    />,
    { wrapper },
  );
}

async function pickPeriod(prefix: string, value: string) {
  fireEvent.keyDown(screen.getByTestId(`${prefix}-period-select`), {
    key: 'Enter',
  });
  fireEvent.click(await screen.findByTestId(`${prefix}-period-${value}`));
}

afterEach(() => {
  vi.mocked(getStandingLeaderboard).mockReset();
  delete TRACK_PANELS.contribution!.Banner;
});

describe('TrackTab', () => {
  it('renders no switcher for a single-metric track', async () => {
    respond();
    renderTab(track({ metrics: [POINTS] }));
    await screen.findByTestId('contributions-row-1');
    expect(
      screen.queryByTestId('standing-metric-contribution'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Contributions' }),
    ).toBeInTheDocument();
  });

  it('switches contribution points to entries and keeps the period', async () => {
    respond();
    renderTab(track());
    await screen.findByTestId('contributions-row-1');
    expect(screen.getByTestId('contributions-org-total')).toHaveTextContent(
      '20points',
    );
    const month = periodOptions('UTC')[1];
    await pickPeriod('contributions', month.value);
    await waitFor(() =>
      expect(getStandingLeaderboard).toHaveBeenLastCalledWith(
        7,
        'contribution',
        POINTS,
        month.value,
      ),
    );
    fireEvent.click(screen.getByTestId('standing-metric-contribution-entries'));
    await waitFor(() =>
      expect(getStandingLeaderboard).toHaveBeenLastCalledWith(
        7,
        'contribution',
        ENTRIES,
        month.value,
      ),
    );
    expect(screen.getByTestId('contributions-period-select')).toHaveTextContent(
      month.label,
    );
    expect(screen.getByTestId('contributions-org-total')).toHaveTextContent(
      '20points',
    );
  });

  it('ignores the deselect Radix emits when the active metric is clicked again', async () => {
    respond();
    renderTab(track());
    await screen.findByTestId('contributions-row-1');
    const points = screen.getByTestId('standing-metric-contribution-points');
    expect(points).toHaveAttribute('data-state', 'on');
    fireEvent.click(points);
    expect(points).toHaveAttribute('data-state', 'on');
  });

  it('hides the period select for a non-periodic metric and sends no period', async () => {
    respond({ total: null });
    renderTab(track({ metrics: [SHOW_RATE, SCORE] }));
    await screen.findByTestId('contributions-row-1');
    expect(
      screen.queryByTestId('contributions-period-select'),
    ).not.toBeInTheDocument();
    expect(getStandingLeaderboard).toHaveBeenCalledTimes(1);
    expect(getStandingLeaderboard).toHaveBeenLastCalledWith(
      7,
      'contribution',
      SHOW_RATE,
      'all',
    );
    fireEvent.click(screen.getByTestId('standing-metric-contribution-score'));
    expect(
      await screen.findByTestId('contributions-period-select'),
    ).toBeInTheDocument();
  });

  it('shows the self-only note when the board is closed', async () => {
    respond({ rows: [], rows_visible: false, own_row: row(2, 8) });
    renderTab(track({ board_open: false }));
    expect(
      await screen.findByTestId('contributions-self-only'),
    ).toHaveTextContent(
      'This organization keeps its Contributions ranking private.',
    );
    expect(
      await screen.findByTestId('contributions-row-2'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('contributions-members-only'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('contributions-members-private'),
    ).not.toBeInTheDocument();
  });

  it('renders the admin block only for managers', async () => {
    respond();
    const { unmount } = renderTab(track());
    await screen.findByTestId('contributions-row-1');
    expect(screen.queryByTestId('contributions-admin')).not.toBeInTheDocument();
    unmount();

    renderTab(track({ can_manage: true }), {
      ...access,
      canManageContributions: true,
    });
    expect(
      await screen.findByTestId('contributions-admin'),
    ).toBeInTheDocument();
  });

  it('uses a select for more than three metrics and switches metric', async () => {
    const extra: Metric = {
      key: 'rating.comms',
      label: 'Rating: Communication',
      format: 'score5',
      periodic: false,
      default: false,
    };
    respond();
    renderTab(track({ metrics: [POINTS, ENTRIES, SHOW_RATE, SCORE, extra] }));
    await screen.findByTestId('contributions-row-1');
    const trigger = screen.getByRole('combobox', { name: 'Metric' });
    expect(trigger).toHaveAttribute(
      'data-testid',
      'standing-metric-contribution',
    );
    expect(trigger).toHaveTextContent('Points');
    fireEvent.keyDown(trigger, { key: 'Enter' });
    fireEvent.click(
      await screen.findByTestId('standing-metric-contribution-rating.comms'),
    );
    await waitFor(() =>
      expect(getStandingLeaderboard).toHaveBeenLastCalledWith(
        7,
        'contribution',
        extra,
        'all',
      ),
    );
    expect(trigger).toHaveTextContent('Rating: Communication');
  });

  it('renders the panel banner between the header and the board', async () => {
    TRACK_PANELS.contribution!.Banner = () => <div data-testid="test-banner" />;
    respond();
    renderTab(track());
    const rowEl = await screen.findByTestId('contributions-row-1');
    const banner = screen.getByTestId('test-banner');
    const heading = screen.getByRole('heading', { name: 'Contributions' });
    expect(
      heading.compareDocumentPosition(banner) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      banner.compareDocumentPosition(rowEl) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('shows the error with the API message', async () => {
    vi.mocked(getStandingLeaderboard).mockRejectedValue(new Error('boom'));
    renderTab(track());
    expect(
      await screen.findByTestId('contributions-error'),
    ).toBeInTheDocument();
  });
});

// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import {
  CAPTAIN,
  memberLeadership,
  pendingReview,
} from '~/features/leadership/__tests__/fixtures';
import {
  getMemberLeadership,
  getMyReviews,
  getPendingReviews,
} from '~/features/leadership/api';
import type { OrgFeatureAccess } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { getStandingLeaderboard } from '../api';
import type {
  Metric,
  StandingLeaderboard,
  StandingRow,
  TrackInfo,
} from '../schemas';
import { TrackTab } from '../TrackTab';

vi.mock('../api', () => ({ getStandingLeaderboard: vi.fn() }));
vi.mock('~/features/leadership/api', () => ({
  getMemberLeadership: vi.fn(),
  getPendingReviews: vi.fn(),
  getMyReviews: vi.fn(),
  putReview: vi.fn(),
  deleteReview: vi.fn(),
}));

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
});

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

function metric(key: string, label: string, over: Partial<Metric> = {}) {
  return {
    key,
    label,
    format: 'score5',
    periodic: false,
    default: false,
    ...over,
  } satisfies Metric;
}

const METRICS: Metric[] = [
  metric('rating', 'Rating', { default: true }),
  metric('points', 'Points', { format: 'int', periodic: true }),
  metric('rating.communication', 'Communication'),
  metric('rating.drafting', 'Drafting'),
  metric('rating.composure', 'Composure'),
  metric('rating.sportsmanship', 'Sportsmanship'),
];

function leadershipTrack(overrides: Partial<TrackInfo> = {}): TrackInfo {
  return {
    key: 'leadership',
    label: 'Leadership',
    metrics: METRICS,
    can_view_rows: true,
    can_view_own: true,
    board_open: true,
    can_manage: false,
    ...overrides,
  };
}

function row(orgUserPk: number, value: number | null): StandingRow {
  return {
    member: {
      org_user_pk: orgUserPk,
      user_pk: orgUserPk + 100,
      username: `user${orgUserPk}`,
      nickname: null,
      avatarUrl: null,
    },
    value,
    sample: 4,
    status: 'ranked',
  };
}

const member: OrgFeatureAccess = makeOrgFeatureAccess({ viewerPk: 102 });
const nonMemberAdmin: OrgFeatureAccess = makeOrgFeatureAccess({
  viewerPk: 900,
});

function respond(base: Partial<StandingLeaderboard> = {}) {
  vi.mocked(getStandingLeaderboard).mockImplementation(
    async (_orgId, trackKey, m, period) => ({
      track: trackKey,
      metric: m,
      period,
      total: null,
      rows: [row(1, 4.5), row(2, 4.1)],
      rows_visible: true,
      own_row: row(2, 4.1),
      ...base,
    }),
  );
  vi.mocked(getMemberLeadership).mockImplementation(async (_o, pk) =>
    memberLeadership({ member: { ...CAPTAIN, org_user_pk: pk } }),
  );
  vi.mocked(getPendingReviews).mockResolvedValue([]);
  vi.mocked(getMyReviews).mockResolvedValue([]);
}

function renderTab(
  t: TrackInfo = leadershipTrack(),
  viewer: OrgFeatureAccess = member,
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TooltipProvider>{children}</TooltipProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return render(
    <TrackTab
      orgId={7}
      track={t}
      timeZone="UTC"
      membersPrivate={false}
      access={{ ...viewer, standingTracks: [t] }}
    />,
    { wrapper },
  );
}

async function pickMetric(key: string) {
  fireEvent.keyDown(screen.getByTestId('standing-metric-leadership'), {
    key: 'Enter',
  });
  fireEvent.click(
    await screen.findByTestId(`standing-metric-leadership-${key}`),
  );
}

afterEach(() => {
  vi.mocked(getStandingLeaderboard).mockReset();
  vi.mocked(getMemberLeadership).mockReset();
  vi.mocked(getPendingReviews).mockReset();
  vi.mocked(getMyReviews).mockReset();
});

describe('TrackTab leadership', () => {
  it('switches between rating, points and per-trait metrics', async () => {
    respond();
    renderTab();
    expect(await screen.findByTestId('leadership-tab')).toBeInTheDocument();
    await screen.findByTestId('leadership-row-1');
    expect(screen.getByRole('combobox', { name: 'Metric' })).toHaveTextContent(
      'Rating',
    );
    expect(screen.queryByTestId('leadership-period-select')).toBeNull();
    await pickMetric('rating.drafting');
    await waitFor(() =>
      expect(getStandingLeaderboard).toHaveBeenLastCalledWith(
        7,
        'leadership',
        METRICS[3],
        'all',
      ),
    );
    await pickMetric('points');
    expect(
      await screen.findByTestId('leadership-period-select'),
    ).toBeInTheDocument();
  });

  it('opens the captain own panel by default', async () => {
    respond();
    renderTab();
    expect(await screen.findByTestId('leadership-member')).toBeInTheDocument();
    expect(getMemberLeadership).toHaveBeenCalledWith(7, 2);
  });

  it('shows the pending reviews banner above the board', async () => {
    respond();
    vi.mocked(getPendingReviews).mockResolvedValue([
      pendingReview({
        window_closes_at: new Date(Date.now() + 86_400_000).toISOString(),
      }),
    ]);
    renderTab();
    const banner = await screen.findByTestId('leadership-pending');
    const firstRow = await screen.findByTestId('leadership-row-1');
    expect(
      banner.compareDocumentPosition(firstRow) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.getByTestId('leadership-mine-toggle')).toBeInTheDocument();
  });

  it('keeps the board closed for members when not public', async () => {
    respond({ rows: [], rows_visible: false });
    renderTab(leadershipTrack({ board_open: false, can_view_rows: false }));
    expect(
      await screen.findByTestId('leadership-self-only'),
    ).toBeInTheDocument();
    expect(await screen.findByTestId('leadership-member')).toBeInTheDocument();
  });

  it('shows no banner and does not fetch pending reviews for a non-member admin', async () => {
    respond({ own_row: null });
    renderTab(
      leadershipTrack({ can_view_own: false, can_manage: true }),
      nonMemberAdmin,
    );
    await screen.findByTestId('leadership-row-1');
    expect(screen.queryByTestId('leadership-pending')).toBeNull();
    expect(screen.queryByTestId('leadership-mine-toggle')).toBeNull();
    expect(getPendingReviews).not.toHaveBeenCalled();
    expect(getMyReviews).not.toHaveBeenCalled();
  });

  it('shows the admins-only message when the backend refuses a captain', async () => {
    respond();
    vi.mocked(getMemberLeadership).mockImplementation(async (_o, pk) => {
      if (pk === 1)
        throw { response: { status: 403, data: { code: 'not_permitted' } } };
      return memberLeadership({ member: { ...CAPTAIN, org_user_pk: pk } });
    });
    renderTab();
    await screen.findByTestId('leadership-member');
    fireEvent.click(screen.getByTestId('leadership-row-1'));
    expect(
      await screen.findByTestId('leadership-member-forbidden'),
    ).toHaveTextContent("Only org admins can see other captains' details.");
  });

  it('admins open any captain', async () => {
    respond({ own_row: null });
    renderTab(
      leadershipTrack({ can_view_own: false, can_manage: true }),
      nonMemberAdmin,
    );
    fireEvent.click(await screen.findByTestId('leadership-row-1'));
    expect(await screen.findByTestId('leadership-member')).toBeInTheDocument();
    expect(getMemberLeadership).toHaveBeenCalledWith(7, 1);
  });
});

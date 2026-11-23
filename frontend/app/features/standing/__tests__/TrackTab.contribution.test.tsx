// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { getMemberBreakdown } from '~/features/contributions/api';
import { periodOptions } from '~/features/contributions/timezone';
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

vi.mock('../api', () => ({
  getStandingLeaderboard: vi.fn(),
}));

vi.mock('~/features/contributions/api', () => ({
  getMemberBreakdown: vi.fn(),
}));

beforeAll(() => {
  // Radix Select needs these pointer/scroll APIs, which jsdom lacks.
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

const TRACK: TrackInfo = {
  key: 'contribution',
  label: 'Contributions',
  metrics: [POINTS],
  can_view_rows: true,
  can_view_own: true,
  board_open: true,
  can_manage: false,
  can_moderate: false,
};

const access: OrgFeatureAccess = makeOrgFeatureAccess({
  viewerPk: 5,
  canViewContributions: true,
  canViewContributors: true,
});

function row(
  orgUserPk: number,
  userPk: number,
  username: string,
  points: number,
): StandingRow {
  return {
    member: {
      org_user_pk: orgUserPk,
      user_pk: userPk,
      username,
      nickname: null,
      avatarUrl: null,
    },
    value: points,
    sample: 1,
    status: 'ranked',
  };
}

function board(
  overrides: Partial<StandingLeaderboard> = {},
): StandingLeaderboard {
  return {
    track: 'contribution',
    metric: POINTS,
    period: 'all',
    total: 0,
    rows_visible: true,
    rows: [],
    own_row: null,
    ...overrides,
  };
}

function renderTab(
  timeZone: string | undefined = 'America/New_York',
  {
    membersPrivate = true,
    viewer = access,
  }: { membersPrivate?: boolean; viewer?: OrgFeatureAccess } = {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(
    <TrackTab
      orgId={7}
      track={TRACK}
      timeZone={timeZone}
      membersPrivate={membersPrivate}
      access={viewer}
    />,
    { wrapper },
  );
}

afterEach(() => {
  vi.mocked(getStandingLeaderboard).mockReset();
  vi.mocked(getMemberBreakdown).mockReset();
});

describe('ContributionsTab leaderboard', () => {
  it('shows the private note without an own-standing promise to a non-member of a private org', async () => {
    vi.mocked(getStandingLeaderboard).mockResolvedValue(
      board({ total: 42, rows_visible: false }),
    );
    renderTab();
    expect(
      await screen.findByTestId('contributions-org-total'),
    ).toHaveTextContent('42');
    const note = screen.getByTestId('contributions-members-private');
    expect(note).toHaveTextContent('Members are private in this organization.');
    expect(note).not.toHaveTextContent('your own standing');
    expect(screen.queryByTestId('contributions-empty')).not.toBeInTheDocument();
    expect(getStandingLeaderboard).toHaveBeenCalledWith(
      7,
      'contribution',
      POINTS,
      'all',
    );
  });

  it('asks an anonymous viewer of a public org to sign in, not that members are private', async () => {
    vi.mocked(getStandingLeaderboard).mockResolvedValue(
      board({ total: 42, rows_visible: false }),
    );
    renderTab('UTC', {
      membersPrivate: false,
      viewer: { ...access, viewerPk: null },
    });
    expect(
      await screen.findByTestId('contributions-members-signin'),
    ).toHaveTextContent('Sign in as a member to see the leaderboard.');
    expect(
      screen.queryByTestId('contributions-members-private'),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId('contributions-empty')).not.toBeInTheDocument();
  });

  it('tells a signed-in outsider of a public org that only members see the leaderboard', async () => {
    vi.mocked(getStandingLeaderboard).mockResolvedValue(
      board({ total: 42, rows_visible: false }),
    );
    renderTab('UTC', { membersPrivate: false });
    expect(
      await screen.findByTestId('contributions-members-only'),
    ).toHaveTextContent(
      'Only members of this organization can see the leaderboard.',
    );
    expect(
      screen.queryByTestId('contributions-members-private'),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId('contributions-empty')).not.toBeInTheDocument();
  });

  it('still shows the empty state when the visible leaderboard has no rows', async () => {
    vi.mocked(getStandingLeaderboard).mockResolvedValue(board());
    renderTab('UTC', { membersPrivate: false });
    expect(await screen.findByTestId('contributions-empty')).toHaveTextContent(
      'No contributions in this period',
    );
  });

  it('highlights the viewer own row in the visible leaderboard', async () => {
    vi.mocked(getStandingLeaderboard).mockResolvedValue(
      board({
        total: 30,
        rows: [row(11, 9, 'alice', 20), row(12, 5, 'me', 10)],
        own_row: row(12, 5, 'me', 10),
      }),
    );
    renderTab();
    const own = await screen.findByTestId('contributions-row-12');
    expect(own).toHaveAttribute('data-own', 'true');
    expect(screen.getByTestId('contributions-row-11')).toHaveAttribute(
      'data-own',
      'false',
    );
    expect(
      screen.queryByTestId('contributions-members-private'),
    ).not.toBeInTheDocument();
  });

  it('shows only the own row, highlighted, to a member of a private org', async () => {
    vi.mocked(getStandingLeaderboard).mockResolvedValue(
      board({
        total: 30,
        rows_visible: false,
        own_row: row(12, 5, 'me', 10),
      }),
    );
    renderTab();
    const own = await screen.findByTestId('contributions-row-12');
    expect(own).toHaveAttribute('data-own', 'true');
    expect(own).toHaveTextContent('10');
    expect(
      screen.getByTestId('contributions-members-private'),
    ).toHaveTextContent(
      'Members are private in this organization, so only your own standing is shown.',
    );
  });

  it('renders period labels without throwing for an invalid org timezone', async () => {
    vi.mocked(getStandingLeaderboard).mockResolvedValue(board());
    renderTab('Not/AZone');
    const trigger = await screen.findByTestId('contributions-period-select');
    expect(trigger).toHaveTextContent('All time');
    fireEvent.keyDown(trigger, { key: 'Enter' });
    const listbox = await screen.findByRole('listbox');
    const options = within(listbox).getAllByRole('option');
    expect(options).toHaveLength(13);
    expect(options[1].textContent).toMatch(/^[A-Z][a-z]+ \d{4}$/);
  });

  it('opens the breakdown on row click and formats entry dates for an invalid org timezone', async () => {
    vi.mocked(getStandingLeaderboard).mockResolvedValue(
      board({
        total: 30,
        rows: [row(11, 9, 'alice', 20), row(12, 5, 'me', 10)],
        own_row: row(12, 5, 'me', 10),
      }),
    );
    vi.mocked(getMemberBreakdown).mockResolvedValue({
      member: {
        org_user_pk: 11,
        user_pk: 9,
        username: 'alice',
        nickname: null,
        avatarUrl: null,
      },
      totals: { all_time: 20, this_month: 5 },
      monthly: [],
      entries: [
        {
          pk: 301,
          kind: 'event_host',
          points: 10,
          event: null,
          event_name: 'Weekly Cup',
          occurred_at: '2026-03-15T12:00:00Z',
        },
      ],
    });
    renderTab('Not/AZone', { membersPrivate: false });
    const alice = await screen.findByRole('button', {
      name: "Open alice's details",
    });
    expect(
      screen.queryByTestId('contributions-breakdown'),
    ).not.toBeInTheDocument();
    fireEvent.click(alice);
    const entry = await screen.findByTestId('contributions-entry-301');
    expect(getMemberBreakdown).toHaveBeenCalledWith(7, 11, 'all');
    expect(entry).toHaveTextContent('Event host');
    expect(entry).toHaveTextContent('Mar 15, 2026 · Weekly Cup');
    expect(
      screen.getByTestId('contributions-member-all-time'),
    ).toHaveTextContent('20');
  });

  it("keeps a private-org member's own breakdown open for a period without own entries", async () => {
    vi.mocked(getStandingLeaderboard).mockImplementation(
      async (_orgId, _track, _metric, period) =>
        board({
          period,
          total: 30,
          rows_visible: false,
          own_row: period === 'all' ? row(12, 5, 'me', 10) : null,
        }),
    );
    vi.mocked(getMemberBreakdown).mockResolvedValue({
      member: {
        org_user_pk: 12,
        user_pk: 5,
        username: 'me',
        nickname: null,
        avatarUrl: null,
      },
      totals: { all_time: 10, this_month: 0 },
      monthly: [],
      entries: [],
    });
    renderTab('UTC');
    fireEvent.click(await screen.findByTestId('contributions-row-12'));
    expect(
      await screen.findByTestId('contributions-member-all-time'),
    ).toHaveTextContent('10');
    const month = periodOptions('UTC')[1];
    fireEvent.keyDown(screen.getByTestId('contributions-period-select'), {
      key: 'Enter',
    });
    fireEvent.click(
      await screen.findByTestId(`contributions-period-${month.value}`),
    );
    await waitFor(() =>
      expect(getMemberBreakdown).toHaveBeenCalledWith(7, 12, month.value),
    );
    await waitFor(() =>
      expect(
        screen.queryByTestId('contributions-row-12'),
      ).not.toBeInTheDocument(),
    );
    expect(screen.getByTestId('contributions-breakdown')).toBeInTheDocument();
  });
});

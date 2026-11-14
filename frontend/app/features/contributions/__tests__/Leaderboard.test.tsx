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
import type { OrgFeatureAccess } from '~/features/org-features';
import { getLeaderboard, getMemberBreakdown } from '../api';
import { ContributionsTab } from '../ContributionsTab';
import type { LeaderboardRow } from '../schemas';
import { periodOptions, safeTimeZone } from '../timezone';

vi.mock('../api', () => ({
  getLeaderboard: vi.fn(),
  getMemberBreakdown: vi.fn(),
}));

beforeAll(() => {
  // Radix Select needs these pointer/scroll APIs, which jsdom lacks.
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
});

const access: OrgFeatureAccess = {
  settled: true,
  viewerPk: 5,
  canUsePromotion: false,
  canManageTemplates: false,
  canManagePromoters: false,
  canViewContributions: true,
  canViewContributors: true,
  canManageContributions: false,
};

function row(
  orgUserPk: number,
  userPk: number,
  username: string,
  points: number,
): LeaderboardRow {
  return {
    org_user_pk: orgUserPk,
    user_pk: userPk,
    username,
    nickname: null,
    avatarUrl: null,
    points,
    entries: 1,
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
    <ContributionsTab
      orgId={7}
      timeZone={timeZone}
      membersPrivate={membersPrivate}
      access={viewer}
    />,
    { wrapper },
  );
}

afterEach(() => {
  vi.mocked(getLeaderboard).mockReset();
  vi.mocked(getMemberBreakdown).mockReset();
});

describe('ContributionsTab leaderboard', () => {
  it('shows the private note without an own-standing promise to a non-member of a private org', async () => {
    vi.mocked(getLeaderboard).mockResolvedValue({
      period: 'all',
      total: 42,
      rows_visible: false,
      rows: [],
      own_row: null,
    });
    renderTab();
    expect(
      await screen.findByTestId('contributions-org-total'),
    ).toHaveTextContent('42');
    const note = screen.getByTestId('contributions-members-private');
    expect(note).toHaveTextContent('Members are private in this organization.');
    expect(note).not.toHaveTextContent('your own standing');
    expect(screen.queryByTestId('contributions-empty')).not.toBeInTheDocument();
    expect(getLeaderboard).toHaveBeenCalledWith(7, 'all');
  });

  it('asks an anonymous viewer of a public org to sign in, not that members are private', async () => {
    vi.mocked(getLeaderboard).mockResolvedValue({
      period: 'all',
      total: 42,
      rows_visible: false,
      rows: [],
      own_row: null,
    });
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
    vi.mocked(getLeaderboard).mockResolvedValue({
      period: 'all',
      total: 42,
      rows_visible: false,
      rows: [],
      own_row: null,
    });
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
    vi.mocked(getLeaderboard).mockResolvedValue({
      period: 'all',
      total: 0,
      rows_visible: true,
      rows: [],
      own_row: null,
    });
    renderTab('UTC', { membersPrivate: false });
    expect(await screen.findByTestId('contributions-empty')).toHaveTextContent(
      'No contributions in this period',
    );
  });

  it('highlights the viewer own row in the visible leaderboard', async () => {
    vi.mocked(getLeaderboard).mockResolvedValue({
      period: 'all',
      total: 30,
      rows_visible: true,
      rows: [row(11, 9, 'alice', 20), row(12, 5, 'me', 10)],
      own_row: row(12, 5, 'me', 10),
    });
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
    vi.mocked(getLeaderboard).mockResolvedValue({
      period: 'all',
      total: 30,
      rows_visible: false,
      rows: [],
      own_row: row(12, 5, 'me', 10),
    });
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
    vi.mocked(getLeaderboard).mockResolvedValue({
      period: 'all',
      total: 0,
      rows_visible: true,
      rows: [],
      own_row: null,
    });
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
    vi.mocked(getLeaderboard).mockResolvedValue({
      period: 'all',
      total: 30,
      rows_visible: true,
      rows: [row(11, 9, 'alice', 20), row(12, 5, 'me', 10)],
      own_row: row(12, 5, 'me', 10),
    });
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
      name: "View alice's contributions",
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
    vi.mocked(getLeaderboard).mockImplementation(async (_orgId, period) => ({
      period,
      total: 30,
      rows_visible: false,
      rows: [],
      own_row: period === 'all' ? row(12, 5, 'me', 10) : null,
    }));
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

describe('safeTimeZone', () => {
  it('falls back to UTC for an invalid zone', () => {
    expect(safeTimeZone('Not/AZone')).toBe('UTC');
  });

  it('falls back to UTC for a missing zone and keeps a valid one', () => {
    expect(safeTimeZone(undefined)).toBe('UTC');
    expect(safeTimeZone('America/New_York')).toBe('America/New_York');
  });
});

describe('periodOptions', () => {
  it('lists all time then the last 12 months in the org timezone', () => {
    const now = new Date('2026-11-01T03:00:00Z');
    const ny = periodOptions('America/New_York', now);
    expect(ny[0]).toEqual({ value: 'all', label: 'All time' });
    expect(ny).toHaveLength(13);
    expect(ny[1]).toEqual({ value: '2026-10', label: 'October 2026' });
    expect(ny[12].value).toBe('2025-11');
    expect(periodOptions('Not/AZone', now)[1]).toEqual({
      value: '2026-11',
      label: 'November 2026',
    });
  });
});

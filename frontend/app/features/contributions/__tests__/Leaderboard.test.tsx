// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { OrgFeatureAccess } from '~/features/org-features';
import { getLeaderboard, getMemberBreakdown } from '../api';
import { ContributionsTab } from '../ContributionsTab';
import type { LeaderboardResponse, LeaderboardRow } from '../schemas';
import { periodOptions, safeTimeZone } from '../timezone';

vi.mock('../api', () => ({ getLeaderboard: vi.fn(), getMemberBreakdown: vi.fn() }));

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

function row(orgUserPk: number, userPk: number, username: string, points: number): LeaderboardRow {
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
  { membersPrivate = true, viewer = access }: { membersPrivate?: boolean; viewer?: OrgFeatureAccess } = {},
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
    expect(await screen.findByTestId('contributions-org-total')).toHaveTextContent('42');
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
    renderTab('UTC', { membersPrivate: false, viewer: { ...access, viewerPk: null } });
    expect(await screen.findByTestId('contributions-members-signin')).toHaveTextContent(
      'Sign in as a member to see the leaderboard.',
    );
    expect(screen.queryByTestId('contributions-members-private')).not.toBeInTheDocument();
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
    expect(await screen.findByTestId('contributions-members-only')).toHaveTextContent(
      'Only members of this organization can see the leaderboard.',
    );
    expect(screen.queryByTestId('contributions-members-private')).not.toBeInTheDocument();
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
    expect(screen.getByTestId('contributions-row-11')).toHaveAttribute('data-own', 'false');
    expect(screen.queryByTestId('contributions-members-private')).not.toBeInTheDocument();
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
    expect(screen.getByTestId('contributions-members-private')).toHaveTextContent(
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
    expect(periodOptions('Not/AZone', now)[1]).toEqual({ value: '2026-11', label: 'November 2026' });
  });
});

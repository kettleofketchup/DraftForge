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

function renderTab(timeZone: string | undefined = 'America/New_York') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<ContributionsTab orgId={7} timeZone={timeZone} access={access} />, { wrapper });
}

afterEach(() => {
  vi.mocked(getLeaderboard).mockReset();
  vi.mocked(getMemberBreakdown).mockReset();
});

describe('ContributionsTab leaderboard', () => {
  it('shows the org total and the private note when rows are hidden', async () => {
    const data: LeaderboardResponse = {
      period: 'all',
      total: 42,
      rows_visible: false,
      rows: [],
      own_row: null,
    };
    vi.mocked(getLeaderboard).mockResolvedValue(data);
    renderTab();
    expect(await screen.findByTestId('contributions-org-total')).toHaveTextContent('42');
    expect(screen.getByTestId('contributions-members-private')).toBeInTheDocument();
    expect(getLeaderboard).toHaveBeenCalledWith(7, 'all');
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

  it('shows only the own row, highlighted, when members are private', async () => {
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

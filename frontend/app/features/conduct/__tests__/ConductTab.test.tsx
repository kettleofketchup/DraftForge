// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { OrgFeatureAccess } from '~/features/org-features';
import { getConductLeaderboard, getMemberConduct } from '../api';
import { ConductTab } from '../ConductTab';
import type { MemberConduct } from '../schemas';

vi.mock('../api', () => ({
  getConductLeaderboard: vi.fn(),
  getMemberConduct: vi.fn(),
}));

const base: OrgFeatureAccess = {
  settled: true,
  viewerPk: 5,
  canUsePromotion: false,
  canManageTemplates: false,
  canManagePromoters: false,
  canViewContributions: false,
  canViewContributors: false,
  canManageContributions: false,
  canViewConduct: false,
  canViewOwnConduct: true,
  canViewConductDetails: false,
  canManageConduct: false,
};

const me = {
  org_user_pk: 12,
  user_pk: 5,
  username: 'me',
  nickname: null,
  avatarUrl: null,
};
const alice = {
  org_user_pk: 11,
  user_pk: 9,
  username: 'alice',
  nickname: null,
  avatarUrl: null,
};

function memberConduct(overrides: Partial<MemberConduct> = {}): MemberConduct {
  return {
    member: me,
    show_rate: 0.8,
    status: 'scored',
    counted_events: 3,
    weighted_events: 2.5,
    totals: { attended: 2, no_show: 1, late_cancel: 0, excused: 0 },
    history: [
      {
        event_id: 41,
        event_name: 'Weekly Cup',
        event_starts_at: '2026-11-01T20:00:00Z',
        outcome: 'no_show',
        source: 'default',
        committed: true,
        finalized: true,
        voided: false,
        weight: 0.75,
        reason: 'Did not show',
      },
      {
        event_id: null,
        event_name: 'Deleted night',
        event_starts_at: '2026-10-01T20:00:00Z',
        outcome: 'attended',
        source: 'staff',
        committed: false,
        finalized: true,
        voided: false,
        weight: 0.5,
      },
    ],
    ...overrides,
  };
}

function renderTab(access: OrgFeatureAccess) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
  return render(
    <ConductTab
      orgId={7}
      timeZone="UTC"
      membersPrivate={false}
      access={access}
    />,
    { wrapper },
  );
}

afterEach(() => {
  cleanup();
  vi.mocked(getConductLeaderboard).mockReset();
  vi.mocked(getMemberConduct).mockReset();
});

describe('ConductTab self-only mode', () => {
  it('shows only the viewer history with the private-ranking note', async () => {
    vi.mocked(getConductLeaderboard).mockResolvedValue({
      rows_visible: false,
      rows: [],
      new_members: [],
      own_row: {
        member: me,
        show_rate: 0.8,
        counted_events: 3,
        status: 'scored',
        rank: null,
      },
    });
    vi.mocked(getMemberConduct).mockResolvedValue(memberConduct());
    renderTab(base);

    expect(await screen.findByTestId('conduct-self-only')).toHaveTextContent(
      'This organization keeps its attendance ranking private.',
    );
    expect(
      await screen.findByTestId('conduct-history-row-41'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('conduct-table')).not.toBeInTheDocument();
    expect(getConductLeaderboard).toHaveBeenCalledWith(7);
    expect(getMemberConduct).toHaveBeenCalledWith(7, 12, {
      limit: 50,
      offset: 0,
    });
    expect(screen.getByTestId('conduct-member-score')).toHaveTextContent('80%');
  });

  it('labels outcomes, walk-ins and removed events, hiding staff details', async () => {
    vi.mocked(getConductLeaderboard).mockResolvedValue({
      rows_visible: false,
      rows: [],
      new_members: [],
      own_row: {
        member: me,
        show_rate: 0.8,
        counted_events: 3,
        status: 'scored',
        rank: null,
      },
    });
    vi.mocked(getMemberConduct).mockResolvedValue(memberConduct());
    renderTab(base);

    const row = await screen.findByTestId('conduct-history-row-41');
    expect(row).toHaveTextContent('Weekly Cup');
    expect(
      row.querySelector('[data-testid="conduct-outcome-no_show"]'),
    ).toHaveTextContent('No-show');
    expect(row).not.toHaveTextContent('Weight');
    const removed = screen.getByTestId('conduct-history-row-removed-1');
    expect(removed).toHaveTextContent('Removed');
    expect(removed).toHaveTextContent('Walk-in');
  });

  it('renders the empty state for a member with no counted events', async () => {
    vi.mocked(getConductLeaderboard).mockResolvedValue({
      rows_visible: false,
      rows: [],
      new_members: [],
      own_row: {
        member: me,
        show_rate: 0.75,
        counted_events: 0,
        status: 'new',
        rank: null,
      },
    });
    vi.mocked(getMemberConduct).mockResolvedValue(
      memberConduct({
        status: 'new',
        show_rate: 0.75,
        counted_events: 0,
        weighted_events: 0,
        totals: { attended: 0, no_show: 0, late_cancel: 0, excused: 0 },
        history: [],
      }),
    );
    renderTab(base);

    expect(
      await screen.findByTestId('conduct-history-empty'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('conduct-member-score')).toHaveTextContent('New');
  });
});

describe('ConductTab full mode', () => {
  it('lets staff open another member and see weights and reasons', async () => {
    vi.mocked(getConductLeaderboard).mockResolvedValue({
      rows_visible: true,
      rows: [
        { member: alice, show_rate: 0.9, counted_events: 5, rank: 1 },
        { member: me, show_rate: 0.8, counted_events: 3, rank: 2 },
      ],
      new_members: [],
      own_row: {
        member: me,
        show_rate: 0.8,
        counted_events: 3,
        status: 'scored',
        rank: 2,
      },
    });
    vi.mocked(getMemberConduct).mockImplementation(async (_org, pk) =>
      memberConduct(pk === 11 ? { member: alice } : {}),
    );
    renderTab({
      ...base,
      canViewConduct: true,
      canViewConductDetails: true,
    });

    expect(await screen.findByTestId('conduct-table')).toBeInTheDocument();
    expect(screen.queryByTestId('conduct-self-only')).not.toBeInTheDocument();
    await screen.findByTestId('conduct-history-row-41');
    expect(getMemberConduct).toHaveBeenCalledWith(7, 12, {
      limit: 50,
      offset: 0,
    });

    fireEvent.click(screen.getByTestId('conduct-row-11'));
    await waitFor(() =>
      expect(screen.getByTestId('conduct-history')).toHaveTextContent('alice'),
    );
    expect(getMemberConduct).toHaveBeenCalledWith(7, 11, {
      limit: 50,
      offset: 0,
    });
    const row = await screen.findByTestId('conduct-history-row-41');
    expect(row).toHaveTextContent('Weight 0.75');
    expect(row).toHaveTextContent('Did not show');
  });
});

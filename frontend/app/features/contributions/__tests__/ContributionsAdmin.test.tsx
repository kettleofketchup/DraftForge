// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { OrgFeatureAccess } from '~/features/org-features';
import {
  createManualAward,
  deleteManualAward,
  getEntries,
  getLeaderboard,
  getPointValues,
  setPointValue,
  updateManualAward,
} from '../api';
import { ContributionsTab } from '../ContributionsTab';
import type { AdminEntry, PointValueRow } from '../schemas';

vi.mock('../api', () => ({
  getLeaderboard: vi.fn(),
  getMemberBreakdown: vi.fn(),
  getPointValues: vi.fn(),
  setPointValue: vi.fn(),
  getEntries: vi.fn(),
  createManualAward: vi.fn(),
  updateManualAward: vi.fn(),
  deleteManualAward: vi.fn(),
}));

vi.mock('~/components/api/eventsAPI', () => ({
  getEvents: vi.fn(async () => []),
}));

vi.mock('~/hooks/useOrgUsers', () => ({
  useOrgUsers: () => [
    {
      pk: 3,
      username: 'alice',
      nickname: null,
      orgData: {},
      leagueData: {},
      _fetchedAt: 0,
    },
    {
      pk: 4,
      username: 'bob',
      nickname: 'Bobby',
      orgData: {},
      leagueData: {},
      _fetchedAt: 0,
    },
  ],
}));

const getOrgUsers = vi.fn();
vi.mock('~/store/orgStore', () => ({
  useOrgStore: { getState: () => ({ getOrgUsers }) },
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
});

const base: OrgFeatureAccess = {
  settled: true,
  viewerPk: 5,
  canUsePromotion: false,
  canManageTemplates: false,
  canManagePromoters: false,
  canViewContributions: true,
  canViewContributors: true,
  canManageContributions: false,
};
const admin: OrgFeatureAccess = { ...base, canManageContributions: true };

const pointValues: PointValueRow[] = [
  { kind: 'promo_message', points: 1, default: 1, is_default: true },
  { kind: 'event_host', points: 10, default: 10, is_default: true },
  { kind: 'event_helper', points: 8, default: 5, is_default: false },
];

const member = {
  org_user_pk: 21,
  user_pk: 3,
  username: 'alice',
  nickname: null,
  avatarUrl: null,
};

function entry(pk: number, kind: AdminEntry['kind']): AdminEntry {
  return {
    pk,
    kind,
    points: 5,
    event: null,
    event_name: '',
    occurred_at: '2026-11-01T17:00:00Z',
    reason: kind === 'manual' ? 'Casting' : '',
    member,
    awarded_by: null,
  };
}

function renderTab(access: OrgFeatureAccess, timeZone = 'UTC') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <TooltipProvider>{children}</TooltipProvider>
    </QueryClientProvider>
  );
  return render(
    <ContributionsTab
      orgId={7}
      timeZone={timeZone}
      membersPrivate={false}
      access={access}
    />,
    { wrapper },
  );
}

beforeEach(() => {
  vi.mocked(getLeaderboard).mockResolvedValue({
    period: 'all',
    total: 0,
    rows_visible: true,
    rows: [],
    own_row: null,
  });
  vi.mocked(getPointValues).mockResolvedValue(pointValues);
  vi.mocked(getEntries).mockResolvedValue({
    count: 2,
    limit: 50,
    offset: 0,
    results: [entry(31, 'manual'), entry(32, 'event_host')],
  });
  vi.mocked(setPointValue).mockResolvedValue({
    kind: 'event_host',
    old: 10,
    new: 20,
    changed: 0,
  });
  vi.mocked(createManualAward).mockResolvedValue(entry(33, 'manual'));
  vi.mocked(deleteManualAward).mockResolvedValue(undefined);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('contributions admin section', () => {
  it('is not rendered and loads nothing for non-admins', async () => {
    renderTab(base);
    await screen.findByTestId('contributions-tab');
    await waitFor(() => expect(getLeaderboard).toHaveBeenCalled());
    expect(screen.queryByTestId('contributions-admin')).toBeNull();
    expect(getPointValues).not.toHaveBeenCalled();
    expect(getEntries).not.toHaveBeenCalled();
    expect(getOrgUsers).not.toHaveBeenCalled();
  });

  it('shows default and changed badges with reset only for changed kinds', async () => {
    renderTab(admin);
    expect(
      await screen.findByTestId('point-value-badge-event_helper'),
    ).toHaveTextContent('Changed');
    expect(
      screen.getByTestId('point-value-badge-event_host'),
    ).toHaveTextContent('Default');
    expect(
      screen.getByTestId('point-value-reset-event_helper'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('point-value-reset-event_host')).toBeNull();
    expect(screen.getByTestId('point-value-event_helper')).toHaveValue(8);
    expect(getOrgUsers).toHaveBeenCalledWith(7);
  });

  it('applies a new value to past entries since a chosen date', async () => {
    renderTab(admin);
    const input = await screen.findByTestId('point-value-event_host');
    fireEvent.change(input, { target: { value: '20' } });
    fireEvent.click(screen.getByTestId('point-value-save-event_host'));

    const since = await screen.findByTestId('rescore-since-input');
    expect(since).toBeDisabled();
    fireEvent.click(screen.getByTestId('rescore-apply-past'));
    expect(since).toBeEnabled();
    fireEvent.change(since, { target: { value: '2026-10-01' } });
    fireEvent.click(screen.getByTestId('rescore-confirm'));

    await waitFor(() =>
      expect(setPointValue).toHaveBeenCalledWith(7, 'event_host', {
        points: 20,
        apply_to_past: true,
        since: '2026-10-01',
      }),
    );
  });

  it('saves future-only by default and resets with a null value', async () => {
    renderTab(admin);
    fireEvent.click(
      await screen.findByTestId('point-value-reset-event_helper'),
    );
    fireEvent.click(await screen.findByTestId('rescore-confirm'));
    await waitFor(() =>
      expect(setPointValue).toHaveBeenCalledWith(7, 'event_helper', {
        points: null,
        apply_to_past: false,
        since: null,
      }),
    );
  });

  it('rejects an out-of-range point value without calling the API', async () => {
    renderTab(admin);
    const input = await screen.findByTestId('point-value-event_host');
    fireEvent.change(input, { target: { value: '1001' } });
    fireEvent.click(screen.getByTestId('point-value-save-event_host'));
    expect(await screen.findByText('At most 1000 points')).toBeInTheDocument();
    expect(screen.queryByTestId('rescore-confirm')).toBeNull();
    expect(setPointValue).not.toHaveBeenCalled();
  });

  it('offers edit and delete only on manual ledger rows', async () => {
    renderTab(admin);
    await screen.findByTestId('ledger-row-31');
    expect(screen.getByTestId('ledger-edit-31')).toBeInTheDocument();
    expect(screen.getByTestId('ledger-delete-31')).toBeInTheDocument();
    expect(screen.getByTestId('ledger-row-32')).toBeInTheDocument();
    expect(screen.queryByTestId('ledger-edit-32')).toBeNull();
    expect(screen.queryByTestId('ledger-delete-32')).toBeNull();
    expect(screen.getByTestId('ledger-row-31')).toHaveTextContent('Casting');
  });

  it('blocks a manual award with a blank reason', async () => {
    renderTab(admin);
    fireEvent.click(await screen.findByTestId('manual-award-submit'));
    expect(await screen.findByText('Enter a reason')).toBeInTheDocument();
    expect(screen.getByText('Pick a member')).toBeInTheDocument();
    expect(createManualAward).not.toHaveBeenCalled();
  });

  it('submits a manual award for the picked member', async () => {
    renderTab(admin);
    const trigger = await screen.findByTestId('manual-award-member');
    fireEvent.keyDown(trigger, { key: 'Enter' });
    fireEvent.click(await screen.findByTestId('manual-award-member-4'));
    fireEvent.change(screen.getByTestId('manual-award-points'), {
      target: { value: '15' },
    });
    fireEvent.change(screen.getByTestId('manual-award-reason'), {
      target: { value: '  Casting  ' },
    });
    fireEvent.change(screen.getByTestId('manual-award-date'), {
      target: { value: '2026-11-01' },
    });
    fireEvent.click(screen.getByTestId('manual-award-submit'));
    await waitFor(() =>
      expect(createManualAward).toHaveBeenCalledWith(7, {
        user_id: 4,
        points: 15,
        reason: 'Casting',
        date: '2026-11-01',
        event_id: null,
      }),
    );
  });

  it('edits a manual award in the org timezone without sending user_id', async () => {
    vi.mocked(getEntries).mockResolvedValue({
      count: 1,
      limit: 50,
      offset: 0,
      results: [
        { ...entry(31, 'manual'), occurred_at: '2026-11-01T03:00:00Z' },
      ],
    });
    vi.mocked(updateManualAward).mockResolvedValue(entry(31, 'manual'));
    renderTab(admin, 'America/Chicago');
    fireEvent.click(await screen.findByTestId('ledger-edit-31'));
    expect(await screen.findByTestId('manual-award-edit-date')).toHaveValue(
      '2026-10-31',
    );
    fireEvent.change(screen.getByTestId('manual-award-edit-points'), {
      target: { value: '9' },
    });
    fireEvent.click(screen.getByTestId('manual-award-edit-submit'));
    await waitFor(() =>
      expect(updateManualAward).toHaveBeenCalledWith(7, 31, {
        points: 9,
        reason: 'Casting',
        date: '2026-10-31',
        event_id: null,
      }),
    );
  });

  it('deletes a manual award after confirmation', async () => {
    renderTab(admin);
    fireEvent.click(await screen.findByTestId('ledger-delete-31'));
    fireEvent.click(await screen.findByTestId('ledger-delete-confirm'));
    await waitFor(() => expect(deleteManualAward).toHaveBeenCalledWith(7, 31));
  });

  it('falls back to the last page when the current page empties', async () => {
    const pageTwo = {
      count: 51,
      limit: 50,
      offset: 50,
      results: [entry(99, 'manual')],
    };
    const pageOne = {
      count: 50,
      limit: 50,
      offset: 0,
      results: [entry(31, 'manual')],
    };
    vi.mocked(getEntries).mockImplementation(async (_orgId, filters) =>
      filters.offset === 0 ? { ...pageOne, count: pageTwo.count } : pageTwo,
    );
    renderTab(admin);
    fireEvent.click(await screen.findByTestId('ledger-next'));
    await screen.findByTestId('ledger-row-99');

    vi.mocked(getEntries).mockImplementation(async (_orgId, filters) =>
      filters.offset === 0
        ? pageOne
        : { count: 50, limit: 50, offset: filters.offset, results: [] },
    );
    fireEvent.click(screen.getByTestId('ledger-delete-99'));
    fireEvent.click(await screen.findByTestId('ledger-delete-confirm'));

    await screen.findByTestId('ledger-row-31');
    expect(getEntries).toHaveBeenLastCalledWith(
      7,
      expect.objectContaining({ offset: 0 }),
    );
    expect(screen.queryByText('No entries match these filters')).toBeNull();
  });
});

// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import {
  historyItem,
  memberConduct,
} from '~/features/conduct/__tests__/fixtures';
import { getMemberConduct } from '~/features/conduct/api';
import { HISTORY_PAGE_SIZE } from '~/features/conduct/schemas';
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
vi.mock('~/features/conduct/api', () => ({ getMemberConduct: vi.fn() }));

const SHOW_RATE: Metric = {
  key: 'show_rate',
  label: 'Show rate',
  format: 'percent',
  periodic: false,
  default: true,
};

function conductTrack(overrides: Partial<TrackInfo> = {}): TrackInfo {
  return {
    key: 'conduct',
    label: 'Conduct',
    metrics: [SHOW_RATE],
    can_view_rows: true,
    can_view_own: true,
    board_open: true,
    can_manage: false,
    ...overrides,
  };
}

function row(
  orgUserPk: number,
  value: number | null,
  status: StandingRow['status'] = 'ranked',
  sample = 5,
): StandingRow {
  return {
    member: {
      org_user_pk: orgUserPk,
      user_pk: orgUserPk + 100,
      username: `user${orgUserPk}`,
      nickname: null,
      avatarUrl: null,
    },
    value,
    sample,
    status,
  };
}

const member: OrgFeatureAccess = makeOrgFeatureAccess({
  viewerPk: 102,
  canViewConduct: true,
  canViewOwnConduct: true,
});
const staff: OrgFeatureAccess = makeOrgFeatureAccess({
  viewerPk: 900,
  canViewConduct: true,
  canViewOwnConduct: true,
  canViewConductDetails: true,
});

function respond(base: Partial<StandingLeaderboard> = {}) {
  vi.mocked(getStandingLeaderboard).mockImplementation(
    async (_orgId, trackKey, metric, period) => ({
      track: trackKey,
      metric,
      period,
      total: null,
      rows: [row(1, 0.91), row(2, 0.8), row(3, null, 'new', 1)],
      rows_visible: true,
      own_row: row(2, 0.8),
      ...base,
    }),
  );
}

function respondHistory() {
  vi.mocked(getMemberConduct).mockImplementation(async (_o, orgUserPk) =>
    memberConduct({
      member: {
        org_user_pk: orgUserPk,
        user_pk: orgUserPk + 100,
        username: `user${orgUserPk}`,
        nickname: null,
        discordNickname: null,
        guildNickname: null,
        avatarUrl: null,
      },
      history: Array.from({ length: HISTORY_PAGE_SIZE }, (_, i) =>
        historyItem({ event_id: orgUserPk * 1000 + i }),
      ),
    }),
  );
}

function renderTab(
  t: TrackInfo = conductTrack(),
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
  return {
    qc,
    ...render(
      <TrackTab
        orgId={7}
        track={t}
        timeZone="UTC"
        membersPrivate={false}
        access={viewer}
      />,
      { wrapper },
    ),
  };
}

function cells(testId: string): string[] {
  return within(screen.getByTestId(testId))
    .getAllByRole('cell')
    .map((c) => c.textContent ?? '');
}

afterEach(() => {
  vi.mocked(getStandingLeaderboard).mockReset();
  vi.mocked(getMemberConduct).mockReset();
});

describe('TrackTab conduct', () => {
  it('shows the public board and opens the own history by default', async () => {
    respond();
    respondHistory();
    renderTab();
    expect(await screen.findByTestId('conduct-tab')).toBeInTheDocument();
    expect(await screen.findByTestId('conduct-row-1-value')).toHaveTextContent(
      '91%',
    );
    expect(await screen.findByTestId('conduct-history')).toBeInTheDocument();
    expect(getMemberConduct).toHaveBeenCalledWith(7, 2, {
      limit: HISTORY_PAGE_SIZE,
      offset: 0,
    });
    expect(screen.queryByTestId('conduct-period-select')).toBeNull();
    expect(screen.queryByTestId('conduct-admin')).toBeNull();
  });

  it('shows a new row as New without a rank', async () => {
    respond();
    respondHistory();
    renderTab();
    expect(await screen.findByTestId('conduct-row-3-value')).toHaveTextContent(
      'New',
    );
    expect(cells('conduct-row-3')[0]).toBe('—');
  });

  it('opens nothing when a plain member clicks another row', async () => {
    respond();
    respondHistory();
    renderTab();
    await screen.findByTestId('conduct-history');
    fireEvent.click(await screen.findByTestId('conduct-row-1'));
    await waitFor(() =>
      expect(getMemberConduct).not.toHaveBeenCalledWith(
        7,
        1,
        expect.anything(),
      ),
    );
    expect(screen.getByTestId('conduct-history-row-2000')).toBeInTheDocument();
  });

  it("opens another member's history for staff", async () => {
    respond({ own_row: null });
    respondHistory();
    renderTab(conductTrack(), staff);
    fireEvent.click(await screen.findByTestId('conduct-row-1'));
    expect(
      await screen.findByTestId('conduct-history-row-1000'),
    ).toBeInTheDocument();
  });

  it('staff paging member A then opening member B requests offset=0', async () => {
    respond({ own_row: null });
    respondHistory();
    renderTab(conductTrack(), staff);
    fireEvent.click(await screen.findByTestId('conduct-row-1'));
    await screen.findByTestId('conduct-history-row-1000');
    fireEvent.click(screen.getByTestId('conduct-history-next'));
    await waitFor(() =>
      expect(getMemberConduct).toHaveBeenLastCalledWith(7, 1, {
        limit: HISTORY_PAGE_SIZE,
        offset: HISTORY_PAGE_SIZE,
      }),
    );
    fireEvent.click(screen.getByTestId('conduct-row-2'));
    await waitFor(() =>
      expect(getMemberConduct).toHaveBeenLastCalledWith(7, 2, {
        limit: HISTORY_PAGE_SIZE,
        offset: 0,
      }),
    );
  });

  it('tied rows share a rank', async () => {
    respond({ rows: [row(1, 0.9), row(2, 0.9), row(4, 0.7)] });
    respondHistory();
    renderTab();
    await screen.findByTestId('conduct-row-1');
    expect([1, 2, 4].map((pk) => cells(`conduct-row-${pk}`)[0])).toEqual([
      '1',
      '1',
      '2',
    ]);
  });

  it('shows the self-only note, own row and own history when the board is closed', async () => {
    respond({ rows: [], rows_visible: false, own_row: row(2, 0.8) });
    respondHistory();
    renderTab(conductTrack({ board_open: false, can_view_rows: false }));
    expect(await screen.findByTestId('conduct-self-only')).toBeInTheDocument();
    expect(await screen.findByTestId('conduct-row-2')).toBeInTheDocument();
    expect(await screen.findByTestId('conduct-history')).toBeInTheDocument();
    expect(screen.queryByTestId('conduct-error')).toBeNull();
    expect(screen.queryByTestId('conduct-members-only')).toBeNull();
    expect(screen.queryByTestId('conduct-members-private')).toBeNull();
  });

  it('keeps the own history closed after the viewer closes it', async () => {
    respond();
    respondHistory();
    const { qc } = renderTab();
    fireEvent.click(await screen.findByTestId('conduct-history-close'));
    expect(screen.queryByTestId('conduct-history')).toBeNull();
    const calls = vi.mocked(getStandingLeaderboard).mock.calls.length;
    await act(() => qc.invalidateQueries());
    await waitFor(() =>
      expect(
        vi.mocked(getStandingLeaderboard).mock.calls.length,
      ).toBeGreaterThan(calls),
    );
    await screen.findByTestId('conduct-row-2');
    expect(screen.queryByTestId('conduct-history')).toBeNull();
    fireEvent.click(screen.getByTestId('conduct-row-2'));
    expect(await screen.findByTestId('conduct-history')).toBeInTheDocument();
  });

  it('explains the rate next to the ranking for a viewer with no own row', async () => {
    respond({ own_row: null });
    respondHistory();
    renderTab(conductTrack(), makeOrgFeatureAccess({ viewerPk: 555 }));
    await screen.findByTestId('conduct-row-1');
    expect(screen.queryByTestId('conduct-history')).toBeNull();
    const trigger = screen.getByRole('button', {
      name: 'How the show rate works',
    });
    expect(trigger).toHaveAttribute('data-testid', 'conduct-rate-explainer');
    fireEvent.click(trigger);
    expect(
      await screen.findByTestId('conduct-rate-explainer-content'),
    ).toHaveTextContent(/late cancel/i);
  });

  it('marks a new member with a badge', async () => {
    respond();
    respondHistory();
    renderTab();
    const cell = await screen.findByTestId('conduct-row-3-value');
    expect(cell.querySelector('[data-slot="badge"]')).toHaveTextContent('New');
  });
});

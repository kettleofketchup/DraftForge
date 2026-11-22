// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import {
  cancelMmrRequest,
  fetchMyMmrRequests,
  fetchUserMmrSummary,
} from '../api';
import { OrgsMmrTab } from '../OrgsMmrTab';
import type { UserMmrSummary } from '../schemas';
import { mmrRequest, mmrSummary } from './fixtures';

vi.mock('../api', () => ({
  fetchUserMmrSummary: vi.fn(),
  fetchMyMmrRequests: vi.fn(),
  createMmrRequest: vi.fn(),
  cancelMmrRequest: vi.fn(),
  fetchMmrQueue: vi.fn(),
  fetchMmrPendingCount: vi.fn(),
  approveMmrRequest: vi.fn(),
  rejectMmrRequest: vi.fn(),
  staffSetMmr: vi.fn(),
  mmrScreenshotUrl: (id: number) => `/api/mmr-requests/${id}/screenshot/`,
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const SUBJECT = 42;

function renderTab(summary: UserMmrSummary, isOwnProfile: boolean) {
  vi.mocked(fetchUserMmrSummary).mockResolvedValue(summary);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <MemoryRouter>
          <OrgsMmrTab userPk={SUBJECT} isOwnProfile={isOwnProfile} />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

function withLastDecision(
  decision: UserMmrSummary['leagues'][number]['last_decision'],
): UserMmrSummary {
  const summary = mmrSummary();
  summary.leagues[0] = {
    ...summary.leagues[0],
    pending_request: null,
    last_decision: decision,
  };
  return summary;
}

beforeEach(() => {
  useUserStore.setState({ currentUser: { pk: SUBJECT } as UserType });
  vi.mocked(fetchMyMmrRequests).mockResolvedValue([]);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('OrgsMmrTab', () => {
  it('renders org blocks with game rows and nests a matching league', async () => {
    renderTab(mmrSummary(), true);
    const orgRow = await screen.findByTestId('mmr-row-org-3-1');
    expect(orgRow).toHaveTextContent('Dota 2');
    expect(orgRow).toHaveTextContent('4750');
    expect(screen.getByTestId('mmr-badge-official')).toBeInTheDocument();
    const block = screen.getByTestId('mmr-org-block-3');
    const leagueRow = screen.getByTestId('mmr-row-league-5');
    expect(block).toContainElement(leagueRow);
    expect(leagueRow).toHaveTextContent('Season 4');
    expect(leagueRow).toHaveTextContent('4900');
    expect(screen.queryByTestId('mmr-standalone-leagues')).toBeNull();
  });

  it('puts a league without a visible org in a Leagues group', async () => {
    const summary = mmrSummary();
    summary.leagues[0] = { ...summary.leagues[0], organization_pk: null };
    renderTab(summary, false);
    const group = await screen.findByTestId('mmr-standalone-leagues');
    expect(group).toHaveTextContent('Leagues');
    expect(group).toContainElement(screen.getByTestId('mmr-row-league-5'));
    expect(screen.getByTestId('mmr-org-block-3')).not.toContainElement(
      screen.getByTestId('mmr-row-league-5'),
    );
  });

  it('shows Not set for games without an MMR', async () => {
    const summary = mmrSummary();
    summary.orgs[0].game_mmrs.push({
      game_type: 2,
      mmr: 0,
      verified: false,
      verified_at: null,
      verified_by: null,
      legacy_verified: false,
      pending_request: null,
      last_decision: null,
    });
    renderTab(summary, true);
    const row = await screen.findByTestId('mmr-row-org-3-2');
    expect(row).toHaveTextContent('Not set');
    expect(screen.getByTestId('mmr-request-btn-org-3-2')).toBeInTheDocument();
  });

  it('shows request, cancel, pending and last decision only on your own profile', async () => {
    renderTab(mmrSummary(), true);
    expect(
      await screen.findByTestId('mmr-request-btn-org-3-1'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('mmr-request-btn-league-5')).toBeInTheDocument();
    expect(screen.getByTestId('mmr-pending-77')).toHaveTextContent('5100');
    expect(screen.getByTestId('mmr-cancel-btn-77')).toBeInTheDocument();
    expect(screen.getByTestId('mmr-last-decision-70')).toBeInTheDocument();
  });

  it('hides member actions and request state from other viewers', async () => {
    renderTab(mmrSummary(), false);
    await screen.findByTestId('mmr-row-org-3-1');
    expect(screen.queryByTestId('mmr-request-btn-org-3-1')).toBeNull();
    expect(screen.queryByTestId('mmr-request-btn-league-5')).toBeNull();
    expect(screen.queryByTestId('mmr-pending-77')).toBeNull();
    expect(screen.queryByTestId('mmr-cancel-btn-77')).toBeNull();
    expect(screen.queryByTestId('mmr-last-decision-70')).toBeNull();
    expect(fetchMyMmrRequests).not.toHaveBeenCalled();
  });

  it('describes a rejected decision with its reason', async () => {
    renderTab(mmrSummary(), true);
    const line = await screen.findByTestId('mmr-last-decision-70');
    expect(line).toHaveTextContent('Rejected 18 Nov 2026: Blurry');
  });

  it('describes an approved decision', async () => {
    renderTab(
      withLastDecision({
        id: 71,
        status: 'approved',
        decided_mmr: 4800,
        rejection_reason: '',
        reviewed_at: '2026-11-20T10:00:00Z',
      }),
      true,
    );
    const line = await screen.findByTestId('mmr-last-decision-71');
    expect(line).toHaveTextContent('Approved 4800 on 20 Nov 2026');
  });

  it('says when staff adjusted the approved value', async () => {
    vi.mocked(fetchMyMmrRequests).mockResolvedValue([
      mmrRequest({
        id: 71,
        status: 'approved',
        requested_mmr: 4800,
        approved_mmr: 4750,
      }),
    ]);
    renderTab(
      withLastDecision({
        id: 71,
        status: 'approved',
        decided_mmr: 4750,
        rejection_reason: '',
        reviewed_at: '2026-11-20T10:00:00Z',
      }),
      true,
    );
    const line = await screen.findByTestId('mmr-last-decision-71');
    await waitFor(() =>
      expect(line).toHaveTextContent('approved as 4750, you asked 4800'),
    );
  });

  it('describes a superseded decision', async () => {
    renderTab(
      withLastDecision({
        id: 72,
        status: 'superseded',
        decided_mmr: 5000,
        rejection_reason: '',
        reviewed_at: '2026-11-19T10:00:00Z',
      }),
      true,
    );
    const line = await screen.findByTestId('mmr-last-decision-72');
    expect(line).toHaveTextContent(
      'Replaced by a staff-set value of 5000 on 19 Nov 2026',
    );
  });

  it('shows the empty state for other viewers', async () => {
    renderTab({ user_pk: SUBJECT, orgs: [], leagues: [] }, false);
    expect(
      await screen.findByText('No public org memberships'),
    ).toBeInTheDocument();
  });

  it('shows the empty state on your own profile', async () => {
    renderTab({ user_pk: SUBJECT, orgs: [], leagues: [] }, true);
    expect(
      await screen.findByText("You're not in any orgs yet"),
    ).toBeInTheDocument();
  });

  it('cancels a pending request after confirming', async () => {
    vi.mocked(cancelMmrRequest).mockResolvedValue(
      mmrRequest({ id: 77, status: 'cancelled' }),
    );
    renderTab(mmrSummary(), true);
    fireEvent.click(await screen.findByTestId('mmr-cancel-btn-77'));
    expect(cancelMmrRequest).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByTestId('mmr-cancel-confirm'));
    await waitFor(() => expect(cancelMmrRequest).toHaveBeenCalledWith(77));
  });

  it('opens the request dialog for a row', async () => {
    renderTab(mmrSummary(), true);
    fireEvent.click(await screen.findByTestId('mmr-request-btn-org-3-1'));
    expect(
      await screen.findByText('Request MMR update — Org X · Dota 2'),
    ).toBeInTheDocument();
  });
});

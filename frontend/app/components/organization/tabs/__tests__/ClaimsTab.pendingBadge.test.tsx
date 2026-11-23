// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getClaimRequests } from '~/features/claims/api';
import type { ProfileClaimRequest } from '~/features/claims/schemas';
import { ClaimsTab } from '../ClaimsTab';

vi.mock('~/components/user/UserAvatar', () => ({ UserAvatar: () => null }));
vi.mock('~/features/claims/api', () => ({ getClaimRequests: vi.fn() }));

function claim(
  id: number,
  status: ProfileClaimRequest['status'],
): ProfileClaimRequest {
  return {
    id,
    claimer: 10 + id,
    claimer_username: `claimer${id}`,
    claimer_discord_id: null,
    claimer_avatar: null,
    target_user: 20 + id,
    target_nickname: `Target${id}`,
    target_steamid: null,
    target_mmr: null,
    organization: 1,
    organization_name: 'Org',
    status,
    reviewed_by: null,
    reviewed_by_username: null,
    rejection_reason: '',
    created_at: '2026-01-01T00:00:00Z',
    reviewed_at: null,
  };
}

type ByStatus = Record<ProfileClaimRequest['status'], ProfileClaimRequest[]>;

const defaultClaims: ByStatus = {
  pending: [claim(1, 'pending'), claim(2, 'pending'), claim(3, 'pending')],
  approved: [claim(4, 'approved')],
  rejected: [],
};

function renderTab(byStatus: ByStatus = defaultClaims) {
  vi.mocked(getClaimRequests).mockImplementation(async ({ status }) =>
    status ? byStatus[status] : [],
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ClaimsTab organizationId={1} />
    </QueryClientProvider>,
  );
}

function selectFilter(testId: string) {
  const trigger = screen.getByTestId(testId);
  fireEvent.mouseDown(trigger, { button: 0 });
  fireEvent.click(trigger);
}

afterEach(() => {
  vi.mocked(getClaimRequests).mockReset();
});

describe('ClaimsTab pending badge', () => {
  it('shows the pending count on the Pending filter', async () => {
    renderTab();
    await waitFor(() =>
      expect(screen.getByTestId('claims-pending-count').textContent).toBe('3'),
    );
  });

  it('keeps the pending count when another filter is selected', async () => {
    renderTab();
    await screen.findByTestId('claims-list');
    selectFilter('claims-tab-approved');
    await waitFor(() =>
      expect(getClaimRequests).toHaveBeenCalledWith({
        organizationId: 1,
        status: 'approved',
      }),
    );
    await waitFor(() =>
      expect(screen.getAllByTestId(/^claim-card/).length).toBe(1),
    );
    expect(screen.getByTestId('claims-pending-count').textContent).toBe('3');

    selectFilter('claims-tab-rejected');
    await screen.findByTestId('claims-empty');
    expect(screen.getByTestId('claims-pending-count').textContent).toBe('3');
  });

  it('hides the badge when nothing is pending', async () => {
    renderTab({ ...defaultClaims, pending: [] });
    await screen.findByTestId('claims-empty');
    expect(screen.queryByTestId('claims-pending-count')).toBeNull();
  });
});

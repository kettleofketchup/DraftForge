// @vitest-environment jsdom
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { UserType } from '~/components/user/types';
import { useOrgStore } from '~/store/orgStore';
import { useUserStore } from '~/store/userStore';
import * as api from '../api';
import { MmrRequestsTab } from '../MmrRequestsTab';
import { mmrRequest } from './fixtures';
import { installDomStubs, renderWithClient } from './harness';

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    fetchMmrQueue: vi.fn(),
    fetchMmrPendingCount: vi.fn(),
    approveMmrRequest: vi.fn(),
    rejectMmrRequest: vi.fn(),
  };
});

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const SCOPE = { org: 3 };

beforeEach(() => {
  installDomStubs();
  useUserStore.setState({ currentUser: { pk: 9 } as UserType });
  vi.mocked(api.fetchMmrPendingCount).mockResolvedValue({ count: 1 });
  vi.mocked(api.fetchMmrQueue).mockResolvedValue([
    mmrRequest({ current_mmr: 3900, requested_mmr: 4800 }),
  ]);
  vi.mocked(api.approveMmrRequest).mockResolvedValue(
    mmrRequest({ status: 'approved', approved_mmr: 4750 }),
  );
  vi.mocked(api.rejectMmrRequest).mockResolvedValue(
    mmrRequest({ status: 'rejected' }),
  );
});

afterEach(() => {
  vi.clearAllMocks();
});

async function renderTab() {
  renderWithClient(<MmrRequestsTab scope={SCOPE} />);
  return screen.findByTestId('mmr-card-77');
}

describe('MmrRequestsTab', () => {
  it('loads pending requests and switches status', async () => {
    await renderTab();
    expect(api.fetchMmrQueue).toHaveBeenCalledWith(SCOPE, 'pending');
    vi.mocked(api.fetchMmrQueue).mockResolvedValueOnce([]);
    fireEvent.mouseDown(screen.getByTestId('mmr-queue-status-approved'), {
      button: 0,
    });
    await waitFor(() =>
      expect(api.fetchMmrQueue).toHaveBeenCalledWith(SCOPE, 'approved'),
    );
    expect(await screen.findByTestId('mmr-queue-empty')).toHaveTextContent(
      'No approved MMR requests',
    );
  });

  it('shows the pending count on the pending filter', async () => {
    await renderTab();
    await waitFor(() =>
      expect(screen.getByTestId('mmr-queue-status-pending')).toHaveTextContent(
        'Pending1',
      ),
    );
  });

  it('shows the pending count in the mobile status picker', async () => {
    await renderTab();
    await waitFor(() =>
      expect(screen.getAllByText('Pending (1)').length).toBeGreaterThan(0),
    );
  });

  it('approves an adjusted large change after a second confirm', async () => {
    await renderTab();
    fireEvent.click(screen.getByTestId('mmr-approve-btn-77'));
    const value = await screen.findByTestId('mmr-approve-value');
    expect(value).toHaveValue(4800);
    fireEvent.change(value, { target: { value: '4750' } });
    expect(screen.getByTestId('mmr-approve-delta')).toHaveTextContent(
      '3900 → 4750 (+850, 22%)',
    );
    fireEvent.click(screen.getByTestId('mmr-approve-confirm'));
    const anyway = await screen.findByTestId('mmr-approve-anyway');
    expect(anyway).toHaveTextContent('Approve anyway');
    expect(api.approveMmrRequest).not.toHaveBeenCalled();
    fireEvent.click(anyway);
    await waitFor(() =>
      expect(api.approveMmrRequest).toHaveBeenCalledWith(77, 4750),
    );
  });

  it('approves a small change without the second confirm', async () => {
    vi.mocked(api.fetchMmrQueue).mockResolvedValue([
      mmrRequest({ current_mmr: 4600, requested_mmr: 4800 }),
    ]);
    await renderTab();
    fireEvent.click(screen.getByTestId('mmr-approve-btn-77'));
    fireEvent.click(await screen.findByTestId('mmr-approve-confirm'));
    await waitFor(() =>
      expect(api.approveMmrRequest).toHaveBeenCalledWith(77, undefined),
    );
    expect(screen.queryByTestId('mmr-approve-anyway')).not.toBeInTheDocument();
  });

  it('requires a rejection reason before confirming', async () => {
    await renderTab();
    fireEvent.click(screen.getByTestId('mmr-reject-btn-77'));
    const confirm = await screen.findByTestId('mmr-reject-confirm');
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByTestId('mmr-reject-reason'), {
      target: { value: '   ' },
    });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByTestId('mmr-reject-reason'), {
      target: { value: ' Blurry ' },
    });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await waitFor(() =>
      expect(api.rejectMmrRequest).toHaveBeenCalledWith(77, 'Blurry'),
    );
  });

  it('opens the set official dialog with a member picker', async () => {
    const getOrgUsers = vi.fn().mockResolvedValue(undefined);
    useOrgStore.setState({ getOrgUsers });
    await renderTab();
    expect(getOrgUsers).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('set-official-mmr-open'));
    expect(
      await screen.findByTestId('set-official-mmr-member'),
    ).toBeInTheDocument();
    expect(getOrgUsers).toHaveBeenCalledWith(3);
  });
});

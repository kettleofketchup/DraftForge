// @vitest-environment jsdom
import {
  QueryClient,
  QueryClientProvider,
  focusManager,
} from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { contributionsKeys, standingKeys } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { getCandidates, sendPromo, undoPromoSend } from '../api';
import {
  CANDIDATE_POLL_MS,
  useCandidates,
  useSendPromo,
  useUndoPromoSend,
} from '../queries';
import { DEFAULT_CANDIDATE_FILTERS } from '../schemas';
import { SYNC_CONFIGURED, candidateRow, candidatesResponse } from './fixtures';

vi.mock('../api', () => ({
  getCandidates: vi.fn(),
  sendPromo: vi.fn(),
  undoPromoSend: vi.fn(),
}));

const access = makeOrgFeatureAccess({
  viewerPk: 5,
  canUsePromotion: true,
  canViewContributions: true,
});

const LEADERBOARD = contributionsKeys.leaderboard(1, 5, 'all');
const STANDING = standingKeys.leaderboard(
  1,
  5,
  'contribution',
  'points',
  'all',
);

function setup(): {
  qc: QueryClient;
  wrapper: (props: { children: ReactNode }) => ReactNode;
} {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
  });
  qc.setQueryData(LEADERBOARD, { total: 120 });
  qc.setQueryData(STANDING, { total: 120 });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

let unmountCandidates: (() => void) | null = null;

afterEach(() => {
  unmountCandidates?.();
  unmountCandidates = null;
  vi.mocked(getCandidates).mockReset();
  vi.mocked(sendPromo).mockReset();
  vi.mocked(undoPromoSend).mockReset();
  vi.useRealTimers();
  focusManager.setFocused(undefined);
});

describe('candidate refresh', () => {
  function renderCandidates(): void {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { unmount } = renderHook(
      () => useCandidates(1, access, 9, DEFAULT_CANDIDATE_FILTERS),
      { wrapper },
    );
    unmountCandidates = unmount;
  }

  async function settle(calls: number): Promise<void> {
    await waitFor(() => expect(getCandidates).toHaveBeenCalledTimes(calls));
  }

  it('polls every 30 seconds while visible when the integration is configured', async () => {
    expect(CANDIDATE_POLL_MS).toBe(30_000);
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    focusManager.setFocused(true);
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([candidateRow()], { contact_sync: SYNC_CONFIGURED }),
    );
    renderCandidates();
    await settle(1);
    await act(async () => {
      vi.advanceTimersByTime(CANDIDATE_POLL_MS - 1);
    });
    expect(getCandidates).toHaveBeenCalledTimes(1);
    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    await settle(2);
  });

  it('does not poll while the page is hidden, and refetches on focus', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    focusManager.setFocused(true);
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([candidateRow()], { contact_sync: SYNC_CONFIGURED }),
    );
    renderCandidates();
    await settle(1);
    act(() => focusManager.setFocused(false));
    await act(async () => {
      vi.advanceTimersByTime(CANDIDATE_POLL_MS * 3);
    });
    expect(getCandidates).toHaveBeenCalledTimes(1);
    await act(async () => {
      focusManager.setFocused(true);
    });
    await settle(2);
  });

  it('does not poll for an org without the integration', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    focusManager.setFocused(true);
    vi.mocked(getCandidates).mockResolvedValue(
      candidatesResponse([candidateRow()]),
    );
    renderCandidates();
    await settle(1);
    await act(async () => {
      vi.advanceTimersByTime(CANDIDATE_POLL_MS * 3);
    });
    expect(getCandidates).toHaveBeenCalledTimes(1);
  });
});

describe('promotion mutations', () => {
  it('marks cached contributions stale after a send', async () => {
    vi.mocked(sendPromo).mockResolvedValue({
      id: 77,
      earns_points: true,
      points_awarded: 5,
      sent_at: '2026-11-14T00:00:00Z',
      writeback: { state: 'pending', reason: null, delivery_id: 'd-77' },
    });
    const { qc, wrapper } = setup();
    const { result } = renderHook(() => useSendPromo(1, access, 9), {
      wrapper,
    });
    await act(async () => {
      await result.current.mutateAsync({
        template_id: 3,
        recipient_id: 42,
        text: 'Hi',
      });
    });
    await waitFor(() => {
      expect(qc.getQueryState(LEADERBOARD)?.isInvalidated).toBe(true);
      expect(qc.getQueryState(STANDING)?.isInvalidated).toBe(true);
    });
  });

  it('marks cached contributions stale after an undo', async () => {
    vi.mocked(undoPromoSend).mockResolvedValue({
      writeback: { state: 'pending', reason: null, delivery_id: 'd-77' },
    });
    const { qc, wrapper } = setup();
    const { result } = renderHook(() => useUndoPromoSend(1, access), {
      wrapper,
    });
    await act(async () => {
      await result.current.mutateAsync(77);
    });
    await waitFor(() => {
      expect(qc.getQueryState(LEADERBOARD)?.isInvalidated).toBe(true);
      expect(qc.getQueryState(STANDING)?.isInvalidated).toBe(true);
    });
  });
});

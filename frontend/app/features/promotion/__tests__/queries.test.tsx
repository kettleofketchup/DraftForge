// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { contributionsKeys, standingKeys } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { sendPromo, undoPromoSend } from '../api';
import { useSendPromo, useUndoPromoSend } from '../queries';

vi.mock('../api', () => ({
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

afterEach(() => {
  vi.mocked(sendPromo).mockReset();
  vi.mocked(undoPromoSend).mockReset();
});

describe('promotion mutations', () => {
  it('marks cached contributions stale after a send', async () => {
    vi.mocked(sendPromo).mockResolvedValue({
      id: 77,
      earns_points: true,
      points_awarded: 5,
      sent_at: '2026-11-14T00:00:00Z',
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
    vi.mocked(undoPromoSend).mockResolvedValue(undefined);
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

// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { standingKeys } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import { getStandingLeaderboard } from '../api';
import { useStandingLeaderboard } from '../queries';
import type { Metric, StandingLeaderboard, TrackInfo } from '../schemas';

vi.mock('../api', () => ({ getStandingLeaderboard: vi.fn() }));

const showRate: Metric = {
  key: 'show_rate',
  label: 'Show rate',
  format: 'percent',
  periodic: false,
  default: true,
};

const conduct: TrackInfo = {
  key: 'conduct',
  label: 'Conduct',
  metrics: [showRate],
  can_view_rows: true,
  can_view_own: true,
  board_open: true,
  can_manage: false,
  can_moderate: false,
  own_private: false,
};

const board: StandingLeaderboard = {
  track: 'conduct',
  metric: showRate,
  period: 'all',
  total: null,
  rows: [],
  rows_visible: true,
  own_row: null,
  own_private: false,
};

function setup(): {
  qc: QueryClient;
  wrapper: (props: { children: ReactNode }) => ReactNode;
} {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

beforeEach(() => {
  vi.mocked(getStandingLeaderboard).mockResolvedValue(board);
});

afterEach(() => {
  vi.mocked(getStandingLeaderboard).mockReset();
});

describe('useStandingLeaderboard', () => {
  it('does not fetch until access is settled', async () => {
    const { wrapper } = setup();
    const access = makeOrgFeatureAccess({ settled: false });
    const { result } = renderHook(
      () => useStandingLeaderboard(1, access, conduct, showRate, '2026-10'),
      { wrapper },
    );
    await Promise.resolve();
    expect(result.current.fetchStatus).toBe('idle');
    expect(getStandingLeaderboard).not.toHaveBeenCalled();
  });

  it('does not fetch a track the viewer cannot see', async () => {
    const { wrapper } = setup();
    const hidden = { ...conduct, board_open: false, can_view_own: false };
    const { result } = renderHook(
      () =>
        useStandingLeaderboard(
          1,
          makeOrgFeatureAccess(),
          hidden,
          showRate,
          '2026-10',
        ),
      { wrapper },
    );
    await Promise.resolve();
    expect(result.current.fetchStatus).toBe('idle');
    expect(getStandingLeaderboard).not.toHaveBeenCalled();
  });

  it('fetches when only the own row is visible', async () => {
    const { wrapper } = setup();
    const own = { ...conduct, board_open: false, can_view_own: true };
    const { result } = renderHook(
      () =>
        useStandingLeaderboard(1, makeOrgFeatureAccess(), own, showRate, 'all'),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getStandingLeaderboard).toHaveBeenCalledWith(
      1,
      'conduct',
      showRate,
      'all',
    );
  });

  it('keys the cache by viewer', async () => {
    const { qc, wrapper } = setup();
    for (const viewerPk of [5, 6]) {
      const { result } = renderHook(
        () =>
          useStandingLeaderboard(
            1,
            makeOrgFeatureAccess({ viewerPk }),
            conduct,
            showRate,
            'all',
          ),
        { wrapper },
      );
      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    }
    expect(getStandingLeaderboard).toHaveBeenCalledTimes(2);
    expect(
      qc.getQueryData(
        standingKeys.leaderboard(1, 5, 'conduct', 'show_rate', 'current'),
      ),
    ).toEqual(board);
    expect(
      qc.getQueryData(
        standingKeys.leaderboard(1, 6, 'conduct', 'show_rate', 'current'),
      ),
    ).toEqual(board);
  });

  it('does not refetch when the period changes on a non-periodic metric', async () => {
    const { wrapper } = setup();
    const access = makeOrgFeatureAccess();
    const { result, rerender } = renderHook(
      ({ period }: { period: string }) =>
        useStandingLeaderboard(1, access, conduct, showRate, period),
      { wrapper, initialProps: { period: '2026-10' } },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    rerender({ period: '2026-09' });
    await Promise.resolve();
    expect(result.current.fetchStatus).toBe('idle');
    expect(getStandingLeaderboard).toHaveBeenCalledTimes(1);
  });
});

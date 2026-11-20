// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { conductKeys, type OrgFeatureAccess } from '~/features/org-features';
import {
  getConductLeaderboard,
  getConductSettings,
  getMemberConduct,
  putAttendance,
} from '../api';
import {
  useConductLeaderboard,
  useConductSettings,
  useMemberConduct,
  usePutAttendance,
} from '../queries';
import type { MemberConduct } from '../schemas';

vi.mock('../api', () => ({
  getConductLeaderboard: vi.fn(),
  getMemberConduct: vi.fn(),
  getConductSettings: vi.fn(),
  patchConductSettings: vi.fn(),
  getAttendance: vi.fn(),
  putAttendance: vi.fn(),
  getForecast: vi.fn(),
}));

const access: OrgFeatureAccess = {
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

const LEADERBOARD = conductKeys.leaderboard(1, 5);

function setup(): {
  qc: QueryClient;
  wrapper: (props: { children: ReactNode }) => ReactNode;
} {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

afterEach(() => {
  vi.mocked(getConductLeaderboard).mockReset();
  vi.mocked(getMemberConduct).mockReset();
  vi.mocked(getConductSettings).mockReset();
  vi.mocked(putAttendance).mockReset();
});

describe('conduct queries', () => {
  it('loads the leaderboard in self-only mode', async () => {
    vi.mocked(getConductLeaderboard).mockResolvedValue({
      rows_visible: false,
      rows: [],
      new_members: [],
      own_row: null,
    });
    const { wrapper } = setup();
    const { result } = renderHook(() => useConductLeaderboard(1, access), {
      wrapper,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getConductLeaderboard).toHaveBeenCalledWith(1);
  });

  it('waits for a member pk before loading history', () => {
    const { wrapper } = setup();
    renderHook(
      () => useMemberConduct(1, access, null, { limit: 50, offset: 0 }),
      { wrapper },
    );
    expect(getMemberConduct).not.toHaveBeenCalled();
  });

  it('keeps the previous history page while the next one loads', async () => {
    const first = { history: [], page: 0 } as unknown as MemberConduct;
    vi.mocked(getMemberConduct)
      .mockResolvedValueOnce(first)
      .mockReturnValueOnce(new Promise(() => {}))
      .mockReturnValueOnce(new Promise(() => {}));
    const { wrapper } = setup();
    const { result, rerender } = renderHook(
      ({ pk, offset }: { pk: number; offset: number }) =>
        useMemberConduct(1, access, pk, { limit: 50, offset }),
      { wrapper, initialProps: { pk: 3, offset: 0 } },
    );
    await waitFor(() => expect(result.current.data).toBe(first));

    rerender({ pk: 3, offset: 50 });
    expect(result.current.data).toBe(first);
    expect(result.current.isPlaceholderData).toBe(true);

    rerender({ pk: 4, offset: 0 });
    expect(result.current.data).toBeUndefined();
  });

  it('does not load settings without manage access', () => {
    const { wrapper } = setup();
    renderHook(() => useConductSettings(1, access), { wrapper });
    expect(getConductSettings).not.toHaveBeenCalled();
  });

  it('marks cached conduct stale after an attendance save', async () => {
    vi.mocked(putAttendance).mockResolvedValue({
      event_id: 9,
      state: 'roll_call',
      finalized_at: null,
      editable: true,
      editable_reason: null,
      rows: [],
    });
    const { qc, wrapper } = setup();
    qc.setQueryData(LEADERBOARD, { rows_visible: true });
    const { result } = renderHook(() => usePutAttendance(1, access, 9), {
      wrapper,
    });
    await act(async () => {
      await result.current.mutateAsync({
        changes: [{ org_user_pk: 3, outcome: 'no_show' }],
        reason: 'Absent',
      });
    });
    expect(putAttendance).toHaveBeenCalledWith(1, 9, {
      changes: [{ org_user_pk: 3, outcome: 'no_show' }],
      reason: 'Absent',
    });
    await waitFor(() =>
      expect(qc.getQueryState(LEADERBOARD)?.isInvalidated).toBe(true),
    );
  });
});

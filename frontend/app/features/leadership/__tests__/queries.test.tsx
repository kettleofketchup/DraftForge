// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { leadershipKeys, standingKeys } from '~/features/org-features';
import { makeOrgFeatureAccess } from '~/features/org-features/__tests__/makeOrgFeatureAccess';
import {
  deleteReview,
  deleteTrait,
  getEventReviews,
  getLeadershipSettings,
  getMemberLeadership,
  getMyReviews,
  getPendingReviews,
  getTraits,
  patchLeadershipSettings,
  putReview,
  putTraits,
  releaseResults,
  voidReview,
} from '../api';
import {
  useDeleteTrait,
  useEventReviews,
  useLeadershipSettings,
  useLeadershipTraits,
  useMemberLeadership,
  useMyReviews,
  usePatchLeadershipSettings,
  usePendingReviews,
  usePutTraits,
  useReleaseResults,
  useSubmitReview,
  useVoidReview,
  useWithdrawReview,
} from '../queries';
import {
  leadershipFeatureAccess,
  leadershipSettings,
  memberLeadership,
  moderationReview,
  pendingReview,
  traits,
} from './fixtures';

vi.mock('../api', () => ({
  deleteReview: vi.fn(),
  deleteTrait: vi.fn(),
  getEventReviews: vi.fn(),
  getLeadershipSettings: vi.fn(),
  getMemberLeadership: vi.fn(),
  getMyReviews: vi.fn(),
  getPendingReviews: vi.fn(),
  getTraits: vi.fn(),
  patchLeadershipSettings: vi.fn(),
  putReview: vi.fn(),
  putTraits: vi.fn(),
  releaseResults: vi.fn(),
  unvoidReview: vi.fn(),
  voidReview: vi.fn(),
}));

const ORG = 4;
const EVENT = 5;
const VIEWER = 9;

const memberAccess = leadershipFeatureAccess({ viewerPk: VIEWER });
const adminAccess = leadershipFeatureAccess({
  viewerPk: VIEWER,
  track: { can_manage: true, can_moderate: true },
});
const staffAccess = leadershipFeatureAccess({
  viewerPk: VIEWER,
  track: { can_moderate: true, can_manage: false },
});

function makeClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

function seeded() {
  const { client, wrapper } = makeClient();
  const keys = {
    member: leadershipKeys.member(ORG, VIEWER, 7),
    pending: leadershipKeys.pending(ORG, VIEWER, null),
    mine: leadershipKeys.mine(ORG, VIEWER),
    eventReviews: leadershipKeys.eventReviews(ORG, VIEWER, EVENT),
    settings: leadershipKeys.settings(ORG, VIEWER),
    traits: leadershipKeys.traits(ORG, VIEWER),
    leadershipBoard: standingKeys.leaderboard(
      ORG,
      VIEWER,
      'leadership',
      'rating',
      'current',
    ),
    conductBoard: standingKeys.leaderboard(
      ORG,
      VIEWER,
      'conduct',
      'show_rate',
      'current',
    ),
    event: ['event', EVENT] as const,
    org: ['organization', ORG] as const,
  };
  for (const key of Object.values(keys)) client.setQueryData(key, {});
  const invalid = (key: readonly unknown[]) =>
    client.getQueryState(key)?.isInvalidated ?? false;
  return { client, wrapper, keys, invalid };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('review mutations', () => {
  it('submit invalidates pending, member, leadership boards and the event', async () => {
    vi.mocked(putReview).mockResolvedValue({
      submitted_at: '2026-11-02T10:00:00Z',
      updated_at: '2026-11-02T10:00:00Z',
      scores: { communication: 4 },
    } as never);
    const { wrapper, keys, invalid } = seeded();
    const hook = renderHook(() => useSubmitReview(ORG), {
      wrapper,
    });
    await act(() =>
      hook.result.current.mutateAsync({
        eventId: EVENT,
        captainOrgUserId: 7,
        scores: { communication: 4 },
      }),
    );
    expect(putReview).toHaveBeenCalledWith(ORG, EVENT, 7, {
      communication: 4,
    });
    expect(invalid(keys.pending)).toBe(true);
    expect(invalid(keys.member)).toBe(true);
    expect(invalid(keys.mine)).toBe(true);
    expect(invalid(keys.leadershipBoard)).toBe(true);
    expect(invalid(keys.event)).toBe(true);
    expect(invalid(keys.conductBoard)).toBe(false);
  });

  it('review submit does not refetch the org payload', async () => {
    vi.mocked(putReview).mockResolvedValue({} as never);
    const { wrapper, keys, invalid } = seeded();
    const hook = renderHook(() => useSubmitReview(ORG), {
      wrapper,
    });
    await act(() =>
      hook.result.current.mutateAsync({
        eventId: EVENT,
        captainOrgUserId: 7,
        scores: {},
      }),
    );
    expect(invalid(keys.org)).toBe(false);
  });

  it('withdraw invalidates the same keys', async () => {
    vi.mocked(deleteReview).mockResolvedValue(undefined);
    const { wrapper, keys, invalid } = seeded();
    const hook = renderHook(() => useWithdrawReview(ORG), {
      wrapper,
    });
    await act(() =>
      hook.result.current.mutateAsync({ eventId: EVENT, captainOrgUserId: 7 }),
    );
    expect(deleteReview).toHaveBeenCalledWith(ORG, EVENT, 7);
    expect(invalid(keys.pending)).toBe(true);
    expect(invalid(keys.member)).toBe(true);
    expect(invalid(keys.leadershipBoard)).toBe(true);
    expect(invalid(keys.event)).toBe(true);
    expect(invalid(keys.org)).toBe(false);
  });

  it('void invalidates event reviews and leadership boards but not conduct', async () => {
    vi.mocked(voidReview).mockResolvedValue(
      moderationReview({ void_kind: 'moderated' }),
    );
    const { wrapper, keys, invalid } = seeded();
    const hook = renderHook(() => useVoidReview(ORG, EVENT), {
      wrapper,
    });
    await act(() =>
      hook.result.current.mutateAsync({ reviewPk: 31, reason: 'Abuse' }),
    );
    expect(voidReview).toHaveBeenCalledWith(ORG, 31, 'Abuse');
    expect(invalid(keys.eventReviews)).toBe(true);
    expect(invalid(keys.leadershipBoard)).toBe(true);
    expect(invalid(keys.event)).toBe(true);
    expect(invalid(keys.conductBoard)).toBe(false);
  });
});

describe('release mutation', () => {
  it('posts the captains and invalidates leadership, standing and the event but not the org', async () => {
    vi.mocked(releaseResults).mockResolvedValue({ released: [7], skipped: [] });
    const { wrapper, keys, invalid } = seeded();
    const hook = renderHook(() => useReleaseResults(ORG, EVENT), { wrapper });
    await act(() => hook.result.current.mutateAsync({ captains: [7] }));
    expect(releaseResults).toHaveBeenCalledWith(ORG, EVENT, [7]);
    expect(invalid(keys.eventReviews)).toBe(true);
    expect(invalid(keys.member)).toBe(true);
    expect(invalid(keys.leadershipBoard)).toBe(true);
    expect(invalid(keys.event)).toBe(true);
    expect(invalid(keys.org)).toBe(false);
    expect(invalid(keys.conductBoard)).toBe(false);
  });

  it('releases the whole event without captains', async () => {
    vi.mocked(releaseResults).mockResolvedValue({ released: [], skipped: [] });
    const { wrapper } = seeded();
    const hook = renderHook(() => useReleaseResults(ORG, EVENT), { wrapper });
    await act(() => hook.result.current.mutateAsync({}));
    expect(releaseResults).toHaveBeenCalledWith(ORG, EVENT, undefined);
  });

  it('invalidates after a refused release', async () => {
    vi.mocked(releaseResults).mockRejectedValue(new Error('409'));
    const { wrapper, keys, invalid } = seeded();
    const hook = renderHook(() => useReleaseResults(ORG, EVENT), { wrapper });
    await act(async () => {
      await hook.result.current.mutateAsync({}).catch(() => {});
    });
    expect(invalid(keys.eventReviews)).toBe(true);
    expect(invalid(keys.org)).toBe(false);
  });
});

describe('settings and traits', () => {
  it('settings save keeps the fresh settings and invalidates the rest', async () => {
    const saved = leadershipSettings({ review_window_hours: 24 });
    vi.mocked(patchLeadershipSettings).mockResolvedValue(saved);
    const { client, wrapper, keys, invalid } = seeded();
    const hook = renderHook(
      () => usePatchLeadershipSettings(ORG, adminAccess),
      {
        wrapper,
      },
    );
    await act(() =>
      hook.result.current.mutateAsync({ review_window_hours: 24 }),
    );
    expect(client.getQueryData(keys.settings)).toEqual(saved);
    expect(invalid(keys.settings)).toBe(false);
    expect(invalid(keys.member)).toBe(true);
    expect(invalid(keys.leadershipBoard)).toBe(true);
  });

  it('settings save refreshes the org payload', async () => {
    vi.mocked(patchLeadershipSettings).mockResolvedValue(leadershipSettings());
    const { wrapper, keys, invalid } = seeded();
    const hook = renderHook(
      () => usePatchLeadershipSettings(ORG, adminAccess),
      {
        wrapper,
      },
    );
    await act(() =>
      hook.result.current.mutateAsync({ leaderboard_public: true }),
    );
    expect(invalid(keys.org)).toBe(true);
  });

  it('resyncs settings after a failed save', async () => {
    vi.mocked(patchLeadershipSettings).mockRejectedValue(new Error('400'));
    const { wrapper, keys, invalid } = seeded();
    const hook = renderHook(
      () => usePatchLeadershipSettings(ORG, adminAccess),
      {
        wrapper,
      },
    );
    await act(async () => {
      await hook.result.current
        .mutateAsync({ review_window_hours: 999 })
        .catch(() => {});
    });
    expect(invalid(keys.settings)).toBe(true);
    expect(invalid(keys.org)).toBe(true);
  });

  it('put traits invalidates leadership standing boards', async () => {
    const saved = traits().traits;
    vi.mocked(putTraits).mockResolvedValue(saved);
    const { client, wrapper, keys, invalid } = seeded();
    const hook = renderHook(() => usePutTraits(ORG, adminAccess), { wrapper });
    await act(() => hook.result.current.mutateAsync(saved));
    expect(putTraits).toHaveBeenCalledWith(ORG, saved);
    expect(client.getQueryData(keys.traits)).toEqual(saved);
    expect(invalid(keys.traits)).toBe(false);
    expect(invalid(keys.leadershipBoard)).toBe(true);
    expect(invalid(keys.member)).toBe(true);
    expect(invalid(keys.conductBoard)).toBe(false);
  });

  it('put traits refreshes the org payload so new trait metrics appear', async () => {
    vi.mocked(putTraits).mockResolvedValue(traits().traits);
    const { wrapper, keys, invalid } = seeded();
    const hook = renderHook(() => usePutTraits(ORG, adminAccess), { wrapper });
    await act(() => hook.result.current.mutateAsync(traits().traits));
    expect(invalid(keys.org)).toBe(true);
    expect(invalid(['organization', 8])).toBe(false);
  });

  it('delete trait refreshes the org payload', async () => {
    vi.mocked(deleteTrait).mockResolvedValue(undefined);
    const { wrapper, keys, invalid } = seeded();
    const hook = renderHook(() => useDeleteTrait(ORG), {
      wrapper,
    });
    await act(() => hook.result.current.mutateAsync('drafting'));
    expect(deleteTrait).toHaveBeenCalledWith(ORG, 'drafting');
    expect(invalid(keys.org)).toBe(true);
    expect(invalid(keys.traits)).toBe(true);
    expect(invalid(keys.leadershipBoard)).toBe(true);
  });

  it('a refused trait delete leaves the org payload alone', async () => {
    vi.mocked(deleteTrait).mockRejectedValue(new Error('409'));
    const { wrapper, keys, invalid } = seeded();
    const hook = renderHook(() => useDeleteTrait(ORG), {
      wrapper,
    });
    await act(async () => {
      await hook.result.current.mutateAsync('drafting').catch(() => {});
    });
    expect(invalid(keys.org)).toBe(false);
  });
});

describe('query gating', () => {
  async function flush() {
    await act(async () => {
      await Promise.resolve();
    });
  }

  it('does not fetch pending or mine for a non-member', async () => {
    const { wrapper } = makeClient();
    const access = leadershipFeatureAccess({
      viewerPk: VIEWER,
      track: { can_manage: true, can_view_own: false },
    });
    renderHook(() => usePendingReviews(ORG, access, null), { wrapper });
    renderHook(() => useMyReviews(ORG, access), { wrapper });
    await flush();
    expect(getPendingReviews).not.toHaveBeenCalled();
    expect(getMyReviews).not.toHaveBeenCalled();
  });

  it('fetches pending and mine for a member', async () => {
    vi.mocked(getPendingReviews).mockResolvedValue([pendingReview()]);
    vi.mocked(getMyReviews).mockResolvedValue([]);
    const { wrapper } = makeClient();
    const pending = renderHook(
      () => usePendingReviews(ORG, memberAccess, EVENT),
      { wrapper },
    );
    renderHook(() => useMyReviews(ORG, memberAccess), { wrapper });
    await waitFor(() => expect(pending.result.current.data).toHaveLength(1));
    expect(getPendingReviews).toHaveBeenCalledWith(ORG, EVENT);
    expect(getMyReviews).toHaveBeenCalledWith(ORG);
  });

  it('respects the enabled argument', async () => {
    const { wrapper } = makeClient();
    renderHook(() => usePendingReviews(ORG, memberAccess, null, false), {
      wrapper,
    });
    renderHook(() => useMyReviews(ORG, memberAccess, false), { wrapper });
    await flush();
    expect(getPendingReviews).not.toHaveBeenCalled();
    expect(getMyReviews).not.toHaveBeenCalled();
  });

  it('does not fetch moderation or settings for a plain member', async () => {
    const { wrapper } = makeClient();
    renderHook(() => useEventReviews(ORG, memberAccess, EVENT, true), {
      wrapper,
    });
    renderHook(() => useLeadershipSettings(ORG, memberAccess), { wrapper });
    await flush();
    expect(getEventReviews).not.toHaveBeenCalled();
    expect(getLeadershipSettings).not.toHaveBeenCalled();
  });

  it('does not fetch traits for a non-member without staff access', async () => {
    const { wrapper } = makeClient();
    const outsider = leadershipFeatureAccess({
      viewerPk: VIEWER,
      track: { can_view_own: false },
    });
    renderHook(() => useLeadershipTraits(ORG, outsider), { wrapper });
    await flush();
    expect(getTraits).not.toHaveBeenCalled();
  });

  it('fetches event reviews and traits for org staff who cannot manage', async () => {
    vi.mocked(getEventReviews).mockResolvedValue({} as never);
    vi.mocked(getTraits).mockResolvedValue(traits().traits);
    const { wrapper } = makeClient();
    const staffNonMember = leadershipFeatureAccess({
      viewerPk: VIEWER,
      track: { can_moderate: true, can_manage: false, can_view_own: false },
    });
    renderHook(() => useEventReviews(ORG, staffAccess, EVENT, true), {
      wrapper,
    });
    renderHook(() => useLeadershipTraits(ORG, staffNonMember), { wrapper });
    renderHook(() => useLeadershipSettings(ORG, staffAccess), { wrapper });
    await waitFor(() =>
      expect(getEventReviews).toHaveBeenCalledWith(ORG, EVENT),
    );
    await waitFor(() => expect(getTraits).toHaveBeenCalledWith(ORG));
    expect(getLeadershipSettings).not.toHaveBeenCalled();
  });

  it('fetches traits for a plain member', async () => {
    vi.mocked(getTraits).mockResolvedValue(traits().traits);
    const { wrapper } = makeClient();
    renderHook(() => useLeadershipTraits(ORG, memberAccess), { wrapper });
    await waitFor(() => expect(getTraits).toHaveBeenCalledWith(ORG));
  });

  it('fetches admin queries with manage access', async () => {
    vi.mocked(getLeadershipSettings).mockResolvedValue(leadershipSettings());
    const { wrapper } = makeClient();
    const hook = renderHook(() => useLeadershipSettings(ORG, adminAccess), {
      wrapper,
    });
    await waitFor(() => expect(hook.result.current.isSuccess).toBe(true));
    expect(getLeadershipSettings).toHaveBeenCalledWith(ORG);
  });

  it('fetches a member panel when unlocked', async () => {
    vi.mocked(getMemberLeadership).mockResolvedValue(memberLeadership());
    const { wrapper } = makeClient();
    const hook = renderHook(() => useMemberLeadership(ORG, memberAccess, 7), {
      wrapper,
    });
    await waitFor(() => expect(hook.result.current.data?.rating).toBe(4.1));
    expect(getMemberLeadership).toHaveBeenCalledWith(ORG, 7);
  });

  it('does not fetch anything while leadership is locked', async () => {
    const { wrapper } = makeClient();
    const locked = leadershipFeatureAccess({ viewerPk: VIEWER, track: null });
    renderHook(() => useMemberLeadership(ORG, locked, 7), { wrapper });
    renderHook(() => usePendingReviews(ORG, locked, null), { wrapper });
    renderHook(() => useMyReviews(ORG, locked), { wrapper });
    renderHook(() => useEventReviews(ORG, locked, EVENT, true), { wrapper });
    renderHook(() => useLeadershipSettings(ORG, locked), { wrapper });
    renderHook(() => useLeadershipTraits(ORG, locked), { wrapper });
    await flush();
    expect(getMemberLeadership).not.toHaveBeenCalled();
    expect(getPendingReviews).not.toHaveBeenCalled();
    expect(getMyReviews).not.toHaveBeenCalled();
    expect(getEventReviews).not.toHaveBeenCalled();
    expect(getLeadershipSettings).not.toHaveBeenCalled();
    expect(getTraits).not.toHaveBeenCalled();
  });

  it('does not fetch while access is unsettled', async () => {
    const { wrapper } = makeClient();
    const unsettled = makeOrgFeatureAccess({
      ...adminAccess,
      settled: false,
    });
    renderHook(() => useMemberLeadership(ORG, unsettled, 7), { wrapper });
    renderHook(() => usePendingReviews(ORG, unsettled, null), { wrapper });
    await flush();
    expect(getMemberLeadership).not.toHaveBeenCalled();
    expect(getPendingReviews).not.toHaveBeenCalled();
  });
});

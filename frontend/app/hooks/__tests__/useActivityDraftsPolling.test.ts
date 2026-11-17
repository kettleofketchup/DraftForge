// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ActivityDraftList } from '~/lib/activity-types';
import { useActivityViewStore } from '~/store/activityViewStore';
import {
  ACTIVITY_DRAFTS_POLL_MS,
  useActivityDraftsPolling,
} from '../useActivityDraftsPolling';

const mocks = vi.hoisted(() => ({
  fetchActivityDrafts: vi.fn(),
  postActivityView: vi.fn(),
  guard: vi.fn(),
}));

vi.mock('~/components/activity/LeaveDraftConfirm', () => ({
  useLeaveGuard: () => mocks.guard,
}));

vi.mock('~/lib/activity-api', () => ({
  fetchActivityDrafts: mocks.fetchActivityDrafts,
  postActivityView: mocks.postActivityView,
}));

const LIST: ActivityDraftList = {
  tournament: { id: 12, name: 'Kettle Cup' },
  team_draft: null,
  hero_drafts: [],
  launch_intent: null,
  notice: null,
  site_url: 'https://site.test',
};

async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    get: () => state,
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  useActivityViewStore.getState().reset();
  mocks.fetchActivityDrafts.mockResolvedValue(LIST);
  mocks.guard.mockImplementation((proceed: () => void) => proceed());
  setVisibility('visible');
});

afterEach(() => {
  vi.useRealTimers();
  vi.resetAllMocks();
});

describe('useActivityDraftsPolling', () => {
  it('fetches on mount and stores the list', async () => {
    renderHook(() => useActivityDraftsPolling(true));
    await flush();
    expect(mocks.fetchActivityDrafts).toHaveBeenCalledTimes(1);
    expect(useActivityViewStore.getState().drafts).toEqual(LIST);
  });

  it('fetches again every 30 seconds', async () => {
    renderHook(() => useActivityDraftsPolling(true));
    await flush();
    expect(ACTIVITY_DRAFTS_POLL_MS).toBe(30_000);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(mocks.fetchActivityDrafts).toHaveBeenCalledTimes(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(mocks.fetchActivityDrafts).toHaveBeenCalledTimes(3);
  });

  it('fetches when the frame becomes visible and on focus', async () => {
    renderHook(() => useActivityDraftsPolling(true));
    await flush();
    setVisibility('hidden');
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await flush();
    expect(mocks.fetchActivityDrafts).toHaveBeenCalledTimes(1);
    setVisibility('visible');
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await flush();
    expect(mocks.fetchActivityDrafts).toHaveBeenCalledTimes(2);
    act(() => {
      window.dispatchEvent(new Event('focus'));
    });
    await flush();
    expect(mocks.fetchActivityDrafts).toHaveBeenCalledTimes(3);
  });

  it('swallows fetch errors and keeps the last list', async () => {
    useActivityViewStore.setState({ drafts: LIST });
    mocks.fetchActivityDrafts.mockRejectedValue(new Error('boom'));
    renderHook(() => useActivityDraftsPolling(true));
    await flush();
    expect(useActivityViewStore.getState().drafts).toEqual(LIST);
  });

  it('does nothing while disabled', async () => {
    renderHook(() => useActivityDraftsPolling(false));
    await flush();
    act(() => {
      window.dispatchEvent(new Event('focus'));
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(mocks.fetchActivityDrafts).not.toHaveBeenCalled();
  });

  it('stops after unmount', async () => {
    const { unmount } = renderHook(() => useActivityDraftsPolling(true));
    await flush();
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    window.dispatchEvent(new Event('focus'));
    expect(mocks.fetchActivityDrafts).toHaveBeenCalledTimes(1);
  });
  it('applies a launch intent from the drafts list to this view only', async () => {
    useActivityViewStore.setState({ view: { kind: 'bracket' } });
    mocks.fetchActivityDrafts.mockResolvedValue({
      ...LIST,
      launch_intent: { intent_id: 'q1', kind: 'hero', id: 157 },
    });
    renderHook(() => useActivityDraftsPolling(true));
    await flush();
    expect(useActivityViewStore.getState().view).toEqual({
      kind: 'hero',
      id: 157,
    });
    expect(mocks.postActivityView).toHaveBeenCalledWith({
      action: 'view',
      from: { kind: 'bracket' },
      to: { kind: 'hero', id: 157 },
      trigger: 'launch_intent',
      intent_id: 'q1',
    });
  });

  it('ignores an intent that was already applied', async () => {
    useActivityViewStore.setState({
      view: { kind: 'bracket' },
      appliedIntentIds: new Set(['q1']),
    });
    mocks.fetchActivityDrafts.mockResolvedValue({
      ...LIST,
      launch_intent: { intent_id: 'q1', kind: 'hero', id: 157 },
    });
    renderHook(() => useActivityDraftsPolling(true));
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(useActivityViewStore.getState().view).toEqual({ kind: 'bracket' });
    expect(mocks.postActivityView).not.toHaveBeenCalled();
  });

  it('prompts again for an intent whose prompt a newer intent replaced', async () => {
    useActivityViewStore.setState({ view: { kind: 'hero', id: 156 } });
    mocks.guard.mockImplementation(() => {});
    const intent = (intent_id: string, id: number) => ({
      ...LIST,
      launch_intent: { intent_id, kind: 'hero' as const, id },
    });
    mocks.fetchActivityDrafts.mockResolvedValue(intent('q1', 157));
    renderHook(() => useActivityDraftsPolling(true));
    await flush();
    mocks.fetchActivityDrafts.mockResolvedValue(intent('q2', 158));
    act(() => {
      window.dispatchEvent(new Event('focus'));
    });
    await flush();
    mocks.fetchActivityDrafts.mockResolvedValue(intent('q1', 157));
    act(() => {
      window.dispatchEvent(new Event('focus'));
    });
    await flush();
    expect(mocks.guard).toHaveBeenCalledTimes(3);
    mocks.guard.mock.calls[2][0]();
    expect(useActivityViewStore.getState().view).toEqual({
      kind: 'hero',
      id: 157,
    });
  });

  it('does not prompt twice for the same pending intent', async () => {
    useActivityViewStore.setState({ view: { kind: 'hero', id: 156 } });
    mocks.guard.mockImplementation(() => {});
    mocks.fetchActivityDrafts.mockResolvedValue({
      ...LIST,
      launch_intent: { intent_id: 'q1', kind: 'hero', id: 157 },
    });
    renderHook(() => useActivityDraftsPolling(true));
    await flush();
    act(() => {
      window.dispatchEvent(new Event('focus'));
    });
    await flush();
    expect(mocks.fetchActivityDrafts).toHaveBeenCalledTimes(2);
    expect(mocks.guard).toHaveBeenCalledTimes(1);
  });

  it('shows a polled notice but never posts notice_seen itself', async () => {
    const notice = {
      intent_id: 'n1',
      kind: 'hero' as const,
      draft_id: 301,
      tournament_name: 'Other Cup',
      label: 'Game 301',
      url: 'https://site.test/herodraft/301',
    };
    mocks.fetchActivityDrafts.mockResolvedValue({ ...LIST, notice });
    renderHook(() => useActivityDraftsPolling(true));
    await flush();
    expect(useActivityViewStore.getState().notice).toEqual(notice);
    expect(mocks.postActivityView).not.toHaveBeenCalled();
  });

  it('keeps a session notice when a poll returns none', async () => {
    const notice = {
      kind: 'team' as const,
      draft_id: 77,
      tournament_name: 'Other Cup',
      label: 'Team draft',
      url: 'https://site.test/tournament/5/draft',
    };
    useActivityViewStore.getState().showNotice(notice);
    renderHook(() => useActivityDraftsPolling(true));
    await flush();
    expect(useActivityViewStore.getState().notice).toEqual(notice);
  });
});

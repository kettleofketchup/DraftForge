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
  setVisibility('visible');
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
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
});

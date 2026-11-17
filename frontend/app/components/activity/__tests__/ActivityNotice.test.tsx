// @vitest-environment jsdom
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ActivityNotice as Notice } from '~/lib/activity-types';
import { useActivityViewStore } from '~/store/activityViewStore';
import { ActivityNotice } from '../ActivityNotice';

const mocks = vi.hoisted(() => ({
  openExternal: vi.fn<(url: string) => Promise<boolean>>(),
  postActivityView: vi.fn(),
}));

vi.mock('~/lib/discord', () => ({
  openExternal: mocks.openExternal,
}));
vi.mock('~/lib/activity-api', () => ({
  fetchActivityDrafts: vi.fn(),
  postActivityView: mocks.postActivityView,
}));

const INTENT_NOTICE: Notice = {
  intent_id: 'n1',
  kind: 'hero',
  draft_id: 301,
  tournament_name: 'Other Cup',
  label: 'Winners R1 · A vs B',
  url: 'https://site.test/herodraft/301',
};

const CHANNEL_NOTICE: Notice = {
  kind: 'team',
  draft_id: 77,
  tournament_name: 'Other Cup',
  label: 'Team draft',
  url: 'https://site.test/tournament/5/draft',
};

function noticeSeenPosts(): unknown[] {
  return mocks.postActivityView.mock.calls
    .map((c) => c[0])
    .filter((b) => b.action === 'notice_seen');
}

beforeEach(() => {
  useActivityViewStore.getState().reset();
  mocks.openExternal.mockResolvedValue(true);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('ActivityNotice', () => {
  it('renders nothing without a notice', () => {
    render(<ActivityNotice />);
    expect(screen.queryByTestId('activity-notice')).toBeNull();
    expect(mocks.postActivityView).not.toHaveBeenCalled();
  });

  it("names the other tournament's draft and opens it in the browser", () => {
    useActivityViewStore.getState().showNotice(INTENT_NOTICE);
    render(<ActivityNotice />);
    expect(screen.getByTestId('activity-notice')).toHaveTextContent(
      "Winners R1 · A vs B in Other Cup is in another tournament's Activity.",
    );
    fireEvent.click(screen.getByTestId('activity-notice-open'));
    expect(mocks.openExternal).toHaveBeenCalledWith(
      'https://site.test/herodraft/301',
    );
  });

  it('posts notice_seen once per intent id across rerenders and repeats', () => {
    useActivityViewStore.getState().showNotice(INTENT_NOTICE);
    const { rerender } = render(<ActivityNotice />);
    rerender(<ActivityNotice />);
    act(() => useActivityViewStore.getState().showNotice({ ...INTENT_NOTICE }));
    expect(noticeSeenPosts()).toEqual([
      { action: 'notice_seen', intent_id: 'n1' },
    ]);
  });

  it('posts nothing for a channel-record notice without an intent id', () => {
    useActivityViewStore.getState().showNotice(CHANNEL_NOTICE);
    render(<ActivityNotice />);
    expect(screen.getByTestId('activity-notice')).toBeInTheDocument();
    expect(noticeSeenPosts()).toEqual([]);
  });

  it('dismisses and does not show the same notice again', () => {
    useActivityViewStore.getState().showNotice(INTENT_NOTICE);
    render(<ActivityNotice />);
    fireEvent.click(screen.getByTestId('activity-notice-dismiss'));
    expect(screen.queryByTestId('activity-notice')).toBeNull();
    act(() => useActivityViewStore.getState().showNotice(INTENT_NOTICE));
    expect(screen.queryByTestId('activity-notice')).toBeNull();
    expect(noticeSeenPosts()).toHaveLength(1);
  });
});

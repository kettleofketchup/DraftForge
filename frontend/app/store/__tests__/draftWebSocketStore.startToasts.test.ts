// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { DraftEvent } from '~/types/draftEvent';

vi.mock('sonner', () => ({ toast: vi.fn() }));

const { toast } = await import('sonner');
const { muteDraftStartToasts, showEventToast } =
  await import('~/store/draftWebSocketStore');

const event = (event_type: string): DraftEvent =>
  ({
    pk: 1,
    event_type,
    payload: {},
    actor: null,
    created_at: '2026-01-01T00:00:00Z',
  }) as unknown as DraftEvent;

describe('draft start toasts after a local reset', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(toast).mockClear();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('skips the start toast that would cover the reset result', () => {
    muteDraftStartToasts(5000);

    showEventToast(event('draft_started'));
    showEventToast(event('draft_lobby_opened'));

    expect(toast).not.toHaveBeenCalled();
  });

  it('still shows other events while muted', () => {
    muteDraftStartToasts(5000);

    showEventToast(event('draft_completed'));

    expect(toast).toHaveBeenCalledOnce();
  });

  it('shows start toasts again once the window has passed', () => {
    muteDraftStartToasts(5000);
    vi.advanceTimersByTime(5001);

    showEventToast(event('draft_started'));

    expect(toast).toHaveBeenCalledOnce();
  });
});

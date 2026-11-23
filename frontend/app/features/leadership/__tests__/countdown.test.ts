// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { formatCountdown, useCountdown } from '../countdown';

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

describe('formatCountdown', () => {
  it('formats days and hours', () => {
    expect(formatCountdown(2 * DAY + 3 * HOUR + 5 * MINUTE)).toBe('2d 3h left');
  });

  it('formats hours and minutes', () => {
    expect(formatCountdown(5 * HOUR + 12 * MINUTE + 30_000)).toBe(
      '5h 12m left',
    );
  });

  it('formats minutes', () => {
    expect(formatCountdown(4 * MINUTE + 59_000)).toBe('4m left');
  });

  it('formats under a minute', () => {
    expect(formatCountdown(59_000)).toBe('<1m left');
  });

  it('is closed at or past the deadline', () => {
    expect(formatCountdown(0)).toBe('Closed');
    expect(formatCountdown(-1)).toBe('Closed');
  });
});

describe('useCountdown', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('closes exactly at the deadline, not a tick late', () => {
    vi.useFakeTimers();
    const now = new Date('2026-11-22T12:00:00Z');
    vi.setSystemTime(now);
    const deadline = new Date(now.getTime() + 45_000).toISOString();
    const { result } = renderHook(() => useCountdown(deadline));

    expect(result.current.closed).toBe(false);
    act(() => {
      vi.advanceTimersByTime(44_900);
    });
    expect(result.current.closed).toBe(false);
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(result.current.closed).toBe(true);
    expect(result.current.msLeft).toBe(0);
  });

  it('restarts when the deadline changes', () => {
    vi.useFakeTimers();
    const now = new Date('2026-11-22T12:00:00Z');
    vi.setSystemTime(now);
    const { result, rerender } = renderHook(
      ({ iso }: { iso: string }) => useCountdown(iso),
      { initialProps: { iso: new Date(now.getTime() - 1).toISOString() } },
    );
    expect(result.current.closed).toBe(true);

    rerender({ iso: new Date(now.getTime() + 10 * MINUTE).toISOString() });
    expect(result.current.closed).toBe(false);
    expect(result.current.msLeft).toBe(10 * MINUTE);
  });
});

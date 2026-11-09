// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useAnimationFrameClock } from '~/lib/draftClock';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('useAnimationFrameClock', () => {
  it('re-derives every frame while not frozen', () => {
    let n = 0;
    const { result } = renderHook(() => useAnimationFrameClock({ derive: () => ++n, isFrozen: false, inputs: [] }));
    const first = result.current;
    act(() => { vi.advanceTimersByTime(50); });
    expect(result.current).toBeGreaterThan(first);
  });

  it('freezes the frame loop but re-derives once when inputs change', () => {
    let n = 0;
    const { result, rerender } = renderHook(
      ({ key }: { key: number }) => useAnimationFrameClock({ derive: () => ++n, isFrozen: true, inputs: [key] }),
      { initialProps: { key: 1 } },
    );
    const frozen = result.current;
    act(() => { vi.advanceTimersByTime(50); });
    expect(result.current).toBe(frozen);
    rerender({ key: 2 });
    expect(result.current).toBe(frozen + 1);
  });

  it('cancels the frame loop on unmount', () => {
    const cancel = vi.spyOn(globalThis, 'cancelAnimationFrame');
    const { unmount } = renderHook(() => useAnimationFrameClock({ derive: () => 1, isFrozen: false, inputs: [] }));
    unmount();
    expect(cancel).toHaveBeenCalled();
  });
});

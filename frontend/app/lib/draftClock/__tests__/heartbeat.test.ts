import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HEARTBEAT_INTERVAL_MS, startHeartbeatLoop } from '~/lib/draftClock';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('startHeartbeatLoop', () => {
  it('defaults to 3000 ms', () => expect(HEARTBEAT_INTERVAL_MS).toBe(3000));

  it('sends immediately, then every interval, until stopped', () => {
    const send = vi.fn();
    const stop = startHeartbeatLoop(send);
    expect(send).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(3000);
    expect(send).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(3000);
    expect(send).toHaveBeenCalledTimes(3);
    stop();
    vi.advanceTimersByTime(9000);
    expect(send).toHaveBeenCalledTimes(3);
  });
});

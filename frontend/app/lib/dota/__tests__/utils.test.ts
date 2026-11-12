import { describe, expect, it } from 'vitest';
import { formatDuration } from '../utils';

describe('formatDuration', () => {
  it('formats whole seconds as m:ss', () => {
    expect(formatDuration(0)).toBe('0:00');
    expect(formatDuration(59)).toBe('0:59');
    expect(formatDuration(90)).toBe('1:30');
    expect(formatDuration(2_345)).toBe('39:05');
  });
  it('rounds fractional seconds to the nearest second', () => {
    expect(formatDuration(29.6)).toBe('0:30');
    expect(formatDuration(59.6)).toBe('1:00');
  });
  it('clamps negative durations to 0:00', () => {
    expect(formatDuration(-0.005)).toBe('0:00');
    expect(formatDuration(-5)).toBe('0:00');
  });
});

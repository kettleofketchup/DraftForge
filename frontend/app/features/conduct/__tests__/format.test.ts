import { describe, expect, it } from 'vitest';
import { formatShowRate } from '../format';

describe('formatShowRate', () => {
  it('formats a scored rate as a percent', () => {
    expect(formatShowRate({ show_rate: 0.871, status: 'scored' })).toBe('87%');
  });

  it('shows New for a new member', () => {
    expect(formatShowRate({ show_rate: 0.871, status: 'new' })).toBe('New');
  });
});

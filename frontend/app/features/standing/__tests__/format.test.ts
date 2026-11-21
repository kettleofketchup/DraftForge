import { describe, expect, it } from 'vitest';
import { formatMetricValue, formatTotal } from '../format';

describe('formatMetricValue', () => {
  it('formats a new row as New', () => {
    expect(formatMetricValue({ value: null, status: 'new' }, 'percent')).toBe(
      'New',
    );
    expect(formatMetricValue({ value: 0.85, status: 'new' }, 'percent')).toBe(
      'New',
    );
  });

  it('formats a null value as New', () => {
    expect(formatMetricValue({ value: null, status: 'ranked' }, 'int')).toBe(
      'New',
    );
  });

  it('formats a percent', () => {
    expect(
      formatMetricValue({ value: 0.912, status: 'ranked' }, 'percent'),
    ).toBe('91%');
    expect(formatMetricValue({ value: 0, status: 'ranked' }, 'percent')).toBe(
      '0%',
    );
  });

  it('formats an int with separators', () => {
    expect(formatMetricValue({ value: 1234, status: 'ranked' }, 'int')).toBe(
      '1,234',
    );
  });

  it('formats a five-point score to one decimal', () => {
    expect(
      formatMetricValue({ value: 3.456, status: 'ranked' }, 'score5'),
    ).toBe('3.5');
  });
});

describe('formatTotal', () => {
  it('formats by metric format', () => {
    expect(formatTotal(1234, 'int')).toBe('1,234');
    expect(formatTotal(0.5, 'percent')).toBe('50%');
  });
});

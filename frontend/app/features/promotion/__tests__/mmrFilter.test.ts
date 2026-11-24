import { describe, expect, it } from 'vitest';
import { parseMmrBound, validateMmrRange } from '../mmrFilter';

describe('parseMmrBound', () => {
  it('treats blank as no bound', () => {
    expect(parseMmrBound('  ')).toEqual({ value: null, error: null });
  });

  it('accepts whole numbers within bounds', () => {
    expect(parseMmrBound('0').value).toBe(0);
    expect(parseMmrBound('20000').value).toBe(20000);
  });

  it('rejects decimals, negatives, text and out-of-range', () => {
    for (const text of ['4.5', '-1', 'abc', '20001']) {
      const bound = parseMmrBound(text);
      expect(bound.value).toBeNull();
      expect(bound.error).not.toBeNull();
    }
  });
});

describe('validateMmrRange', () => {
  it('accepts open and closed ranges', () => {
    expect(validateMmrRange(parseMmrBound('3000'), parseMmrBound(''))).toBe(
      null,
    );
    expect(
      validateMmrRange(parseMmrBound('3000'), parseMmrBound('3000')),
    ).toBeNull();
  });

  it('reports an inverted range and field errors', () => {
    expect(
      validateMmrRange(parseMmrBound('5000'), parseMmrBound('4000')),
    ).toMatch(/at least/);
    expect(validateMmrRange(parseMmrBound('x'), parseMmrBound(''))).toMatch(
      /^Min:/,
    );
    expect(validateMmrRange(parseMmrBound(''), parseMmrBound('-2'))).toMatch(
      /^Max:/,
    );
  });
});

import { describe, expect, it } from 'vitest';

import { parseGameMmrs } from './gameMmrs';

describe('parseGameMmrs', () => {
  it('converts string keys and drops unknown games', () => {
    expect(parseGameMmrs({ '1': 4000, '2': 2500, '9': 1 })).toEqual({
      1: 4000,
      2: 2500,
    });
  });

  it('returns an empty map for null or undefined', () => {
    expect(parseGameMmrs(null)).toEqual({});
    expect(parseGameMmrs(undefined)).toEqual({});
  });
});

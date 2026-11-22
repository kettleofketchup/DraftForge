import { describe, expect, it } from 'vitest';

import {
  DEFAULT_GAME_TYPE,
  DEFAULT_MMR_BOUNDS,
  GAME_LABEL,
  GAME_MMR_HOTKEY,
  GAME_SHORT_LABEL,
  GAME_SLUG,
  GAME_TYPE,
  GAME_TYPES,
  mmrTestId,
  showsLeagueMmr,
  toGameType,
} from './constants';

describe('game constants', () => {
  it('derives GAME_TYPES from GAME_TYPE', () => {
    expect(GAME_TYPES).toEqual(Object.values(GAME_TYPE));
  });

  it('labels every game', () => {
    for (const g of GAME_TYPES) {
      expect(GAME_LABEL[g]).toBeTruthy();
      expect(GAME_SHORT_LABEL[g]).toBeTruthy();
      expect(GAME_SLUG[g]).toBeTruthy();
    }
    expect(GAME_SHORT_LABEL[GAME_TYPE.DEADLOCK]).toBe('DL');
  });

  it('defaults to Dota 2 with the backend default bounds', () => {
    expect(DEFAULT_GAME_TYPE).toBe(GAME_TYPE.DOTA2);
    expect(DEFAULT_MMR_BOUNDS).toEqual([0, 20000]);
    expect(GAME_MMR_HOTKEY).toEqual({ 1: 'r', 2: 'k' });
  });

  it('toGameType falls back to Dota 2 for null and unknown ids', () => {
    expect(toGameType(null)).toBe(1);
    expect(toGameType(undefined)).toBe(1);
    expect(toGameType(99)).toBe(1);
    expect(toGameType(2)).toBe(2);
  });

  it('mmrTestId keeps the legacy Dota id', () => {
    expect(mmrTestId(1)).toBe('edit-user-mmr');
    expect(mmrTestId(2)).toBe('edit-user-mmr-deadlock');
  });

  it('shows league MMR only beside the league snapshot game', () => {
    expect(showsLeagueMmr(GAME_TYPE.DOTA2)).toBe(true);
    expect(showsLeagueMmr(GAME_TYPE.DEADLOCK)).toBe(false);
    expect(showsLeagueMmr(undefined)).toBe(true);
  });
});

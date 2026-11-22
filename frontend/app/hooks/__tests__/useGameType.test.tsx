// @vitest-environment jsdom
import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { GAME_TYPE, type GameTypeValue } from '~/components/game/constants';
import { useGameTypeStore } from '~/store/gameTypeStore';
import { resetGameType, withGameType } from '~/test-utils/gameType';
import { useContextGameType, useProvideGameType } from '../useGameType';

afterEach(resetGameType);

describe('useContextGameType', () => {
  it('falls back to Dota 2 outside any game context', () => {
    const { result } = renderHook(() => useContextGameType());
    expect(result.current).toBe(GAME_TYPE.DOTA2);
  });

  it('returns the page game from the store', () => {
    withGameType(GAME_TYPE.DEADLOCK);
    const { result } = renderHook(() => useContextGameType());
    expect(result.current).toBe(GAME_TYPE.DEADLOCK);
  });

  it('lets an explicit game override the page game', () => {
    withGameType(GAME_TYPE.DEADLOCK);
    const { result } = renderHook(() => useContextGameType(GAME_TYPE.DOTA2));
    expect(result.current).toBe(GAME_TYPE.DOTA2);
  });
});

describe('useProvideGameType', () => {
  const current = () => useGameTypeStore.getState().currentGameType;

  it('sets the game on mount and clears it on unmount', () => {
    const { unmount } = renderHook(() =>
      useProvideGameType(GAME_TYPE.DEADLOCK),
    );
    expect(current()).toBe(GAME_TYPE.DEADLOCK);
    unmount();
    expect(current()).toBeNull();
  });

  it('follows the game when the page switches entity', () => {
    const { rerender } = renderHook(
      ({ game }: { game: GameTypeValue | null }) => useProvideGameType(game),
      { initialProps: { game: GAME_TYPE.DEADLOCK as GameTypeValue | null } },
    );
    expect(current()).toBe(GAME_TYPE.DEADLOCK);
    rerender({ game: null });
    expect(current()).toBeNull();
    rerender({ game: GAME_TYPE.DOTA2 });
    expect(current()).toBe(GAME_TYPE.DOTA2);
  });
});

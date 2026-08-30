// @vitest-environment jsdom
// frontend/app/hooks/__tests__/usePlayerPositions.test.tsx
import { renderHook } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { usePlayerPositions } from '../usePlayerPositions';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useGameTypeStore } from '~/store/gameTypeStore';
import { GAME_TYPE } from '~/components/game/constants';

describe('usePlayerPositions', () => {
  beforeEach(() => { useUserCacheStore.getState().reset?.(); });

  it('returns dota positions when active game is dota, from the list-populated cache', () => {
    useUserCacheStore.getState().upsert({
      pk: 9, username: 'p',
      positions: { carry: 4, mid: 0, offlane: 0, soft_support: 0, hard_support: 0 },
    } as any);
    useGameTypeStore.setState({ currentGameType: GAME_TYPE.DOTA2 });
    const { result } = renderHook(() => usePlayerPositions(9));
    expect(result.current?.carry).toBe(4);
  });

  it('returns undefined when no active game', () => {
    useGameTypeStore.setState({ currentGameType: null });
    const { result } = renderHook(() => usePlayerPositions(9));
    expect(result.current).toBeUndefined();
  });
});

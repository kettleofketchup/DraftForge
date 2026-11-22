import { useEffect } from 'react';
import {
  DEFAULT_GAME_TYPE,
  type GameTypeValue,
} from '~/components/game/constants';
import { useGameTypeStore } from '~/store/gameTypeStore';

/** The page's game. null outside any game context (org, user and global pages). */
export const useGameType = () => useGameTypeStore((s) => s.currentGameType);

/**
 * The game a single-game surface renders: `override`, else the page's game,
 * else the default game (backend `resolve_game_type`).
 */
export function useContextGameType(override?: GameTypeValue): GameTypeValue {
  const current = useGameType();
  return override ?? current ?? DEFAULT_GAME_TYPE;
}

/** Puts a page's game in scope while it is mounted, like the org store. */
export function useProvideGameType(gameType: GameTypeValue | null): void {
  const setCurrentGameType = useGameTypeStore((s) => s.setCurrentGameType);
  useEffect(() => {
    if (gameType == null) return;
    setCurrentGameType(gameType);
    return () => setCurrentGameType(null);
  }, [gameType, setCurrentGameType]);
}

/**
 * GAME_TYPE — central enum mapping game name → integer ID.
 *
 * KEEP IN SYNC with backend: `backend/common/game.py:GameType(IntegerChoices)`
 * (checked by `gameTypeSync.test.ts`). The numeric IDs MUST match — they are
 * persisted in `Event.game_type`, `OrgEventDefaults.game_type`,
 * `OrgUserGameMmr.game_type`, etc.
 */
export const GAME_TYPE = {
  DOTA2: 1,
  DEADLOCK: 2,
} as const;

export type GameTypeValue = (typeof GAME_TYPE)[keyof typeof GAME_TYPE];

export const GAME_TYPES: readonly GameTypeValue[] = Object.values(GAME_TYPE);

export const GAME_LABEL: Record<GameTypeValue, string> = {
  1: 'Dota 2',
  2: 'Deadlock',
};

export const GAME_SHORT_LABEL: Record<GameTypeValue, string> = {
  1: 'D2',
  2: 'DL',
};

export const GAME_SLUG: Record<GameTypeValue, string> = {
  1: 'dota2',
  2: 'deadlock',
};

export const GAME_MMR_HOTKEY: Partial<Record<GameTypeValue, string>> = {
  1: 'r',
  2: 'k',
};

/** Mirrors backend `org/mmr.py` `MMR_BOUNDS`. */
export const GAME_MMR_BOUNDS: Partial<
  Record<GameTypeValue, readonly [number, number]>
> = {};

/** Mirrors backend `org/mmr.py` `DEFAULT_MMR_BOUNDS`. */
export const DEFAULT_MMR_BOUNDS = [0, 20000] as const;

export const DEFAULT_GAME_TYPE: GameTypeValue = GAME_TYPE.DOTA2;

export function isGameType(v: unknown): v is GameTypeValue {
  return (GAME_TYPES as readonly unknown[]).includes(v);
}

export function toGameType(v: number | null | undefined): GameTypeValue {
  return isGameType(v) ? v : DEFAULT_GAME_TYPE;
}

export function mmrTestId(g: GameTypeValue): string {
  return g === GAME_TYPE.DOTA2
    ? 'edit-user-mmr'
    : `edit-user-mmr-${GAME_SLUG[g]}`;
}

/**
 * GAME_TYPE — central enum mapping game name → integer ID.
 *
 * KEEP IN SYNC with backend: `backend/app/models.py:GameType(IntegerChoices)`.
 * When adding a new game, update BOTH files. The numeric IDs MUST match — they
 * are persisted in `Event.game_type`, `OrgEventDefaults.game_type`, etc.
 */
export const GAME_TYPE = {
  DOTA2: 1,
  DEADLOCK: 2,
} as const;

export type GameTypeValue = typeof GAME_TYPE[keyof typeof GAME_TYPE];

import { isGameType, type GameTypeValue } from './constants';

export type GameMmrs = Partial<Record<GameTypeValue, number>>;

export function parseGameMmrs(
  raw: Record<string, number> | null | undefined,
): GameMmrs {
  const out: GameMmrs = {};
  if (!raw) return out;
  for (const [key, value] of Object.entries(raw)) {
    const game = Number(key);
    if (isGameType(game) && typeof value === 'number') out[game] = value;
  }
  return out;
}

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import {
  DEFAULT_MMR_BOUNDS,
  GAME_LABEL,
  GAME_MMR_BOUNDS,
  GAME_SHORT_LABEL,
  GAME_SLUG,
  GAME_TYPE,
} from './constants';

const backendFile = (rel: string): string =>
  readFileSync(
    fileURLToPath(new URL(`../../../../backend/${rel}`, import.meta.url)),
    'utf8',
  );

function parseGameTypes(src: string): Record<string, number> {
  const body = src.match(/class GameType\([^)]*\):([\s\S]*?)(?=\n\S|$)/);
  if (!body) throw new Error('GameType class not found in backend source');
  const members: Record<string, number> = {};
  for (const m of body[1].matchAll(/^\s+([A-Z][A-Z0-9_]*)\s*=\s*(\d+)\s*,/gm)) {
    members[m[1]] = Number(m[2]);
  }
  if (Object.keys(members).length === 0)
    throw new Error('no GameType members parsed');
  return members;
}

function parseMmrBounds(
  src: string,
  ids: Record<string, number>,
): { bounds: Record<number, [number, number]>; fallback: [number, number] } {
  const block = src.match(/^MMR_BOUNDS\b[^=\n]*=\s*\{([^}]*)\}/m);
  if (!block) throw new Error('MMR_BOUNDS not found in backend source');
  const bounds: Record<number, [number, number]> = {};
  for (const m of block[1].matchAll(
    /(?:GameType\.([A-Z0-9_]+)|(\d+))\s*:\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)/g,
  )) {
    const id = m[1] ? ids[m[1]] : Number(m[2]);
    if (id == null) throw new Error(`unknown GameType member ${m[1]}`);
    bounds[id] = [Number(m[3]), Number(m[4])];
  }
  const def = src.match(
    /^DEFAULT_MMR_BOUNDS\b[^=\n]*=\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)/m,
  );
  if (!def) throw new Error('DEFAULT_MMR_BOUNDS not found in backend source');
  return { bounds, fallback: [Number(def[1]), Number(def[2])] };
}

describe('frontend/backend GameType sync', () => {
  const backendIds = parseGameTypes(backendFile('common/game.py'));

  it('GAME_TYPE matches backend GameType', () => {
    expect({ ...GAME_TYPE }).toEqual(backendIds);
  });

  it('every backend game has a label, short label and slug', () => {
    for (const id of Object.values(backendIds)) {
      expect(GAME_LABEL[id as keyof typeof GAME_LABEL]).toBeTruthy();
      expect(
        GAME_SHORT_LABEL[id as keyof typeof GAME_SHORT_LABEL],
      ).toBeTruthy();
      expect(GAME_SLUG[id as keyof typeof GAME_SLUG]).toBeTruthy();
    }
  });

  it('MMR bounds match backend org/mmr.py', () => {
    const { bounds, fallback } = parseMmrBounds(
      backendFile('org/mmr.py'),
      backendIds,
    );
    expect({ ...GAME_MMR_BOUNDS }).toEqual(bounds);
    expect([...DEFAULT_MMR_BOUNDS]).toEqual(fallback);
  });

  it('the parsers see a game added to the backend', () => {
    const extra = parseGameTypes(
      'class GameType(models.IntegerChoices):\n    DOTA2 = 1, "Dota 2"\n    CS2 = 3, "CS2"\n',
    );
    expect(extra).toEqual({ DOTA2: 1, CS2: 3 });
    expect({ ...GAME_TYPE }).not.toEqual(extra);
    const { bounds } = parseMmrBounds(
      'MMR_BOUNDS: dict[int, tuple[int, int]] = {GameType.CS2: (0, 30000)}\nDEFAULT_MMR_BOUNDS = (0, 20000)\n',
      extra,
    );
    expect(bounds).toEqual({ 3: [0, 30000] });
    expect(() => parseGameTypes('nothing here')).toThrow();
  });
});

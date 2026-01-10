import type { BracketMatch, BadgeMapping } from '../types';

/**
 * Badge utilities for linking winners bracket games to losers bracket destinations.
 */

// Color palette - high contrast on dark backgrounds
const BADGE_COLORS = [
  '#FF6B6B', // A - Coral Red
  '#4ECDC4', // B - Sky Blue
  '#FFE66D', // C - Sunny Yellow
  '#A78BFA', // D - Lavender
  '#6BCB77', // E - Mint Green
  '#FF85A2', // F - Hot Pink
  '#FFA94D', // G - Orange
  '#22D3EE', // H - Cyan
] as const;

/**
 * Get the badge letter for a winners bracket game based on its position.
 * Returns null if the game doesn't have a loser path.
 */
export function getBadgeLetter(
  bracketType: string,
  round: number,
  position: number,
  hasLoserPath: boolean
): string | null {
  // Only winners bracket games with loser path get badges
  if (bracketType !== 'winners' || !hasLoserPath) {
    return null;
  }

  // Calculate sequential index based on round and position
  // Round 1 has most games, each subsequent round has half
  // Round 1: positions 0,1,2,3 → indices 0,1,2,3 → A,B,C,D
  // Round 2: positions 0,1 → indices 4,5 → E,F
  // Round 3: position 0 → index 6 → G
  let index = 0;
  for (let r = 1; r < round; r++) {
    // Estimate games in earlier rounds (this is approximate, works for power-of-2 brackets)
    index += Math.pow(2, Math.max(0, 4 - r)); // Assumes max 16-team bracket
  }
  index += position;

  return String.fromCharCode(65 + (index % 26)); // A-Z, wraps after Z
}

/**
 * Get the badge color for a given letter.
 */
export function getBadgeColor(letter: string): string {
  const index = letter.charCodeAt(0) - 65; // A=0, B=1, etc.
  return BADGE_COLORS[index % BADGE_COLORS.length];
}

/**
 * Find which badge letter a losers bracket slot should display.
 * This requires knowing which winners bracket game feeds into this slot.
 */
export function getLoserSlotBadgeLetter(
  sourceGameId: string | undefined,
  allMatches: Array<{ id: string; bracketType: string; round: number; position: number; loserNextMatchId?: string }>
): string | null {
  if (!sourceGameId) return null;

  // Find the winners bracket game that feeds into this slot
  const sourceGame = allMatches.find(
    (m) => m.bracketType === 'winners' && m.loserNextMatchId === sourceGameId
  );

  if (!sourceGame) return null;

  return getBadgeLetter(
    sourceGame.bracketType,
    sourceGame.round,
    sourceGame.position,
    true
  );
}

/**
 * Build a mapping of losers bracket slots to their source badge letters.
 * This pre-computes which badge each losers bracket slot should display.
 */
export function buildBadgeMapping(matches: BracketMatch[]): BadgeMapping {
  const mapping: BadgeMapping = {};

  // Find all winners bracket games with loser paths
  const winnersWithLoserPath = matches.filter(
    (m) => m.bracketType === 'winners' && m.loserNextMatchId && m.loserNextMatchSlot
  );

  for (const game of winnersWithLoserPath) {
    const letter = getBadgeLetter(
      game.bracketType,
      game.round,
      game.position,
      true
    );

    if (letter && game.loserNextMatchId && game.loserNextMatchSlot) {
      const key = `${game.loserNextMatchId}:${game.loserNextMatchSlot}`;
      mapping[key] = letter;
    }
  }

  return mapping;
}

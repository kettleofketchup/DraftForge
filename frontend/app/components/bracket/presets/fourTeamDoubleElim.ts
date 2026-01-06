import type { BracketPreset } from './types';

/**
 * 4-Team Double Elimination Bracket
 *
 * Structure:
 * - Winners R1: 2 games (losers drop to L-R1)
 * - Winners Final: 1 game (loser drops to L-Final)
 * - Losers R1: 1 game (2 losers from W-R1)
 * - Losers Final: 1 game (W-Final loser vs L-R1 winner)
 * - Grand Finals: 1 game
 *
 * Flow:
 *   W-R1-G1 ──winner──┐
 *       │             │
 *       │loser        ├──▶ W-Final ──winner──┐
 *       │             │        │             │
 *       ▼             │        │loser        ├──▶ Grand Finals
 *   L-R1 ◀────────────┘        │             │
 *       │                      ▼             │
 *       │winner───────────▶ L-Final ─────────┘
 *       │
 *   W-R1-G2 ──winner──┘
 *       │
 *       │loser────────────────▶
 */
export const FOUR_TEAM_DOUBLE_ELIM: BracketPreset = {
  name: '4-Team Double Elimination',
  format: 'double_elimination',
  teamCount: 4,
  games: [
    // Winners Round 1 - Game 1
    {
      id: 'w-1-0',
      bracketType: 'winners',
      round: 1,
      position: 0,
      eliminationType: 'double',
      winnerTo: 'w-2-0',
      winnerSlot: 'radiant',
      loserTo: 'l-1-0',
      loserSlot: 'radiant',
    },
    // Winners Round 1 - Game 2
    {
      id: 'w-1-1',
      bracketType: 'winners',
      round: 1,
      position: 1,
      eliminationType: 'double',
      winnerTo: 'w-2-0',
      winnerSlot: 'dire',
      loserTo: 'l-1-0',
      loserSlot: 'dire',
    },
    // Winners Final (Round 2)
    {
      id: 'w-2-0',
      bracketType: 'winners',
      round: 2,
      position: 0,
      eliminationType: 'double',
      winnerTo: 'gf-1-0',
      winnerSlot: 'radiant',
      loserTo: 'l-2-0',
      loserSlot: 'radiant',
    },
    // Losers Round 1 (W-R1 losers play each other)
    {
      id: 'l-1-0',
      bracketType: 'losers',
      round: 1,
      position: 0,
      eliminationType: 'single',
      winnerTo: 'l-2-0',
      winnerSlot: 'dire',
    },
    // Losers Final (W-Final loser vs L-R1 winner)
    {
      id: 'l-2-0',
      bracketType: 'losers',
      round: 2,
      position: 0,
      eliminationType: 'single',
      winnerTo: 'gf-1-0',
      winnerSlot: 'dire',
    },
    // Grand Finals
    {
      id: 'gf-1-0',
      bracketType: 'grand_finals',
      round: 1,
      position: 0,
      eliminationType: 'single',
    },
  ],
};

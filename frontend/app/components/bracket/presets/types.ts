import type { BracketSectionType, EliminationType, TournamentFormat } from '../types';

/**
 * Bracket configuration types for generating tournament brackets
 */

export interface BracketGameTemplate {
  id: string;                           // e.g., 'w-1-0', 'l-2-0', 'gf-1-0'
  bracketType: BracketSectionType;
  round: number;
  position: number;
  eliminationType: EliminationType;
  winnerTo?: string;                    // ID of next game for winner
  winnerSlot?: 'radiant' | 'dire';
  loserTo?: string;                     // ID of next game for loser (double elim)
  loserSlot?: 'radiant' | 'dire';
}

export interface SwissConfig {
  roundCount: number;
  winsToAdvance?: number;               // e.g., 3 wins = advance to playoffs
  lossesToEliminate?: number;           // e.g., 3 losses = eliminated
  tiebreaker: 'buchholz' | 'head_to_head' | 'game_differential';
}

export interface BracketPreset {
  name: string;
  format: TournamentFormat;
  teamCount: number;
  games: BracketGameTemplate[];
  swiss?: SwissConfig;
}

/**
 * Generate match ID from bracket structure
 */
export function generateMatchId(bracketType: BracketSectionType, round: number, position: number): string {
  const typePrefix: Record<BracketSectionType, string> = {
    winners: 'w',
    losers: 'l',
    grand_finals: 'gf',
    swiss: 'sw',
  };
  return `${typePrefix[bracketType]}-${round}-${position}`;
}

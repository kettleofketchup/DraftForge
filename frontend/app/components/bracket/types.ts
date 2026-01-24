import type { TeamType } from '~/components/tournament/types';

// Bracket section types
export type BracketSectionType = 'winners' | 'losers' | 'grand_finals' | 'swiss';

// Match status
export type MatchStatus = 'pending' | 'live' | 'completed';

// Elimination type per game
export type EliminationType = 'single' | 'double' | 'swiss';

// Seeding methods
export type SeedingMethod = 'random' | 'mmr_total' | 'captain_mmr' | 'manual';

// Tournament format
export type TournamentFormat = 'single_elimination' | 'double_elimination' | 'swiss' | 'custom';

// Core match data for bracket display
export interface BracketMatch {
  id: string;                          // Temporary ID until persisted
  gameId?: number;                     // Backend Game.pk after save
  round: number;                       // Round number within bracket type
  position: number;                    // Position within round (0-indexed)
  bracketType: BracketSectionType;
  eliminationType: EliminationType;    // What happens to loser
  radiantTeam?: TeamType;
  direTeam?: TeamType;
  radiantScore?: number;
  direScore?: number;
  winner?: 'radiant' | 'dire';
  status: MatchStatus;
  steamMatchId?: number;               // Linked Steam match
  herodraft_id?: number;               // HeroDraft ID for this match
  nextMatchId?: string;                // Winner advances to this match
  nextMatchSlot?: 'radiant' | 'dire';  // Which slot in next match
  loserNextMatchId?: string;           // Loser advances to this match (double elim)
  loserNextMatchSlot?: 'radiant' | 'dire';
  swissRecordWins?: number;            // Swiss format - wins entering match
  swissRecordLosses?: number;          // Swiss format - losses entering match
}

// Full bracket state
export interface BracketState {
  tournamentId: number;
  bracketType: 'double_elimination' | 'swiss';
  matches: BracketMatch[];
  isDirty: boolean;                    // Has unsaved changes
  isVirtual: boolean;                  // Not yet persisted to backend
}

// React Flow node data - index signature required for @xyflow/react Node<T> compatibility
export interface MatchNodeData extends BracketMatch {
  // Badge mapping for this node (passed from parent)
  badgeMapping?: BadgeMapping;
  // Additional display properties can go here
  [key: string]: unknown;
}

export interface EmptySlotData {
  matchId: string;
  slot: 'radiant' | 'dire';
  roundLabel: string;
  [key: string]: unknown;
}

// API response types
export interface BracketResponse {
  tournamentId: number;
  matches: BracketMatch[];
}

// Badge mapping for losers bracket slots
// Maps losers game ID + slot to the badge letter
export interface BadgeMapping {
  [gameIdAndSlot: string]: string; // e.g., "l-1-0:radiant" -> "A"
}

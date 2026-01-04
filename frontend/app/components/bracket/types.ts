import type { TeamType } from '~/components/tournament/types';

// Bracket section types
export type BracketSectionType = 'winners' | 'losers' | 'grand_finals';

// Match status
export type MatchStatus = 'pending' | 'live' | 'completed';

// Seeding methods
export type SeedingMethod = 'random' | 'mmr_total' | 'captain_mmr' | 'manual';

// Core match data for bracket display
export interface BracketMatch {
  id: string;                          // Temporary ID until persisted
  gameId?: number;                     // Backend Game.pk after save
  round: number;                       // Round number within bracket type
  position: number;                    // Position within round (0-indexed)
  bracketType: BracketSectionType;
  radiantTeam?: TeamType;
  direTeam?: TeamType;
  radiantScore?: number;
  direScore?: number;
  winner?: 'radiant' | 'dire';
  status: MatchStatus;
  steamMatchId?: number;               // Linked Steam match
  nextMatchId?: string;                // Winner advances to this match
  nextMatchSlot?: 'radiant' | 'dire';  // Which slot in next match
}

// Full bracket state
export interface BracketState {
  tournamentId: number;
  bracketType: 'double_elimination' | 'swiss';
  matches: BracketMatch[];
  isDirty: boolean;                    // Has unsaved changes
  isVirtual: boolean;                  // Not yet persisted to backend
}

// React Flow node data
export interface MatchNodeData extends BracketMatch {
  // Additional display properties can go here
}

export interface EmptySlotData {
  matchId: string;
  slot: 'radiant' | 'dire';
  roundLabel: string;
}

// API response types
export interface BracketResponse {
  tournamentId: number;
  matches: BracketMatch[];
}
